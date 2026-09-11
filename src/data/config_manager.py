# 服务器配置与参数（登记）
import json
from pathlib import Path
from src.app_config import SERVERS_CFG_PATH  # server config json file path here.
from src.core.models import ServerConfig  # server config data module class here.


# server config manage only
class ConfigManager:
    def __init__(self, path: Path = SERVERS_CFG_PATH):
        self.path = path
        self.servers: list[ServerConfig] = []
        self.load()

    def load(self):
        """从JSON文件读取全部服务器配置，损坏时降级为空列表"""
        if not self.path.exists():
            self.servers = []
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.servers = [ServerConfig(**item) for item in data]
        except (json.JSONDecodeError, TypeError, KeyError):
            self.servers = []

    def save(self):
        """将当前服务器列表写回JSON文件"""
        data = [s.__dict__ for s in self.servers]
        self.path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    # add new config
    def add(self, config: ServerConfig) -> bool:
        """添加配置，ID 重复时返回 False"""
        if self.get_by_id(config._id):
            return False
        self.servers.append(config)
        self.save()
        return True

    # update config
    def update(self, config_id: str, new_config: ServerConfig) -> bool:
        """更新配置，未找到时返回 False"""
        for i, s in enumerate(self.servers):
            if s._id == config_id:
                self.servers[i] = new_config
                self.save()
                return True
        return False

    # delete config
    def delete(self, config_id: str) -> bool:
        """删除配置，未找到时返回 False"""
        before = len(self.servers)
        self.servers = [s for s in self.servers if s._id != config_id]
        if len(self.servers) == before:
            return False
        self.save()
        return True

    def get_by_id(self, config_id: str) -> ServerConfig | None:
        for s in self.servers:
            if s._id == config_id:
                return s
        return None

    def get_all(self) -> list[ServerConfig]:
        return self.servers