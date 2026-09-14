# 检测引擎：注册表+分发+记录
from core.models import ServerConfig, DetectionResult, DetectionRun
from core.clients import MCPClient
from data.records_io import RecordsIO
from detection import transport_auth
from typing import Callable


# 总体表单：{编号: (显示名, 检测函数, 是否需要客户端)}
CHECK_REGISTRY: dict[str, tuple[str, Callable, bool]] = {
    "A1": ("TLS/明文传输", transport_auth.check_a1_tls, False),
    "A2": ("匿名访问", transport_auth.check_a2_anonymous, False),
    "A3": ("硬编码凭证", transport_auth.check_a3_credentials, False),
    "A4": ("协议握手与错误处理", transport_auth.check_a4_handshake, True),
}

def run(checks: list[str], config: ServerConfig,
        client: MCPClient | None = None) -> list[DetectionResult]:
    """按编号逐个执行检测，异常降级为warn，不中断整体"""
    results: list[DetectionResult] = []
    for cid in checks:
        entry = CHECK_REGISTRY.get(cid)
        if entry is None:
            continue
        name, fn, needs_client = entry # 解包
        try:
            if needs_client:
                r = fn(config, client)
            else:
                r = fn(config)
        except Exception as e:
            r = DetectionResult(
                module=cid[0], item_id=cid, item_name=name,
                status="warn", evidence=f"检测异常：{e}",
                suggestion="人工复查该检测项",
            )
        results.append(r)
    return results


def run_and_record(checks: list[str], config: ServerConfig,
                   client: MCPClient | None,
                   records: RecordsIO) -> list[DetectionResult]:
    """执行检测并写入记录"""
    results = run(checks, config, client)
    run_record = DetectionRun(
        server_id=config._id,
        server_name=config.name,
        results=results,
    )
    try:
        records.write_detection_run(run_record)
    except Exception:
        pass  # 记录失败不阻断主流程
    return results