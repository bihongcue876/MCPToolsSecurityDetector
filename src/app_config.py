from pathlib import Path
import json
from datetime import datetime
# 文件路径、信息管理、默认参数
APP_NAME = "mcp-security-detector"
VERSION = "0.0.0"
# base dir and other dir
BASE_DIR = Path(__file__).resolve().parent.parent
# data
DATA_DIR = BASE_DIR / "data"
# default
SETTINGS_PATH = DATA_DIR / "settings.json"
SERVERS_CFG_PATH = DATA_DIR / "servers.json"
DEFAULT_LOGS_PATH = DATA_DIR / "logs.log"
USER_PAYLOADS_PATH = DATA_DIR / "payloads.json" # 进攻荷载或自定义资源
RECORD_DIR = DATA_DIR / "record"
# resources
RESOURCES_DIR = BASE_DIR / "src" / "resources"
DEFAULT_PAYLOADS_PATH = RESOURCES_DIR / "default_payloads.json"
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
    # user_payloads.json default
    if not USER_PAYLOADS_PATH.exists():
        USER_PAYLOADS_PATH.write_text("[]", encoding="utf-8")
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