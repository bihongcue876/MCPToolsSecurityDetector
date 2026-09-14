# 检测引擎：注册表 + 分发 + 记录
from collections.abc import Callable
from core.models import ServerConfig, DetectionResult, DetectionRun
from core.clients import MCPClient
from data.records_io import RecordsIO
from detection import transport_auth, tool_injection


# 注册表：{编号: (显示名, 检测函数, 是否需要客户端)}
CHECK_REGISTRY: dict[str, tuple[str, Callable, bool]] = {
    "A1": ("TLS/明文传输", transport_auth.check_a1_tls, False),
    "A2": ("匿名访问", transport_auth.check_a2_anonymous, False),
    "A3": ("硬编码凭证", transport_auth.check_a3_credentials, False),
    "A4": ("协议握手与错误处理", transport_auth.check_a4_handshake, True),
    "B1": ("工具元数据提示注入", tool_injection.check_b1_metadata_injection, True),
    "B2": ("工具结果响应注入", tool_injection.check_b2_result_injection, True),
    "B3": ("参数Schema约束不足", tool_injection.check_b3_schema_constraints, True),
    "B4": ("危险能力声明不一致", tool_injection.check_b4_capability_consistency, True),
}


def run(checks: list[str], config: ServerConfig, client: MCPClient | None = None) -> list[DetectionResult]:
    """按编号逐个执行检测，异常降级为warn，不中断整体"""
    results: list[DetectionResult] = []
    for cid in checks:
        entry = CHECK_REGISTRY.get(cid)
        if entry is None:
            continue
        name, fn, needs_client = entry
        try:
            r = fn(config, client) if needs_client else fn(config)
        except Exception as e:
            r = DetectionResult(module=cid[0], item_id=cid, item_name=name, status="warn", evidence=f"检测异常：{e}", suggestion="人工复查该检测项")
        results.append(r)
    return results


def run_and_record(checks: list[str], config: ServerConfig, client: MCPClient | None, records: RecordsIO) -> list[DetectionResult]:
    """执行检测并写入记录"""
    results = run(checks, config, client)
    run_record = DetectionRun(server_id=config._id, server_name=config.name, results=results)
    try:
        records.write_detection_run(run_record)
    except Exception:
        pass
    return results