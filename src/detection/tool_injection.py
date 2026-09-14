# B组工具与注入风险检测：B1-B4四个检测函数。每个函数返回一个DetectionResult，内部枚举所有分支
from core.models import ServerConfig, ToolInfo, DetectionResult
from core.clients import MCPClient
from core import utils

MODULE = "B" # 检测模式模块编号

# B2 一次最多实际调用的只读工具数量，避免慢工具拖垮整次检测
MAX_CALLS = 10

# 危险能力关键词库
DANGEROUS_WORDS = [
    "delete", "remove", "drop", "destroy", "kill", "shutdown",
    "exec", "execute", "run", "shell", "command", "eval", "system",
    "write", "put", "post", "upload", "create", "update", "insert",
]
# 只读特征关键词
READONLY_HINTS = ["get", "list", "read", "query", "fetch", "search", "view", "show", "find"]
# 删除类关键词
DELETE_WORDS = ["delete", "remove", "drop", "destroy", "clear", "purge"]


# ---------- B1工具元数据提示注入 ----------

def check_b1_metadata_injection(config: ServerConfig, client: MCPClient | None) -> DetectionResult:
    """B1检测：遍历工具名称、描述、参数说明，检测提示注入特征"""
    tools = _safe_list_tools(client)
    if tools is None:
        return _result("B1", "工具元数据提示注入", "warn", "未连接或无法获取工具列表", "建议先完成连接")
    if not tools:
        return _result("B1", "工具元数据提示注入", "skip", "服务器未提供工具", "无工具可检测")
    hits = []       # 决定性可疑特征（注入指令/混淆字符），命中即 fail
    url_warns = []  # 仅含URL的提示（可能只是文档链接），命中记为 warn
    for t in tools:
        if utils.contains_prompt_injection(t.name or ""):
            hits.append(f"工具名[{t.name}]命中注入关键词")
        desc = t.description or ""
        if utils.contains_prompt_injection(desc):
            hits.append(f"工具[{t.name}]描述命中注入关键词")
        if utils.has_obfuscated_chars(desc):
            hits.append(f"工具[{t.name}]描述含零宽或混淆字符")
        urls = utils.extract_urls(desc)
        if urls:
            url_warns.append(f"工具[{t.name}]描述含URL：{urls[0][:50]}")
        props = (t.input_schema or {}).get("properties", {}) if isinstance(t.input_schema, dict) else {}
        for pname, pdef in props.items():
            if not isinstance(pdef, dict):
                continue
            pdesc = pdef.get("description", "") or ""
            if utils.contains_prompt_injection(pdesc):
                hits.append(f"工具[{t.name}]参数[{pname}]说明命中注入关键词")
    if hits:
        preview = "；".join(hits[:5])
        if len(hits) > 5:
            preview += f"；……共{len(hits)}条"
        return _result("B1", "工具元数据提示注入", "fail", preview, "建议清理工具名称、描述、参数说明中的指令性语句、混淆字符和外部链接")
    if url_warns:
        preview = "；".join(url_warns[:5])
        if len(url_warns) > 5:
            preview += f"；……共{len(url_warns)}条"
        return _result("B1", "工具元数据提示注入", "warn", preview, "含URL不一定是风险，请人工确认链接是否指向信任站点")
    return _result("B1", "工具元数据提示注入", "pass", f"已检查{len(tools)}个工具，未发现可疑元数据", "保持工具描述简洁，避免指令性语句")


# ---------- B2工具结果响应注入 ----------

def check_b2_result_injection(config: ServerConfig, client: MCPClient | None) -> DetectionResult:
    """B2检测：对只读工具进行无害调用，检查响应是否含诱导内容"""
    tools = _safe_list_tools(client)
    if tools is None:
        return _result("B2", "工具结果响应注入", "warn", "未连接或无法获取工具列表", "建议先完成连接")
    if not tools:
        return _result("B2", "工具结果响应注入", "skip", "服务器未提供工具", "无工具可检测")
    readonly = [t for t in tools if _is_readonly(t)]
    if not readonly:
        return _result("B2", "工具结果响应注入", "skip", f"共有{len(tools)}个工具，但无只读工具可安全调用", "手动挑选工具进行测试")
    hits = []       # 命中注入特征的工具
    errors = []     # 调用失败的工具
    empty_msgs = [] # 响应内容为空的工具，单独留意以免误判
    called = 0
    total = min(len(readonly), MAX_CALLS)  # 实际尝试调用的数量（受上限约束）
    skipped = len(readonly) - total        # 因上限未调用的数量
    if client is None:
        return _result("B2", "工具结果响应注入", "warn", "未连接或无法获取工具列表", "建议先完成连接")
    for t in readonly[:MAX_CALLS]:
        args = _build_safe_args(t.input_schema)
        try:
            resp = client.call_tool(t.name, args)
            called += 1
        except Exception as e:
            errors.append(f"{t.name}：{str(e)[:60]}")
            continue
        text = _extract_text(resp)
        if utils.contains_prompt_injection(text):
            hits.append(f"工具[{t.name}]响应命中注入关键词")
        urls = utils.extract_urls(text)
        if urls:
            hits.append(f"工具[{t.name}]响应含URL：{urls[0][:50]}")
        if not text.strip():
            empty_msgs.append(t.name)
    if hits:
        preview = "；".join(hits[:5])
        if len(hits) > 5:
            preview += f"；……共{len(hits)}条"
        if empty_msgs:
            preview += f"（另有{len(empty_msgs)}个工具响应为空）"
        return _result("B2", "工具结果响应注入", "fail", preview, "建议对工具响应文本进行内容过滤或标记可疑片段")
    if called == 0:
        detail = "；".join(errors[:3]) if errors else "无可用调用"
        return _result("B2", "工具结果响应注入", "warn", f"共{total}个只读工具均调用失败：{detail}", "检查工具参数或服务器状态")
    # 部分调用失败：不能当作全部成功，明确报告成功/失败数量
    if errors:
        evidence = f"成功调用{called}个，失败{len(errors)}个：{('；'.join(errors[:3]))}"
        if skipped:
            evidence += f"；另有{skipped}个只读工具因数量上限未调用"
        return _result("B2", "工具结果响应注入", "warn", evidence, "请检查调用失败的工具参数或服务器状态")
    # 全部成功但响应均为空：无法据此判断注入，按 warn 提示人工复核
    if empty_msgs and len(empty_msgs) == called:
        return _result("B2", "工具结果响应注入", "warn", f"已调用{called}个只读工具但响应内容均为空，无法判断", "请确认工具确有返回内容后再复测")
    extra = ""
    if empty_msgs:
        extra += f"；其中{len(empty_msgs)}个响应为空，仅供参考"
    if skipped:
        extra += f"；另有{skipped}个只读工具因数量上限未调用"
    return _result("B2", "工具结果响应注入", "pass", f"已安全调用{called}个只读工具，未发现响应注入{extra}", "保持响应内容规范")


# ---------- B3参数Schema约束不足 ----------

def check_b3_schema_constraints(config: ServerConfig, client: MCPClient | None) -> DetectionResult:
    """B3检测：遍历工具input_schema，检查约束是否完整"""
    tools = _safe_list_tools(client)
    if tools is None:
        return _result("B3", "参数Schema约束不足", "warn", "未连接或无法获取工具列表", "建议先完成连接")
    if not tools:
        return _result("B3", "参数Schema约束不足", "skip", "服务器未提供工具", "无工具可检测")
    issues = []
    for t in tools:
        schema = t.input_schema or {}
        if not isinstance(schema, dict):
            issues.append(f"工具[{t.name}]input_schema非字典")
            continue
        if schema.get("additionalProperties") is True:
            issues.append(f"工具[{t.name}]允许额外属性")
        props = schema.get("properties", {}) if isinstance(schema.get("properties"), dict) else {}
        # 只有确实声明了属性时才要求 required：参数全可选时服务器本就不写 required 字段
        if props and "required" not in schema:
            issues.append(f"工具[{t.name}]声明了{len(props)}个属性但缺少required字段")
        for pname, pdef in props.items():
            if not isinstance(pdef, dict):
                continue
            if pdef.get("type") != "string":
                continue
            has_max = "maxLength" in pdef
            has_pattern = "pattern" in pdef
            has_enum = "enum" in pdef
            if not (has_max or has_pattern or has_enum):
                issues.append(f"工具[{t.name}]参数[{pname}]字符串无任何约束")
            elif not has_max:
                issues.append(f"工具[{t.name}]参数[{pname}]字符串缺少maxLength")
    if not issues:
        return _result("B3", "参数Schema约束不足", "pass", f"已检查{len(tools)}个工具的Schema，约束完整", "保持参数约束规范")
    preview = "；".join(issues[:5])
    if len(issues) > 5:
        preview += f"；……共{len(issues)}条"
    return _result("B3", "参数Schema约束不足", "warn", preview, "建议为字符串参数添加maxLength、pattern或enum约束，为对象添加required声明")


# ---------- B4危险能力声明不一致 ----------

def check_b4_capability_consistency(config: ServerConfig, client: MCPClient | None) -> DetectionResult:
    """B4检测：对比工具能力声明与实际名称描述是否矛盾"""
    tools = _safe_list_tools(client)
    if tools is None:
        return _result("B4", "危险能力声明不一致", "warn", "未连接或无法获取工具列表", "建议先完成连接")
    if not tools:
        return _result("B4", "危险能力声明不一致", "skip", "服务器未提供工具", "无工具可检测")
    issues = []
    for t in tools:
        ann = t.annotations or {}
        name_low = (t.name or "").lower()
        desc_low = (t.description or "").lower()
        read_only = ann.get("readOnlyHint")
        destructive = ann.get("destructiveHint")
        if _as_bool(read_only):
            hit_name = [w for w in DANGEROUS_WORDS if w in name_low]
            hit_desc = [w for w in DANGEROUS_WORDS if w in desc_low]
            if hit_name:
                issues.append(f"工具[{t.name}]声明只读但名称含危险词：{hit_name[0]}")
            if hit_desc:
                issues.append(f"工具[{t.name}]声明只读但描述含危险词：{hit_desc[0]}")
        if destructive is not None and not _as_bool(destructive):
            hit = [w for w in DELETE_WORDS if w in name_low or w in desc_low]
            if hit:
                issues.append(f"工具[{t.name}]声明非破坏但含删除类词：{hit[0]}")
        if read_only is None:
            for hint in READONLY_HINTS:
                if name_low.startswith(hint):
                    issues.append(f"工具[{t.name}]名称暗示只读但未声明readOnlyHint")
                    break
    if not issues:
        return _result("B4", "危险能力声明不一致", "pass", f"已检查{len(tools)}个工具，声明与命名一致", "保持能力声明与工具行为一致")
    preview = "；".join(issues[:5])
    if len(issues) > 5:
        preview += f"；……共{len(issues)}条"
    return _result("B4", "危险能力声明不一致", "fail", preview, "建议修正工具的能力声明，或调整名称与描述与实际行为一致")


# ---------- 内部工具 ----------

def _as_bool(value) -> bool:
    """宽松布尔判定：部分服务器以字符串/数字返回注解，统一视为布尔"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return False


def _safe_list_tools(client: MCPClient | None) -> list[ToolInfo] | None:
    """安全获取工具列表，未连接或异常时返回None"""
    if client is None or not client.connected:
        return None
    try:
        return client.list_tools()
    except Exception:
        return None


def _is_readonly(tool: ToolInfo) -> bool:
    """判断工具是否为只读：优先看annotations，无注解时按名称推断"""
    ann = tool.annotations or {}
    if ann.get("readOnlyHint") is True:
        return True
    if ann.get("destructiveHint") is True:
        return False
    name_low = (tool.name or "").lower()
    for hint in READONLY_HINTS:
        if name_low.startswith(hint) or f"_{hint}" in name_low or f"-{hint}" in name_low:
            return True
    return False


def _build_safe_args(schema) -> dict:
    """根据schema生成保守的空参数，只填必填字段"""
    if not isinstance(schema, dict):
        return {}
    required = schema.get("required", [])
    props = schema.get("properties", {}) if isinstance(schema.get("properties"), dict) else {}
    args = {}
    for key in required:
        if not isinstance(key, str):
            continue
        pdef = props.get(key, {})
        if not isinstance(pdef, dict):
            continue
        if "default" in pdef:
            args[key] = pdef["default"]
            continue
        ptype = pdef.get("type", "string")
        if ptype == "string":
            args[key] = ""
        elif ptype == "integer":
            args[key] = 0
        elif ptype == "number":
            args[key] = 0.0
        elif ptype == "boolean":
            args[key] = False
        elif ptype == "array":
            args[key] = []
        elif ptype == "object":
            args[key] = {}
        else:
            args[key] = ""
    return args


def _extract_text(resp) -> str:
    """从MCP工具响应中提取文本内容"""
    if not isinstance(resp, dict):
        return str(resp)
    parts = []
    content = resp.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
    if not parts:
        try:
            import json
            return json.dumps(resp, ensure_ascii=False)
        except Exception:
            return str(resp)
    return "\n".join(parts)


def _result(item_id: str, item_name: str, status: str, evidence: str, suggestion: str) -> DetectionResult:
    """统一构造DetectionResult"""
    return DetectionResult(module=MODULE, item_id=item_id, item_name=item_name, status=status, evidence=evidence, suggestion=suggestion)