# MCP client
import json
import os
import subprocess
from abc import ABC, abstractmethod
from core.models import ServerConfig, ToolInfo
from app_config import APP_NAME,VERSION
from typing import Any

# MCP 协议版本（客户端声明使用的版本）
DEFAULT_PROTOCOL_VERSION = "2024-11-05"
# 客户端标识信息
CLIENT_INFO = {"name": APP_NAME, "version": VERSION}


class MCPClient(ABC):
    """MCP 客户端抽象基类，定义统一接口，用于承接各个MCP服务器，适配后续不同MCP服务器的需求。"""

    def __init__(self, config: ServerConfig):
        self.config = config              # 服务器配置
        self._connected = False           # 连接状态
        self._protocol_version = ""       # 协商后的协议版本
        self._req_id = 0                  # 请求 ID 自增计数器

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def protocol_version(self) -> str:
        return self._protocol_version

    # ---------- 内部辅助 ----------
    def _next_id(self) -> int:
        """生成下一个请求 ID"""
        self._req_id += 1
        return self._req_id

    def _build_request(self, method: str, params: dict | None = None) -> dict:
        """组装 JSON-RPC 请求"""
        req:dict[str,Any] = {"jsonrpc": "2.0", "id": self._next_id(), "method": method}
        if params is not None:
            req["params"] = params
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

    # ---------- 子类需要实现的方法 ----------
    @abstractmethod
    def _send(self, message: dict) -> dict | None:
        """发送消息并返回响应；若为通知则返回 None"""
        pass

    # ---------- 公共接口 ----------
    def connect(self) -> bool:
        """建立连接并完成 initialize 握手"""
        try:
            params = {
                "protocolVersion": DEFAULT_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            }
            result = self._rpc("initialize", params)
            self._protocol_version = result.get("protocolVersion", "")
            self._connected = True
            # 发送 initialized 通知（无响应）
            notif = self._build_notification("notifications/initialized")
            try:
                self._send(notif)
            except Exception:
                pass  # 通知失败不影响连接
            return True
        except Exception:
            self._connected = False
            return False

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


class HttpMCPClient(MCPClient):
    """基于 Streamable HTTP 的客户端"""

    def __init__(self, config: ServerConfig):
        super().__init__(config)
        self._http = None  # 延迟创建 httpx.Client

    def _get_http(self):
        """懒加载 httpx 客户端"""
        if self._http is None:
            import httpx  # 延迟导入，避免未使用时加载
            self._http = httpx.Client(timeout=self.config.timeout)
        return self._http

    def _build_headers(self) -> dict:
        """组装请求头，包含认证信息"""
        headers = dict(self.config.headers)
        if self.config.auth_type == "bearer" and self.config.auth_value:
            headers["Authorization"] = f"Bearer {self.config.auth_value}"
        elif self.config.auth_type == "api_key" and self.config.auth_value:
            headers["X-API-Key"] = self.config.auth_value
        headers.setdefault("Content-Type", "application/json")
        # Streamable HTTP 可能返回 SSE 流或 JSON
        headers.setdefault("Accept", "application/json, text/event-stream")
        return headers

    def _send(self, message: dict) -> dict | None:
        http = self._get_http()
        headers = self._build_headers()
        resp = http.post(self.config.url, json=message, headers=headers)
        resp.raise_for_status()
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

    def connect(self) -> bool:
        """启动子进程并完成握手"""
        try:
            # 合并环境变量：系统环境 + 配置中的 env
            env = os.environ.copy()
            if self.config.env:
                env.update(self.config.env)
            cmd = [self.config.command] + list(self.config.args)
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except (FileNotFoundError, OSError):
            self._process = None
            return False
        return super().connect()

    def _send(self, message: dict) -> dict | None:
        if (self._process is None
            or self._process.stdin is None
            or self._process.stdout is None):
            raise RuntimeError("STDIO进程未启动或管道异常")
        # 每行一条 JSON 消息
        line = json.dumps(message, ensure_ascii=False) + "\n"
        self._process.stdin.write(line)
        self._process.stdin.flush()
        # 通知无需读取响应
        if "id" not in message:
            return None
        # 逐行读取，跳过空行和非 JSON 行
        while True:
            resp_line = self._process.stdout.readline()
            if not resp_line:
                raise RuntimeError("STDIO连接已关闭")
            resp_line = resp_line.strip()
            if not resp_line:
                continue
            try:
                return json.loads(resp_line)
            except json.JSONDecodeError:
                continue  # 跳过非 JSON 输出

    def disconnect(self):
        super().disconnect()
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None


class SseMCPClient(MCPClient):
    """基于 SSE 的客户端（骨架，具体实现后续迭代）"""

    def __init__(self, config: ServerConfig):
        super().__init__(config)
        self._http = None
        self._post_endpoint = ""  # SSE 事件流返回的 POST 端点

    def _send(self, message: dict) -> dict | None:
        # 尚未实现完整 SSE 逻辑
        raise NotImplementedError("SSE客户端尚未实现，请使用HTTP或STDIO模式")

    def connect(self) -> bool:
        # 暂时直接返回失败
        return False

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