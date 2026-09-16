from pathlib import Path
import json
import sys
from datetime import datetime
# 文件路径、信息管理、默认参数
APP_NAME = "mcp-security-detector"
VERSION = "0.1.0"
# 打包态下 exe 自兼任示范服务器宿主时使用的命令行开关
DEMO_SERVER_FLAG = "--run-demo-server"
# 是否冻结(打包)运行态：源码与资源在 _MEIPASS 临时解压目录，数据放在可执行文件同级
FROZEN = bool(getattr(sys, "frozen", False))
# 资源根：开发态为项目根 src 的上层，打包态为 _MEIPASS
_BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", "")).resolve()
BASE_DIR = _BUNDLE_ROOT if FROZEN else Path(__file__).resolve().parent.parent
# 数据目录：开发态位于项目根 data，打包态位于可执行文件同级 data
if FROZEN:
    DATA_DIR = Path(sys.executable).resolve().parent / "data"
else:
    DATA_DIR = BASE_DIR / "data"
# default
SETTINGS_PATH = DATA_DIR / "settings.json"
SERVERS_CFG_PATH = DATA_DIR / "servers.json"
DEFAULT_LOGS_PATH = DATA_DIR / "logs.log"
RECORD_DIR = DATA_DIR / "record"
# resources（相对 BASE_DIR 的 src/resource 层级保持一致）
RESOURCES_DIR = BASE_DIR / "src" / "resources"
DEFAULT_PAYLOADS_PATH = RESOURCES_DIR / "default-payloads.json"
DEMO_SERVERS_PATH = RESOURCES_DIR / "demo-servers.json"
# 应用图标
ICON_PATH = BASE_DIR / "src" / "feature" / "icon.ico"
# default params
DEFAULT_TIMEOUT = 10
MAX_LOG_LINES = 100

def ensure_directories():
    """当默认文件不存在时，创建默认空文件"""
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    RECORD_DIR.mkdir(parents=True,exist_ok=True)
    # setting.json default
    if not SETTINGS_PATH.exists():
        default_settings = {
            "timeout":DEFAULT_TIMEOUT,
            "max_log_lines": MAX_LOG_LINES
        }
        SETTINGS_PATH.write_text(json.dumps(default_settings,indent=2),encoding="utf-8")
    # servers.json default
    if not SERVERS_CFG_PATH.exists():
        SERVERS_CFG_PATH.write_text("[]",encoding="utf-8")   
    # logs default
    if not DEFAULT_LOGS_PATH.exists():
        DEFAULT_LOGS_PATH.touch() 
        
def ensure_record_files():
    """记录文件检查"""
    month = datetime.now().strftime("%Y_%m")
    RECORD_DIR.mkdir(parents=True, exist_ok=True)
    toolcall_path = RECORD_DIR / f"tool_call_{month}.log"
    detect_path = RECORD_DIR / f"detection_{month}.log"
    toolcall_path.touch(exist_ok=True)
    detect_path.touch(exist_ok=True)
    return toolcall_path, detect_path

def resolve_project_path(p: str) -> str:
    """对于内置MCP服务器，把相对路径解析为基于项目根的绝对路径；绝对路径原样返回"""
    if not p:
        return p
    path = Path(p)
    if path.is_absolute():
        return str(path)
    return str(BASE_DIR / path)

def load_settings() -> dict:
    """读取全局设置；文件缺失或损坏时回退到默认值并补写默认文件"""
    ensure_directories()
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    default = {
        "timeout": DEFAULT_TIMEOUT,
        "max_log_lines": MAX_LOG_LINES,
    }
    merged = {**default, **{k: v for k, v in (data or {}).items() if k in default}}
    return merged

def save_settings(settings: dict) -> None:
    """写回全局设置（仅保留已知键）"""
    allowed = {"timeout", "max_log_lines"}
    data = {k: v for k, v in settings.items() if k in allowed}
    ensure_directories()
    SETTINGS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")