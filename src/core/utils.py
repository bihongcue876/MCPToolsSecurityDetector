# 通用工具
import re
import json
import unicodedata

from typing import Any


# ---------- JSON 处理 ----------
def safe_json_dumps(obj: Any, indent: int = 2) -> str:
    """安全序列化对象为JSON字符串，保留中文，失败时返回可读错误"""
    try:
        return json.dumps(obj, indent=indent, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        return f"<序列化失败: {e}>"


def safe_json_loads(text: str) -> Any | None:
    """安全反序列化JSON字符串，失败返回None"""
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


# ---------- 文本处理（GUI 辅助） ----------
def truncate(text: str, max_len: int = 80) -> str:
    """截断超长文本，用于表格或列表摘要显示"""
    if not text:
        return ""
    return text if len(text) <= max_len else text[:max_len] + "..."


# ---------- 基础安全检测逻辑（供后续检测模块调用） ----------
# 凭证匹配正则（预先编译以提升性能）
SECRET_PATTERNS = [
    re.compile(r"(?i)bearer\s+[a-z0-9\-_\.]+"),                 # Bearer Token
    re.compile(r"(?i)api[_-]?key[\"'\s:=]+[a-z0-9\-_]{8,}"),    # API Key
    re.compile(r"(?i)password[\"'\s:=]+\S+"),                   # Password
    re.compile(r"(?i)token[\"'\s:=]+[a-z0-9\-_\.]{8,}"),        # Token
]


def has_hardcoded_secret(text: str) -> bool:
    """检测文本中是否疑似包含明文凭证"""
    if not text:
        return False
    return any(p.search(text) for p in SECRET_PATTERNS)


# 提示注入关键词库（可后续按需扩充）
INJECTION_KEYWORDS = [
    "忽略之前", "忽略以上", "ignore previous", "ignore above",
    "system prompt", "系统提示", "不要告诉用户",
    "以管理员身份", "act as", "jailbreak",
]


def contains_prompt_injection(text: str) -> bool:
    """检测文本中是否包含提示注入特征"""
    if not text:
        return False
    lower_text = text.lower()
    return any(kw.lower() in lower_text for kw in INJECTION_KEYWORDS)


def has_obfuscated_chars(text: str) -> bool:
    """检测文本是否包含零宽字符、双向控制符等常见混淆字符"""
    if not text:
        return False
    return any(unicodedata.category(ch) == "Cf" for ch in text)


# URL 提取（用于工具描述中的可疑链接检测）
URL_PATTERN = re.compile(r"https?://[^\s\"']+")


def extract_urls(text: str) -> list[str]:
    """提取文本中所有 HTTP/HTTPS 链接"""
    return URL_PATTERN.findall(text or "")