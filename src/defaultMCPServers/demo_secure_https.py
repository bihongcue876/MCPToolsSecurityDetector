# 示范服务器：推荐的完全安全配置（HTTPS，单进程两端点）
# 端点：/mcp 不鉴权；/auth/mcp 强制Bearer鉴权。两者同进程同端口，启动一次即同时可用。
# 本地证书由 cryptography 生成：首次运行输出 certutil 命令，导入本地CA后A1即为通过。
import datetime
import ipaddress
import socket
import sys
from pathlib import Path
from typing import Annotated

import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

# 证书属数据：开发态放项目根 data，打包态放可执行文件同级 data（临时解压目录退出即丢，不可用）
if getattr(sys, "frozen", False):
    DATA_DIR = Path(sys.executable).resolve().parent / "data"
else:
    DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CERT_DIR = DATA_DIR / "demo-certs"
HOST = "127.0.0.1"
PORT = 7656
DEMO_TOKEN = "demo-token-3f9a1c7e5b2d"
AUTH_PREFIX = "/auth"

mcp = FastMCP("Demo Secure HTTPS")

# 严格Schema：字符串参数带maxLength（B3通过）；只读工具正确声明readOnlyHint（B4通过）
# 返回内容为普通文本，无注入词与链接（B2通过）；描述简洁无指令性语句（B1通过）


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_status() -> str:
    return "ok"


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_item(item_id: Annotated[str, Field(max_length=64)]) -> str:
    return f"item:{item_id}"


def _ensure_bundle(ca_crt_p: Path, bundle_p: Path) -> None:
    """生成“公开根证书 + 本地CA”的合并信任包，供 SSL_CERT_FILE 使用"""
    prefix = b""
    try:
        import certifi

        prefix = Path(certifi.where()).read_bytes()
    except Exception:
        prefix = b""
    bundle_p.write_bytes(prefix + ca_crt_p.read_bytes())


def _ensure_certificates() -> tuple[Path, Path, Path]:
    """生成（或复用）本地CA与服务器证书，返回(ca_cer, server_crt, server_key)"""
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    ca_key_p = CERT_DIR / "ca.key"
    ca_crt_p = CERT_DIR / "ca.crt"
    ca_cer_p = CERT_DIR / "ca.cer"
    ca_bundle_p = CERT_DIR / "ca-bundle.pem"
    srv_key_p = CERT_DIR / "server.key"
    srv_crt_p = CERT_DIR / "server.crt"
    if all(p.exists() for p in (ca_crt_p, ca_cer_p, srv_key_p, srv_crt_p)):
        _ensure_bundle(ca_crt_p, ca_bundle_p)
        return ca_cer_p, srv_crt_p, srv_key_p

    now = datetime.datetime.now(datetime.timezone.utc)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "MCP Demo Local CA")])
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True,
                crl_sign=True, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )

    srv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    srv_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
        .issuer_name(ca_name)
        .public_key(srv_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.IPv4Address(HOST)),
            ]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=True,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(srv_key.public_key()), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )

    ca_crt_p.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    ca_cer_p.write_bytes(ca_cert.public_bytes(serialization.Encoding.DER))
    _ensure_bundle(ca_crt_p, ca_bundle_p)
    srv_crt_p.write_bytes(srv_cert.public_bytes(serialization.Encoding.PEM))
    srv_key_p.write_bytes(
        srv_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return ca_cer_p, srv_crt_p, srv_key_p


class BearerPathMiddleware:
    """按路径前缀实施Bearer鉴权，并把 /auth/xxx 重写为 /xxx 交给MCP应用"""

    def __init__(self, app, token: str, prefix: str = AUTH_PREFIX):
        self.app = app
        self.token = token
        self.prefix = prefix

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            path = scope.get("path", "")
            if path == self.prefix or path.startswith(self.prefix + "/"):
                if not self._authorized(scope):
                    await self._deny(send)
                    return
                rewritten = path[len(self.prefix):] or "/"
                scope = dict(scope)
                scope["path"] = rewritten
                if isinstance(scope.get("raw_path"), (bytes, bytearray)):
                    scope["raw_path"] = rewritten.encode("utf-8")
        await self.app(scope, receive, send)

    def _authorized(self, scope) -> bool:
        for key, value in scope.get("headers", []):
            if key.lower() == b"authorization":
                return value.decode("latin-1").strip() == f"Bearer {self.token}"
        return False

    async def _deny(self, send):
        body = b'{"error":"unauthorized"}'
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})


def _port_in_use(host: str, port: int) -> bool:
    """探测端口是否已被监听，用于给出更明确的启动失败提示"""
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _pause_on_failure(reason: str) -> None:
    """启动失败时保留终端窗口，避免用户只看到一闪而过"""
    print(f"启动失败：{reason}")
    print(f"若为端口占用，请先停止占用 {PORT} 端口的程序，或修改本脚本的 PORT 常量。")
    try:
        input("按回车键关闭窗口...")
    except Exception:
        pass


def demo_secure_https_run():
    ca_cer, srv_crt, srv_key = _ensure_certificates()
    bundle = CERT_DIR / "ca-bundle.pem"
    app = mcp.http_app(path="/mcp", transport="streamable-http")
    wrapped = BearerPathMiddleware(app, token=DEMO_TOKEN)
    print("=" * 64)
    print("示范服务器：推荐的完全安全配置（HTTPS）")
    print(f"  不鉴权端点：https://{HOST}:{PORT}/mcp")
    print(f"  鉴权端点　：https://{HOST}:{PORT}{AUTH_PREFIX}/mcp")
    print(f"  鉴权口令　：Bearer {DEMO_TOKEN}")
    print(f"  本地CA证书：{ca_cer}")
    print(f"  信任包　　：{bundle}")
    print("让本工具信任该证书（A1与连接均生效），启动本工具前设置环境变量：")
    print(f'  set SSL_CERT_FILE="{bundle}"')
    print("或把本地CA导入当前用户的受信任根证书颁发机构：")
    print(f'  certutil -addstore -user Root "{ca_cer}"')
    print("=" * 64)
    if _port_in_use(HOST, PORT):
        _pause_on_failure(f"端口 {PORT} 已被占用")
        return
    try:
        uvicorn.run(
            wrapped,
            host=HOST,
            port=PORT,
            ssl_certfile=str(srv_crt),
            ssl_keyfile=str(srv_key),
            log_level="warning",
        )
    except BaseException as e:  # 含端口占用等导致的 SystemExit
        _pause_on_failure(str(e) or e.__class__.__name__)


if __name__ == "__main__":
    demo_secure_https_run()