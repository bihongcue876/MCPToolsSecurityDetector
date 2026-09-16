# 攻防检测模拟器：读取载荷库、组装参数、执行、判定、写日志
from dataclasses import fields
from typing import Any
from app_config import DEFAULT_PAYLOADS_PATH
from core.models import ServerConfig, ToolInfo, AttackPayload, AttackRecord
from core.clients import MCPClient
from core.utils import (
    safe_json_dumps, safe_json_loads,
    contains_prompt_injection, extract_urls, has_obfuscated_chars,
)
from data.records_io import RecordsIO


def load_payloads(path: str | None = None) -> list[AttackPayload]:
    """读取内置载荷库文件，转为 AttackPayload 列表；缺字段用默认值"""
    p = path or str(DEFAULT_PAYLOADS_PATH)
    try:
        with open(p, encoding="utf-8") as f:
            data = safe_json_loads(f.read()) or []
    except (OSError, IOError):
        return []
    names = {x.name for x in fields(AttackPayload)}
    return [AttackPayload(**{k: v for k, v in d.items() if k in names})
            for d in data if isinstance(d, dict)]


class AttackSimulator:
    """对单个目标工具执行一次受控攻防探测，观察响应并判定异常"""

    def __init__(self, client: MCPClient,
                 config: ServerConfig,
                 records: RecordsIO | None = None):
        self.client = client
        self.config = config
        self.records = records

    def list_tools(self) -> list[ToolInfo]:
        """返回当前连接的工具列表；未连接或失败时返回空"""
        if self.client is None or not self.client.connected:
            return []
        try:
            return self.client.list_tools()
        except Exception:
            return []

    def get_tool(self, name: str) -> ToolInfo | None:
        for t in self.list_tools():
            if t.name == name:
                return t
        return None

    # ---------- 载荷注入 ----------
    @staticmethod
    def inject(payload: AttackPayload, schema: dict) -> tuple[dict | None, str]:
        """把载荷注入工具参数；返回 (args, 说明)；不可测时可注入返回 (None, 原因)

        按设计文档规则：
        1. 优先替换工具的字符串参数；
        2. 无法精确替换时，追加到首个字符串字段；
        3. 全部失败则不可测。
        """
        text = payload.payload * max(1, payload.repeat)
        props = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        str_props = [k for k, v in props.items()
                     if isinstance(v, dict) and v.get("type") == "string"]
        if not str_props:
            return None, "工具没有字符串参数，无法注入载荷"
        # str_props 按需排序：必填优先
        str_props.sort(key=lambda k: (0 if k in required else 1, k))
        target = str_props[0]
        args = {k: "" for k in str_props}
        args[target] = text
        return args, f"载荷注入参数「{target}」"

    # ---------- 执行 ----------
    def execute(self, tool_name: str, payload: AttackPayload,
                schema: dict | None = None) -> dict:
        """执行一次攻防探测，返回结果字典（含请求/响应/判定/是否异常）"""
        tool = self.get_tool(tool_name)
        if tool is None:
            return self._outcome(payload, None, None,
                                 "工具不存在或未连接", abnormal=False)
        args, note = self.inject(payload, schema if schema is not None else tool.input_schema)
        if args is None:
            return self._outcome(payload, None, None, note, abnormal=False)
        try:
            response = self.client.call_tool(tool_name, args)
        except Exception as e:
            return self._outcome(payload, args, None, f"调用异常：{e}", abnormal=False)
        abnormal, judgement = self._judge(payload, response)
        self._log(tool_name, payload, args, response, judgement, abnormal)
        return self._outcome(payload, args, response, judgement, abnormal)

    def _judge(self, payload: AttackPayload, response: dict) -> tuple[bool, str]:
        """判定响应是否出现异常特征；返回 (是否异常, 判定说明)"""
        text = self._extract_text(response)
        hits = [f for f in payload.detect if f and f in text]
        reasons = []
        if hits:
            reasons.append(f"命中载荷特征：{', '.join(hits)}")
        if contains_prompt_injection(text):
            reasons.append("疑似提示注入")
        if has_obfuscated_chars(text):
            reasons.append("含混淆字符")
        if extract_urls(text):
            reasons.append("含外部链接")
        if reasons:
            return True, "检出异常响应：" + "；".join(reasons)
        return False, "无异常响应"

    @staticmethod
    def _extract_text(response: dict) -> str:
        """从工具响应中提取可判定的文本"""
        if not isinstance(response, dict):
            return str(response)
        content = response.get("content")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("text"):
                    parts.append(str(item["text"]))
            if parts:
                return "\n".join(parts)
        return safe_json_dumps(response)

    def _log(self, tool_name: str, payload: AttackPayload,
             args, response, judgement: str, abnormal: bool):
        """写入攻防日志；失败静默"""
        if self.records is None:
            return
        try:
            record = AttackRecord(
                server_id=self.config._id,
                server_name=self.config.name,
                tool_name=tool_name,
                payload_id=payload.id,
                payload_content=payload.payload,
                args_json=safe_json_dumps(args),
                response_json=safe_json_dumps(response),
            )
            self.records.write_attack(record)
        except Exception:
            pass

    @staticmethod
    def _outcome(payload: AttackPayload, args, response,
                 judgement: str, abnormal: bool) -> dict:
        return {
            "payload": payload,
            "args": args,
            "response": response,
            "judgement": judgement,
            "abnormal": abnormal,
        }