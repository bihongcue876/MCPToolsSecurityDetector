# 服务器配置与参数（登记）
import json
from pathlib import Path
from src.app_config import SERVERS_CFG_PATH  # server config json file path here.
from src.core.models import ServerConfig # server config data module class here.

# server config manage only
class ConfigManager:
    def __init__(self, path: Path = SERVERS_CFG_PATH):
        self.path = path
        self.servers: list[ServerConfig] = []
        self.load()

    def load(self):
        """从JSON文件读取全部服务器配置"""
        if not self.path.exists():
            self.servers = []
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.servers = [ServerConfig(**item) for item in data]

    def save(self):
        """将当前服务器列表写回JSON文件"""
        data = [s.__dict__ for s in self.servers]
        self.path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    # add new config
    def add(self, config: ServerConfig):
        self.servers.append(config)
        self.save()
    
    # update config
    def update(self, config_id: str, new_config: ServerConfig):
        for i, s in enumerate(self.servers):
            if s._id == config_id:
                self.servers[i] = new_config
                self.save()
                return
    
    # delete config(if not default)
    def delete(self, config_id: str):
        self.servers = [s for s in self.servers if s._id != config_id]
        self.save()

    def get_by_id(self, config_id: str) -> ServerConfig | None:
        for s in self.servers:
            if s._id == config_id:
                return s
        return None

    def get_all(self) -> list[ServerConfig]:
        return self.servers

