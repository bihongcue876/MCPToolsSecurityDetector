# A组传输与鉴权检测：A1-A4四个检测模块的基准函数。每个函数返回一个DetectionResult(分类编号,分类说明,检查情况,检查说明,检查建议)，内部枚举所有分支
import socket
import ssl
from urllib.parse import urlparse
import httpx
from core.models import ServerConfig, DetectionResult
from core.clients import MCPClient
from core import utils
import re

MODULE = "A" # 检测模式模块编号

# ---------- A1TLS/明文传输 ----------

def check_a1_tls(config: ServerConfig) -> DetectionResult:
    """A1检测：判断传输是否加密、证书是否有效"""
    # stdio本地进程不涉及网络
    if config.transport == "stdio":
        return _result("A1", "TLS/明文传输", "skip", "本地进程，不涉及网络传输", "stdio模式下无使用TLS，也无需检测")
    url = (config.url or "").strip()
    if not url:
        return _result("A1", "TLS/明文传输", "warn", "配置缺失URL", "请补充服务器地址")
    # URL解析
    try:
        parsed = urlparse(url)
    except ValueError as e:
        return _result("A1", "TLS/明文传输", "fail", f"URL格式错误：{e}", "建议修正URL格式")
    scheme = (parsed.scheme or "").lower()
    host = parsed.hostname or ""
    # 明文HTTP
    if scheme == "http":
        return _result("A1", "TLS/明文传输", "fail", f"明文使用HTTP：{url}", "建议改用HTTPS并配置有效证书")
    if scheme not in ("https",):
        return _result("A1", "TLS/明文传输", "warn", f"未知协议：{scheme}", "建议使用HTTPS")
    # HTTPS：真实握手校验证书
    if not host:
        return _result("A1", "TLS/明文传输", "fail", "HTTPS地址缺少主机名", "建议检查URL有效性")
    port = parsed.port or 443
    status, evidence, suggestion = _tls_probe(host, port, config.timeout)
    return _result("A1", "TLS/明文传输", status, evidence, suggestion)

def _tls_probe(host: str, port: int, timeout: int) -> tuple[str, str, str]:
    """执行一次真实TLS握手，验证证书情况，返回(status, evidence, suggestion)"""
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert() or {}
                subject = _fmt_name(cert.get("subject", []))
                not_after = cert.get("notAfter", "")
                return ("pass", f"证书有效；主机={host}；颁发给={subject}；到期={not_after}", "证书有效，请定时关注证书有效性")
    except ssl.SSLCertVerificationError as e:
        msg = getattr(e, "verify_message", "") or str(e)
        low = msg.lower()
        if "expired" in low:
            return ("fail", f"证书已过期：{msg}", "建议更换有效证书")
        if "not yet valid" in low:
            return ("fail", f"证书尚未生效：{msg}", "建议检查证书生效时间")
        if "hostname" in low or "doesn't match" in low:
            return ("fail", f"证书主机名不匹配：{msg}", "建议更换匹配主机名的证书")
        if "self-signed" in low or "self signed" in low:
            return ("fail", f"自签名或不受信任证书：{msg}", "建议使用可信CA签发的证书")
        return ("fail", f"证书验证失败：{msg}", "建议检查证书链")
    except ssl.SSLError as e:
        return ("fail", f"TLS握手失败：{e}", "建议检查服务器TLS配置")
    except socket.timeout:
        return ("warn", f"连接超时（{timeout}s），无法完成TLS校验", "建议检查网络连通性与地址可达性")
    except socket.gaierror as e:
        return ("warn", f"DNS解析失败：{e}", "建议检查域名是否可解析")
    except OSError as e:
        return ("warn", f"网络错误：{e}", "建议检查目标可达性")

def _fmt_name(pairs) -> str:
    """把证书的subject/issuer字段格式化为字符串"""
    for item in pairs or []:
        for k, v in item:
            if k == "commonName":
                return v
    return "unknown"


# ---------- A2匿名访问 ----------

def check_a2_anonymous(config: ServerConfig) -> DetectionResult:
    """A2检测：不带任何凭证尝试连接"""
    if config.transport == "stdio":
        return _result("A2", "匿名访问", "skip", "本地进程不涉及远程鉴权", "stdio模式无需远程认证")

    url = (config.url or "").strip()
    if not url:
        return _result("A2", "匿名访问", "warn", "配置缺失URL，无法验证", "建议补充服务器地址后重试")

    # 构造匿名请求头：剔除常见认证头
    headers = dict(config.headers or {})
    for k in list(headers.keys()):
        if k.lower() in ("authorization", "x-api-key", "apikey", "api-key"):
            headers.pop(k, None)

    code, body = _anonymous_probe(url, config.timeout, headers)

    if code == -1:
        return _result("A2", "匿名访问", "warn", "连接超时，无法验证", "建议检查网络与地址")
    if code == -2:
        return _result("A2", "匿名访问", "warn", f"连接失败：{body}", "建议检查服务可达性")
    if code == -3:
        return _result("A2", "匿名访问", "warn", f"请求错误：{body}", "建议检查请求格式或协议")
    if code == 401:
        return _result("A2", "匿名访问", "pass", "返回状态码401，要求鉴权", "服务器具有鉴权机制")
    if code == 403:
        return _result("A2", "匿名访问", "pass", "返回状态码403，拒绝匿名访问", "服务器具有匿名拒绝策略")
    if 200 <= code < 300:
        return _result("A2", "匿名访问", "warn", f"无凭证即可访问（HTTP{code}），响应片段：{body[:120]}", "建议确认是否需要添加鉴权")
    if 500 <= code < 600:
        return _result("A2", "匿名访问", "warn", f"服务器错误HTTP{code}，无法判断鉴权", "建议先修复服务端错误")
    return _result("A2", "匿名访问", "warn", f"返回HTTP{code}，无法明确判断", "建议人工检查")


def _anonymous_probe(url: str, timeout: int, headers: dict) -> tuple[int, str]:
    """向目标发送一条initialize请求，返回(状态码, 响应片段)"""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2026-07-28",
            "capabilities": {},
            "clientInfo": {"name": "mcp-security-detector", "version": "0.1.0"},
        },
    }
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=timeout, follow_redirects=False)
        return resp.status_code, resp.text[:300]
    except httpx.TimeoutException:
        return -1, "timeout"
    except httpx.ConnectError as e:
        return -2, str(e)
    except httpx.RequestError as e:
        return -3, str(e)


# ---------- A3硬编码凭证 ----------

def check_a3_credentials(config: ServerConfig) -> DetectionResult:
    """A3检测：扫描headers/env/url中是否明文存放凭证，此功能完成明文扫描"""
    hits = []
    hits += _scan_dict(config.headers or {}, "headers")
    hits += _scan_dict(config.env or {}, "env")
    hits += _scan_url(config.url or "")

    if not hits:
        return _result("A3", "硬编码凭证", "pass", "未在headers/env/url中发现明文凭证", "凭证应当属于外部注入")

    lines = []
    for where, key, value in hits:
        lines.append(f"{where}.{key}={_mask(value)}")
    return _result("A3", "硬编码凭证", "fail", "发现明文凭证：" + "；".join(lines), "建议改用环境变量或密钥管理服务")


def _scan_dict(d: dict, label: str) -> list[tuple[str, str, str]]:
    """扫描字典，返回[(位置, 键, 值)]"""
    hits = []
    for k, v in d.items():
        if not isinstance(v, str):
            continue
        text = f"{k}: {v}"
        if utils.has_hardcoded_secret(text):
            hits.append((label, k, v))
    return hits


def _scan_url(url: str) -> list[tuple[str, str, str]]:
    """扫描URL查询参数中是否含token等"""
    hits = []
    parsed = urlparse(url)
    if not parsed.query:
        return hits
    sensitive = ("token", "api_key", "apikey", "api-key", "password", "passwd", "secret", "key")
    for pair in parsed.query.split("&"):
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        if k.lower() in sensitive:
            hits.append(("url", k, v))
    return hits


def _mask(s: str, keep: int = 6) -> str:
    """数据脱敏处理"""
    if not s:
        return ""
    if len(s) <= keep:
        return s + "***"
    return s[:keep] + "***"


# ---------- A4协议握手 ----------

def check_a4_handshake(config: ServerConfig, client: MCPClient | None) -> DetectionResult:
    """A4检测：协议握手 + 错误响应是否泄露内部信息"""
    if client is None or not client.connected:
        return _result("A4", "协议握手与错误处理", "warn", "无已连接客户端，无法验证", "建议先完成连接再检测")
    version = (client.protocol_version or "").strip()
    if not version:
        return _result("A4", "协议握手与错误处理", "warn", "服务器未返回协议版本", "建议检查服务器初始化响应")
    # 主动探测：发送两条错误请求
    try:
        leaked, evidence = _probe_error_leakage(client)
    except Exception as e:
        return _result("A4", "协议握手与错误处理", "warn", f"协议版本：{version}；错误响应探测失败：{e}", "建议人工检查错误响应")
    if leaked: # 出现内部栈泄露
        return _result("A4", "协议握手与错误处理", "fail", f"协议版本：{version}；错误响应泄露内部信息：{evidence}", "建议服务器统一错误响应格式，屏蔽堆栈与路径")
    if evidence:
        return _result("A4", "协议握手与错误处理", "pass", f"协议版本：{version}；错误响应返回：{evidence}", "错误响应详情未发现堆栈泄露")
    return _result("A4", "协议握手与错误处理", "pass", f"协议版本：{version}；服务器未返回错误详情", "无处理建议")

# ---------- A4堆栈泄露特征 ----------

_STACK_PATTERNS = [
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r'File\s+"[^"]+\.py"'),
    re.compile(r"File\s+'[^']+\.py'"),
    re.compile(r"[A-Za-z]:\\[^\s\"']+\.py"),      # Windows路径
    re.compile(r"/(?:usr|home|var|opt|root)/[^\s\"']+\.py"),  # Unix路径
    re.compile(r"site-packages"),
    re.compile(r"line\s+\d+,\s+in\s+\w+"),
    re.compile(r"\bfastmcp\b[\s\S]{0,40}\d+\.\d+"),
    re.compile(r"\buvicorn\b"),
    re.compile(r"\bstarlette\b"),
    re.compile(r"\bpydantic\b[\s\S]{0,40}\d+\.\d+"),
]

def _detect_stack_trace(text: str) -> list[str]:
    """检测文本中的堆栈/内部信息特征，返回命中模式列表"""
    if not text:
        return []
    hits = []
    for pat in _STACK_PATTERNS:
        if pat.search(text):
            hits.append(pat.pattern)
    return hits

def _probe_error_leakage(client: MCPClient) -> tuple[bool, str]:
    """向客户端发送两条错误请求，检查错误响应是否泄露内部信息。返回(是否泄露, 探测证据文本)

    泄露判定使用完整原文；展示给用户的证据对返回的 data 做中心掩码，
    只保留头尾片段，防止把探测到的敏感内容直接扩散出去。
    """
    probes = [
        {"jsonrpc": "2.0", "id": 9001, "method": "__nonexistent_method__"},
        {"jsonrpc": "2.0", "id": 9002, "method": "tools/call", "params": {}},
    ]

    fragments_raw = []
    fragments_show = []
    for req in probes:
        try:
            resp = client.send_raw(req)
        except Exception as e:
            fragments_raw.append(f"[{req['method']}]发送异常：{e}")
            fragments_show.append(f"[{req['method']}]发送异常：{_mask_center(str(e))}")
            continue
        if not isinstance(resp, dict):
            fragments_raw.append(f"[{req['method']}]响应：{str(resp)[:200]}")
            fragments_show.append(f"[{req['method']}]响应：{_mask_center(str(resp))}")
            continue
        err = resp.get("error")
        if not isinstance(err, dict):
            fragments_raw.append(f"[{req['method']}]响应：{str(resp)[:200]}")
            fragments_show.append(f"[{req['method']}]响应：{_mask_center(str(resp))}")
            continue
        code = err.get("code", "")
        msg = str(err.get("message", ""))
        data = str(err.get("data", ""))
        frag_raw = f"[{req['method']}] code={code} {msg}"
        frag_show = f"[{req['method']}] code={code} {msg}"
        if data:
            frag_raw += f" data={data}"
            frag_show += f" data={_mask_center(data)}"
        fragments_raw.append(frag_raw)
        fragments_show.append(frag_show)
    full = " | ".join(fragments_raw)
    shown = " | ".join(fragments_show)
    if _detect_stack_trace(full):
        return True, f"命中泄露特征：{shown[:400]}"
    return False, shown[:400]


def _mask_center(text: str, head: int = 8, tail: int = 4, marker: str = "***") -> str:
    """中心掩码：长文本只保留头 tail 字符，中间以 marker 替代"""
    if not text:
        return ""
    if len(text) <= head + tail:
        return text[:head] + marker
    return text[:head] + marker + text[-tail:]

# ---------- 内部工具 ----------

def _result(item_id: str, item_name: str, status: str,
            evidence: str, suggestion: str) -> DetectionResult:
    """统一构造DetectionResult"""
    return DetectionResult(
        module=MODULE,
        item_id=item_id,
        item_name=item_name,
        status=status,
        evidence=evidence,
        suggestion=suggestion,
    )