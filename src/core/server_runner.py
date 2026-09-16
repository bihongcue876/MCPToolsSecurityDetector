# 示范服务器进程管理：命令解析、以独立可见终端启动、停止与存活监测
import json
import os
import shutil
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from app_config import BASE_DIR, DATA_DIR, DEMO_SERVER_FLAG, DEMO_SERVERS_PATH, FROZEN

try:
    import psutil
except ImportError:  # 缺少psutil时回退到taskkill/信号
    psutil = None

# Windows：为新进程创建独立控制台窗口（即“可见系统终端”）
CREATE_NEW_CONSOLE = 0x00000010
# 运行中服务器的持久化记录
RUNNING_PATH = DATA_DIR / "running_servers.json"


def resolve_command(command: str) -> str | None:
    """把配置中的命令解析为可直接启动的完整路径

    开发态下解释器类命令优先使用当前进程解释器（本项目依赖均装在当前环境）；
    打包态下当前进程是 exe，不能充当解释器，改为从 PATH 里寻找独立 Python。
    其余命令一律按 PATH 解析。
    """
    if not command:
        return None
    if os.path.isabs(command):
        return command
    base = os.path.basename(command).lower()
    if base in ("python", "pythonw", "python3", "pythonw3", "py"):
        if not FROZEN:
            return sys.executable
        for name in ("python", "python3", "py"):
            found = shutil.which(name)
            if found:
                return found
        return None
    return shutil.which(command)


def load_demo_servers() -> list[dict]:
    """读取示范服务器清单，文件缺失或损坏时返回空列表"""
    try:
        data = json.loads(DEMO_SERVERS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    servers = data.get("servers") if isinstance(data, dict) else None
    if not isinstance(servers, list):
        return []
    return [s for s in servers if isinstance(s, dict) and s.get("id")]


def _terminate_tree(pid: int) -> None:
    """终止进程及其子进程（优先psutil，回退taskkill/信号）"""
    if psutil is not None:
        try:
            parent = psutil.Process(pid)
            victims = parent.children(recursive=True)
            victims.append(parent)
            for proc in victims:
                try:
                    proc.terminate()
                except psutil.Error:
                    pass
            _, alive = psutil.wait_procs(victims, timeout=3)
            for proc in alive:
                try:
                    proc.kill()
                except psutil.Error:
                    pass
            return
        except psutil.Error:
            pass
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def _pid_alive(pid: int) -> bool:
    """判断pid是否仍存活"""
    if psutil is not None:
        try:
            return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
        except psutil.Error:
            return False
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True
        )
        return str(pid) in (result.stdout or "")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _pid_matches(pid: int, run_key: str) -> bool:
    """校验存活的pid确实由该脚本启动，避免pid被复用后误认（无psutil时不做校验）"""
    if psutil is None:
        return True
    name = os.path.basename(run_key)
    try:
        cmdline = psutil.Process(pid).cmdline()
    except psutil.Error:
        return False
    return bool(name) and name in " ".join(cmdline)


class ServerProcessManager:
    """示范服务器子进程管理：按运行键共享进程、持久化、退出时统一回收"""

    def __init__(self, servers: list[dict] | None = None):
        self.servers = servers if servers is not None else load_demo_servers()
        self._pids: dict[str, int] = {}
        self._started_at: dict[str, str] = {}
        self._load_running()

    # ---------- 查询 ----------
    def get(self, server_id: str) -> dict | None:
        for server in self.servers:
            if server.get("id") == server_id:
                return server
        return None

    def run_key(self, server_id: str) -> str:
        """运行键：同一脚本的多个条目共享同一进程，启动一次即全部可用"""
        server = self.get(server_id) or {}
        return str(server.get("run_key") or server.get("script") or server_id)

    def is_running(self, server_id: str) -> bool:
        key = self.run_key(server_id)
        pid = self._pids.get(key)
        if pid is None:
            return False
        if _pid_alive(pid):
            return True
        self._forget(key)
        return False

    def pid(self, server_id: str) -> int | None:
        key = self.run_key(server_id)
        pid = self._pids.get(key)
        return pid if pid is not None and _pid_alive(pid) else None

    def started_at(self, server_id: str) -> str:
        return self._started_at.get(self.run_key(server_id), "")

    def shared_count(self, server_id: str) -> int:
        """与该条目共享同一进程的条目数量"""
        key = self.run_key(server_id)
        return sum(1 for s in self.servers if self.run_key(str(s.get("id"))) == key)

    # ---------- 启动/停止 ----------
    def start(self, server_id: str) -> tuple[bool, str]:
        """以独立可见终端启动服务器；同一运行键已在运行时直接返回成功"""
        server = self.get(server_id)
        if server is None:
            return False, "未找到该示范服务器"
        key = self.run_key(server_id)
        if self.is_running(server_id):
            return True, "该服务器已在运行"
        script = str(server.get("script") or "")
        if not script:
            return False, "该条目缺少启动脚本"
        script_path = Path(script)
        if not script_path.is_absolute():
            script_path = BASE_DIR / script_path
        if not script_path.exists():
            return False, f"启动脚本不存在：{script_path}"
        extra_args = [str(a) for a in (server.get("args") or [])]
        if FROZEN:
            # 打包态由 exe 自兼任服务器宿主，用自带解释器运行随包脚本，无需外部 Python
            cmd = [sys.executable, DEMO_SERVER_FLAG, str(script_path)] + extra_args
        else:
            command = resolve_command(str(server.get("command") or "python"))
            if not command:
                return False, f"无法解析命令：{server.get('command')}"
            cmd = [command, str(script_path)] + extra_args
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        creationflags = CREATE_NEW_CONSOLE if os.name == "nt" else 0
        try:
            proc = subprocess.Popen(
                cmd, cwd=str(BASE_DIR), env=env, creationflags=creationflags
            )
        except (OSError, ValueError) as e:
            return False, f"启动失败：{e}"
        self._pids[key] = proc.pid
        self._started_at[key] = datetime.now().isoformat(timespec="seconds")
        self._save_running()
        return True, f"已在新的终端窗口启动：{server.get('name') or server_id}"

    def stop(self, server_id: str) -> tuple[bool, str]:
        key = self.run_key(server_id)
        pid = self._pids.get(key)
        if pid is None or not _pid_alive(pid):
            self._forget(key)
            return False, "该服务器未在运行"
        _terminate_tree(pid)
        self._forget(key)
        return True, "已停止"

    def stop_all(self) -> int:
        """停止全部运行中的示范服务器，返回成功停止的数量"""
        count = 0
        for key in list(self._pids.keys()):
            pid = self._pids.get(key)
            if pid is None or not _pid_alive(pid):
                self._forget(key)
                continue
            _terminate_tree(pid)
            self._forget(key)
            count += 1
        return count

    def refresh(self, server_id: str) -> bool:
        """复核存活状态，进程已退出则清理，返回是否仍在运行"""
        return self.is_running(server_id)

    # ---------- 内部 ----------
    def _forget(self, key: str) -> None:
        self._pids.pop(key, None)
        self._started_at.pop(key, None)
        self._save_running()

    def _save_running(self) -> None:
        data = [
            {"run_key": key, "pid": pid, "started_at": self._started_at.get(key, "")}
            for key, pid in self._pids.items()
        ]
        try:
            RUNNING_PATH.parent.mkdir(parents=True, exist_ok=True)
            RUNNING_PATH.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass

    def _load_running(self) -> None:
        """恢复上次未正常退出的服务器记录，仅保留仍存活的进程"""
        try:
            data = json.loads(RUNNING_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, list):
            return
        for item in data:
            if not isinstance(item, dict):
                continue
            key = str(item.get("run_key") or "")
            pid = item.get("pid")
            if not key or not isinstance(pid, int):
                continue
            if _pid_alive(pid) and _pid_matches(pid, key):
                self._pids[key] = pid
                self._started_at[key] = str(item.get("started_at") or "")
        self._save_running()