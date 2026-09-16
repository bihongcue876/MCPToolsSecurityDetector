# MCP client
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urljoin
from abc import ABC, abstractmethod
from core.models import ServerConfig, ToolInfo
from core.server_runner import resolve_command
from app_config import APP_NAME,VERSION,BASE_DIR
from typing import Any

# MCP 协议版本：客户端支持的全部版本，从新到旧排序（ISO 日期可字典序比较）
SUPPORTED_PROTOCOL_VERSIONS = ["2026-07-28", "2025-11-25", "2025-06-18"]
DEFAULT_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]  # 默认声明最新版本
# 现代协议起始版本：此版本起废除 initialize 握手，改用 server/discover + 请求级 _meta 声明
MODERN_PROTOCOL_START = "2026-07-28"
# 现代协议在每个请求_meta中声明版本的字段名
META_PROTOCOL_KEY = "io.modelcontextprotocol/protocolVersion"
# 现代协议_meta信封中客户端能力字段名
META_CAPABILITIES_KEY = "io.modelcontextprotocol/clientCapabilities"
# 客户端标识信息
CLIENT_INFO = {"name": APP_NAME, "version": VERSION}


def resolve_project_path(path: str) -> str:
    """把配置中的相对路径解析为基于项目根的绝对路径

    服务器脚本 args 中常以相对路径书写（如相对项目根），
    而子进程工作目录未必是项目根，统一基于 BASE_DIR 解析，
    避免相对路径因工作目录不同而失效。
    """
    if not path:
        return path
    p = Path(path)
    if p.is_absolute():
        return path
    return str(BASE_DIR / p)


class MCPClient(ABC):
    """MCP 客户端抽象基类，定义统一接口，用于承接各个MCP服务器，适配后续不同MCP服务器的需求。"""

    def __init__(self, config: ServerConfig):
        self.config = config              # 服务器配置
        self._connected = False           # 连接状态
        self._protocol_version = ""       # 协商后的协议版本
        self._req_id = 0                  # 请求 ID 自增计数器
        self.last_error = ""              # 最近一次连接的失败原因

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def protocol_version(self) -> str:
        return self._protocol_version

    def _is_modern(self) -> bool:
        """是否为现代协议（版本 >= MODERN_PROTOCOL_START，ISO 日期可字典序比较）"""
        return bool(self._protocol_version) and self._protocol_version >= MODERN_PROTOCOL_START

    # ---------- 内部辅助 ----------
    def _next_id(self) -> int:
        """生成下一个请求 ID"""
        self._req_id += 1
        return self._req_id

    def _build_request(self, method: str, params: dict | None = None) -> dict:
        """组装JSON-RPC请求"""
        req:dict[str,Any] = {"jsonrpc": "2.0", "id": self._next_id(), "method": method}
        if params is not None:
            req["params"] = params
        # 修复协议版本有关资源：现代协议：每个请求在 _meta 信封中声明协议版本与客户端能力
        if self._is_modern():
            meta = req.setdefault("params", {}).setdefault("_meta", {})
            meta[META_PROTOCOL_KEY] = self._protocol_version
            meta.setdefault(META_CAPABILITIES_KEY, {})
        return req

    def _build_notification(self, method: str, params: dict | None = None) -> dict:
        """组装 JSON-RPC 通知（无 id）"""
        notif:dict[str,Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            notif["params"] = params
        return notif

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        """发送请求并返回响应 result 部分"""
        req = self._build_request(method, params)
        resp = self._send(req)
        if resp is None:
            raise RuntimeError(f"请求{method}未获得响应")
        if "error" in resp:
            err = resp["error"]
            raise RuntimeError(f"MCP错误[{err.get('code')}]: {err.get('message')}")
        return resp.get("result", {})

    # ---------- 子类实现方法 ----------
    @abstractmethod
    def _send(self, message: dict) -> dict | None:
        """发送消息并返回响应；若为通知则返回 None"""
        pass

    # ---------- 公共接口 ----------
    def connect(self) -> bool:
        """建立连接：动态协商协议版本并完成握手"""
        self.last_error = ""
        try:
            negotiated = self._negotiate_version()
            self._protocol_version = negotiated
            self._connected = True
            # 传统时代（initialize 握手）需发送 initialized 通知；现代协议无需
            if not self._is_modern():
                notif = self._build_notification("notifications/initialized")
                try:
                    self._send(notif)
                except Exception:
                    pass  # 通知失败不影响连接
            return True
        except Exception as e:
            self._connected = False
            self.last_error = str(e)
            return False

    def _negotiate_version(self) -> str:
        """协商协议版本，返回服务器实际使用的版本

        策略：优先尝试 server/discover（现代协议），失败回退到 initialize 握手。
        若服务器返回 UnsupportedProtocolVersionError，继续尝试下一个支持的版本。
        """
        # 现代协议：以最新版本声明探测 server/discover
        self._protocol_version = SUPPORTED_PROTOCOL_VERSIONS[0]
        try:
            result = self._rpc("server/discover", {})
            version = result.get("protocolVersion", "")
            if not version:
                # 服务器可能以 supportedVersions 列表声明，取双方共同的最新版本
                supported = result.get("supportedVersions") or []
                for v in SUPPORTED_PROTOCOL_VERSIONS:
                    if v in supported:
                        version = v
                        break
            if version:
                return version
        except RuntimeError:
            pass  # 不支持 server/discover，回退到 initialize

        # 传统协议：逐个尝试客户端支持的版本，取双方交集
        self._protocol_version = ""
        for version in SUPPORTED_PROTOCOL_VERSIONS:
            params = {
                "protocolVersion": version,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            }
            try:
                result = self._rpc("initialize", params)
                server_version = result.get("protocolVersion", "")
                if server_version:
                    return server_version
            except RuntimeError as e:
                # 服务器拒绝该版本（UnsupportedProtocolVersionError），尝试下一个
                if "nsupported protocol version" in str(e).lower():
                    continue
                raise
        raise RuntimeError("无法与服务器协商出共同支持的协议版本")

    def disconnect(self):
        """关闭连接（子类可扩展）"""
        self._connected = False

    def list_tools(self) -> list[ToolInfo]:
        """获取工具列表"""
        result = self._rpc("tools/list")
        tools = []
        for t in result.get("tools", []):
            tools.append(ToolInfo(
                name=t.get("name", ""),
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
                annotations=t.get("annotations", {}),
            ))
        return tools

    def call_tool(self, name: str, args: dict) -> dict:
        """调用指定工具"""
        result = self._rpc("tools/call", {"name": name, "arguments": args})
        return result
    
    def send_raw(self, message: dict) -> dict | None:
        """发送任意JSON-RPC消息，用于检测探测；现代协议下自动补充 _meta 信封。"""
        if self._is_modern():
            params = message.setdefault("params", {})
            if not isinstance(params, dict):
                params = {}
                message["params"] = params
            meta = params.setdefault("_meta", {})
            meta.setdefault(META_PROTOCOL_KEY, self._protocol_version)
            meta.setdefault(META_CAPABILITIES_KEY, {})
        return self._send(message)


class HttpMCPClient(MCPClient):
    """基于 Streamable HTTP 的客户端"""

    def __init__(self, config: ServerConfig):
        super().__init__(config)
        self._http = None  # 延迟创建 httpx.Client
        self._session_id = ""  # Streamable HTTP 会话 ID，初始化后必须随后续请求透传

    def _get_http(self):
        """懒加载 httpx 客户端"""
        if self._http is None:
            import httpx  # 延迟导入，避免未使用时加载
            self._http = httpx.Client(timeout=self.config.timeout)
        return self._http

    def _build_headers(self) -> dict:
        """组装请求头，包含认证信息与会话 ID"""
        headers = dict(self.config.headers)
        if self.config.auth_type == "bearer" and self.config.auth_value:
            headers["Authorization"] = f"Bearer {self.config.auth_value}"
        elif self.config.auth_type == "api_key" and self.config.auth_value:
            headers["X-API-Key"] = self.config.auth_value
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        headers.setdefault("Content-Type", "application/json")
        # Streamable HTTP 可能返回 SSE 流或 JSON
        headers.setdefault("Accept", "application/json, text/event-stream")
        return headers

    def _send(self, message: dict) -> dict | None:
        http = self._get_http()
        headers = self._build_headers()
        resp = http.post(self.config.url, json=message, headers=headers)
        if resp.status_code >= 400:
            # HTTP 错误（如会话未建立/协议不支持）走 RuntimeError，供协商回退捕获
            raise RuntimeError(f"MCP HTTP错误[{resp.status_code}]: {resp.text[:200]}")
        # 保存会话 ID，后续请求必须携带
        sid = resp.headers.get("mcp-session-id")
        if sid:
            self._session_id = sid
        # 通知请求无需解析响应
        if "id" not in message:
            return None
        # 解析响应，兼容 JSON 与 SSE 两种格式
        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return self._parse_sse_response(resp.text)
        return resp.json()

    def _parse_sse_response(self, text: str) -> dict | None:
        """从 SSE 文本中提取最后一个 JSON-RPC 响应"""
        result = None
        for line in text.splitlines():
            if line.startswith("data:"):
                data = line[5:].strip()
                if data:
                    try:
                        result = json.loads(data)
                    except json.JSONDecodeError:
                        continue
        return result

    def disconnect(self):
        super().disconnect()
        if self._http is not None:
            try:
                self._http.close()
            except Exception:
                pass
            self._http = None


class StdioMCPClient(MCPClient):
    """基于子进程 STDIO 的客户端"""

    def __init__(self, config: ServerConfig):
        super().__init__(config)
        self._process: subprocess.Popen | None = None
        self._abort_error = ""  # 连接失败原因，保留给后续重复发送时报出

    def connect(self) -> bool:
        """启动子进程并完成握手"""
        self._abort_error = ""
        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            if self.config.env:
                env.update(self.config.env)
            command = self._resolve_command(self.config.command)
            if not command:
                self.last_error = f"无法解析命令：{self.config.command}"
                return False
            cmd = [command] + [resolve_project_path(a) for a in self.config.args]
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=env,
            )  # 字节模式，不指定 text / bufsize
        except (FileNotFoundError, OSError) as e:
            self._process = None
            self.last_error = f"启动子进程失败：{e}"
            return False
        # 子进程已提前退出（常见于命令解析到错误解释器或缺依赖），
        # 此时管道已断开，继续握手只会写入已损坏的管道，提前失败并给出明确原因
        if self._process.poll() is not None:
            code = self._process.returncode
            self._abort()
            self.last_error = (
                f"STDIO子进程已退出(退出码{code})，"
                f"请检查命令路径{self.config.command}与服务器运行依赖"
            )
            return False
        ok = super().connect()
        if not ok:
            # 握手失败时清理子进程与管道，避免悬挂进程，
            # 也避免损坏的文件对象在 GC 时输出 finalize 异常噪声
            self._abort()
        return ok

    def _abort(self, reason: str = ""):
        """终止子进程并关闭全部管道（幂等，异常吞掉）

        reason 记录连接失败原因，供协商回退路径里重复发送时报出真实原因。
        """
        if reason:
            self._abort_error = reason
        proc = self._process
        self._process = None
        if proc is None:
            return
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is None:
                continue
            try:
                stream.close()
            except Exception:
                pass

    def _resolve_command(self, command: str) -> str | None:
        """把配置中的命令解析为可直接启动的完整路径

        Windows 上裸命令名（如 "python"）可能被系统“应用执行别名
        (App Execution Alias)”抢先解析到 Microsoft Store Python 等
        意外解释器而绕过 PATH 顺序；解释器类命令优先使用当前进程
        解释器（本项目服务器依赖 fastmcp 等均安装在当前 venv），
        其余命令按 PATH 解析。解析规则与示范服务器启动构件共用。
        """
        return resolve_command(command)

    def _send(self, message: dict) -> dict | None:
        if (self._process is None
                or self._process.stdin is None
                or self._process.stdout is None):
            if self._abort_error:
                raise RuntimeError(self._abort_error)
            raise RuntimeError("STDIO进程未启动或管道异常")
        # 写入字节
        line = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            self._process.stdin.write(line)
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            code = self._process.returncode if self._process is not None else None
            self._abort(f"STDIO写入失败（子进程可能已退出，退出码{code}）：{e}")
            raise RuntimeError(self._abort_error) from e
        # 通知无需响应
        if "id" not in message:
            return None
        # 逐行读取字节
        while True:
            resp_line = self._process.stdout.readline()
            if not resp_line:
                self._abort("STDIO连接已关闭")
                raise RuntimeError(self._abort_error)
            try:
                return json.loads(resp_line.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue  # 跳过非 JSON 行

    def disconnect(self):
        super().disconnect()
        self._abort()


class SseMCPClient(MCPClient):
    """基于 SSE 的客户端：GET 建立事件流，POST 发送请求，响应经事件流返回"""

    def __init__(self, config: ServerConfig):
        super().__init__(config)
        self._http = None
        self._msg_endpoint = ""  # endpoint 事件给出的消息POST端点
        self._reader = None      # 后台事件流读取线程
        self._stop = threading.Event()
        self._endpoint_ready = threading.Event()
        self._pending: dict[int, dict] = {}
        self._pending_event = threading.Event()

    def _get_http(self):
        if self._http is None:
            import httpx
            self._http = httpx.Client(timeout=self.config.timeout)
        return self._http

    def _build_headers(self) -> dict:
        headers = dict(self.config.headers)
        if self.config.auth_type == "bearer" and self.config.auth_value:
            headers["Authorization"] = f"Bearer {self.config.auth_value}"
        elif self.config.auth_type == "api_key" and self.config.auth_value:
            headers["X-API-Key"] = self.config.auth_value
        headers.setdefault("Accept", "text/event-stream")
        return headers

    def connect(self) -> bool:
        self.last_error = ""
        self._stop.clear()
        self._endpoint_ready.clear()
        self._pending.clear()
        self._msg_endpoint = ""
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        # 等待 endpoint 事件就绪，给出消息端点
        if not self._endpoint_ready.wait(timeout=self.config.timeout):
            self._abort()
            self.last_error = "SSE连接失败：未获取到消息端点"
            return False
        return super().connect()

    def _read_loop(self):
        """后台读取 SSE 事件流，解析 endpoint 与 message 事件"""
        http = self._get_http()
        try:
            with http.stream("GET", self.config.url, headers=self._build_headers()) as resp:
                resp.raise_for_status()
                event = ""
                data = ""
                for line in resp.iter_lines():
                    if self._stop.is_set():
                        break
                    if line == "":
                        self._handle_event(event, data)
                        event, data = "", ""
                    elif line.startswith("event:"):
                        event = line[len("event:"):].strip()
                    elif line.startswith("data:"):
                        data = line[len("data:"):].strip()
        except Exception as e:
            self.last_error = f"SSE事件流中断：{e}"
        self._stop.set()
        self._pending_event.set()

    def _handle_event(self, event: str, data: str):
        if event == "endpoint" and data:
            self._msg_endpoint = urljoin(self.config.url, data)
            self._endpoint_ready.set()
        elif event == "message" and data:
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                return
            rid = msg.get("id") if isinstance(msg, dict) else None
            if rid is not None:
                self._pending[rid] = msg
                self._pending_event.set()

    def _send(self, message: dict) -> dict | None:
        if not self._msg_endpoint:
            raise RuntimeError("SSE未就绪：缺少消息端点")
        http = self._get_http()
        rid = message.get("id")
        resp = http.post(self._msg_endpoint, json=message, headers=self._build_headers())
        if resp.status_code >= 400:
            raise RuntimeError(f"MCP SSE错误[{resp.status_code}]: {resp.text[:200]}")
        # 通知无需响应
        if "id" not in message:
            return None
        # 优先使用 POST 直接返回的 JSON-RPC 响应
        ct = resp.headers.get("content-type", "")
        if "application/json" in ct and rid is not None:
            try:
                body = resp.json()
                if isinstance(body, dict) and body.get("id") == rid:
                    return body
            except Exception:
                pass
        # 否则等待同 id 的响应从事件流返回
        while not self._stop.is_set():
            if rid in self._pending:
                return self._pending.pop(rid)
            self._pending_event.wait(timeout=0.5)
            self._pending_event.clear()
        raise RuntimeError(f"SSE请求未获得响应：{self.last_error}")

    def disconnect(self):
        super().disconnect()
        self._abort()

    def _abort(self):
        """停止读取线程并清理HTTP资源（幂等）"""
        self._stop.set()
        self._pending_event.set()
        if self._http is not None:
            try:
                self._http.close()
            except Exception:
                pass
            self._http = None
        self._msg_endpoint = ""
        self._pending.clear()

# 各个Client承接的MCP服务器区别为：发送与连接的形式不同。

def create_client(config: ServerConfig) -> MCPClient:
    """根据配置的传输类型创建对应客户端"""
    if config.transport == "http":
        return HttpMCPClient(config)
    elif config.transport == "stdio":
        return StdioMCPClient(config)
    elif config.transport == "sse":
        return SseMCPClient(config)
    raise ValueError(f"未知传输类型: {config.transport}")