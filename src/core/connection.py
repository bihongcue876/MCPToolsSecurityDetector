# 用于连接，并作为连接后其他工作的基础
from core.clients import MCPClient, create_client
from core.models import ServerConfig, ToolInfo


class ConnectionManager:
    """管理当前连接状态与客户端实例，负责状态管理与动作包装"""

    def __init__(self):
        self._client: MCPClient | None = None # 当前客户端
        self._current_server_id: str = "" # 当前服务器 ID
        self._cached_tools: list[ToolInfo] = [] # 工具列表缓存

    # ---------- 状态查询 ----------
    @property
    def client(self) -> MCPClient | None:
        return self._client

    @property
    def current_server_id(self) -> str:
        return self._current_server_id

    def is_connected(self) -> bool:
        return self._client is not None and self._client.connected

    # ---------- 连接管理 ----------
    def connect(self, config: ServerConfig) -> tuple[bool, str]:
        """连接到指定服务器，返回 (是否成功, 错误信息)"""
        self.disconnect()  # 先断开旧连接
        try:
            client = create_client(config)
            if client.connect():
                self._client = client
                self._current_server_id = config._id
                self._cached_tools = []
                return True, ""
            return False, client.last_error or "连接失败：初始化握手未成功"
        except Exception as e:
            return False, f"连接异常：{e}"

    def disconnect(self):
        """断开当前连接并清空状态"""
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:
                pass
        self._client = None
        self._current_server_id = ""
        self._cached_tools = []

    # ---------- 操作接口 ----------
    def list_tools(self, refresh: bool = False) -> list[ToolInfo]:
        """获取工具列表，默认使用缓存"""
        if self._client is None:
            return []
        if self._cached_tools and not refresh:
            return self._cached_tools
        self._cached_tools = self._client.list_tools()
        return self._cached_tools

    def call_tool(self, name: str, args: dict) -> dict:
        """调用工具，未连接时抛出异常"""
        if self._client is None:
            raise RuntimeError("尚未连接服务器")
        return self._client.call_tool(name, args)