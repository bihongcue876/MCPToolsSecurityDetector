import json
from datetime import datetime
from pathlib import Path
from dataclasses import fields
from app_config import RECORD_DIR
from core.models import (
    BaseRecord, ToolCallRecord, AttackRecord,
    DetectionRun, DetectionResult,
)


class RecordsIO:
    def __init__(self, record_dir: Path = RECORD_DIR):
        self.record_dir = record_dir
        self.record_dir.mkdir(parents=True, exist_ok=True)
        self._seq = 0  # 同进程内序号，用于生成唯一 ID

    # ---------- 内部工具 ----------
    def _month_tag(self) -> str:
        return datetime.now().strftime("%Y_%m")

    def _path_for(self, prefix: str) -> Path:
        return self.record_dir / f"{prefix}_{self._month_tag()}.log"

    def _append_line(self, prefix: str, data: dict):
        """向指定前缀的当月文件追加一行 JSON"""
        path = self._path_for(prefix)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")

    def _read_lines(self, prefix: str, month: str | None = None) -> list[dict]:
        """读取某月文件，month 为 None 时读当月"""
        tag = month or self._month_tag()
        path = self.record_dir / f"{prefix}_{tag}.log"
        if not path.exists():
            return []
        records = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return records

    def _new_id(self) -> str:
        """生成唯一ID：毫秒时间戳 + 同进程序号"""
        self._seq += 1
        return f"{int(datetime.now().timestamp() * 1000)}{self._seq:04d}"

    def _prepare(self, record: BaseRecord):
        """补全基础字段（id、timestamp），幂等；只填空值不覆盖既有值"""
        if not record.id:
            record.id = self._new_id()
        if not record.timestamp:
            record.timestamp = datetime.now().isoformat()
        if isinstance(record, DetectionRun) and not record.run_time:
            record.run_time = record.timestamp

    # ---------- 写入 ----------
    def write_tool_call(self, record: ToolCallRecord):
        self._prepare(record)
        self._append_line("tool_call", record.__dict__)

    def write_attack(self, record: AttackRecord):
        self._prepare(record)
        self._append_line("attack", record.__dict__)

    def write_detection_run(self, run: DetectionRun):
        self._prepare(run)
        data = run.__dict__.copy()
        data["results"] = [r.__dict__ for r in run.results]
        self._append_line("detection", data)

    # ---------- 读取 ----------
    @staticmethod
    def _pick(obj: dict, cls):
        """按 dataclass 字段过滤行数据，兼容缺字段的旧行日志"""
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in obj.items() if k in names})

    def read_tool_calls(self, month: str | None = None) -> list[ToolCallRecord]:
        return [self._pick(d, ToolCallRecord)
                for d in self._read_lines("tool_call", month)]

    def read_attacks(self, month: str | None = None) -> list[AttackRecord]:
        return [self._pick(d, AttackRecord)
                for d in self._read_lines("attack", month)]

    def read_detection_runs(self, month: str | None = None) -> list[DetectionRun]:
        runs = []
        for d in self._read_lines("detection", month):
            results_data = d.pop("results", [])
            try:
                run = self._pick(d, DetectionRun)
            except TypeError:
                continue
            run.results = []
            for r in results_data:
                try:
                    run.results.append(DetectionResult(**r))
                except TypeError:
                    continue
            runs.append(run)
        return runs

    # ---------- 查询（带筛选，供日志工作区使用） ----------
    def _months_in_range(self, prefix: str,
                         start_month: str | None, end_month: str | None) -> list[str]:
        months = self.list_months(prefix)
        if start_month:
            months = [m for m in months if m >= start_month]
        if end_month:
            months = [m for m in months if m <= end_month]
        return months

    def query_tool_calls(self, server_id: str | None = None,
                         server_name: str | None = None,
                         tool_name: str | None = None,
                         start_month: str | None = None,
                         end_month: str | None = None) -> list[ToolCallRecord]:
        out = []
        for m in self._months_in_range("tool_call", start_month, end_month):
            for r in self.read_tool_calls(m):
                if server_id and r.server_id != server_id:
                    continue
                if server_name and r.server_name != server_name:
                    continue
                if tool_name and r.tool_name != tool_name:
                    continue
                out.append(r)
        return out

    def query_attacks(self, server_id: str | None = None,
                      server_name: str | None = None,
                      tool_name: str | None = None,
                      start_month: str | None = None,
                      end_month: str | None = None) -> list[AttackRecord]:
        out = []
        for m in self._months_in_range("attack", start_month, end_month):
            for r in self.read_attacks(m):
                if server_id and r.server_id != server_id:
                    continue
                if server_name and r.server_name != server_name:
                    continue
                if tool_name and r.tool_name != tool_name:
                    continue
                out.append(r)
        return out

    def query_detection_runs(self, server_id: str | None = None,
                             status: str | None = None,
                             start_month: str | None = None,
                             end_month: str | None = None) -> list[DetectionRun]:
        out = []
        for m in self._months_in_range("detection", start_month, end_month):
            for r in self.read_detection_runs(m):
                if server_id and r.server_id != server_id:
                    continue
                if status and not any(x.status == status for x in r.results):
                    continue
                out.append(r)
        return out

    def get_latest_detection_run(self, server_id: str) -> DetectionRun | None:
        """读取某服务器最近一次检测记录（从最新月份倒序查找）"""
        for m in reversed(self.list_months("detection")):
            for d in reversed(self._read_lines("detection", m)):
                if d.get("server_id") != server_id:
                    continue
                results_data = d.pop("results", [])
                try:
                    run = self._pick(d, DetectionRun)
                except TypeError:
                    continue
                run.results = [DetectionResult(**r) for r in results_data]
                return run
        return None

    # ---------- 管理 ----------
    def list_months(self, prefix: str) -> list[str]:
        """列出某前缀下所有存在的月份标签"""
        return sorted([
            p.stem.replace(f"{prefix}_", "")
            for p in self.record_dir.glob(f"{prefix}_*.log")
        ])

    def get_available_months(self, prefix: str | None = None) -> list[str]:
        """聚合所有记录类型（或指定类型）的可用月份，供日期下拉框使用"""
        prefixes = [prefix] if prefix else ["tool_call", "detection", "attack"]
        months: set[str] = set()
        for p in prefixes:
            months.update(self.list_months(p))
        return sorted(months)

    def delete_month(self, prefix: str, month: str) -> bool:
        path = self.record_dir / f"{prefix}_{month}.log"
        if path.exists():
            path.unlink()
            return True
        return False