import json
from datetime import datetime
from pathlib import Path
from app_config import RECORD_DIR
from core.models import ToolCallRecord, DetectionRun, DetectionResult


class RecordsIO:
    def __init__(self, record_dir: Path = RECORD_DIR):
        self.record_dir = record_dir
        self.record_dir.mkdir(parents=True, exist_ok=True)

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

    # ---------- 写入 ----------
    def write_tool_call(self, record: ToolCallRecord):
        record.timestamp = record.timestamp or datetime.now().isoformat()
        self._append_line("tool_call", record.__dict__)

    def write_detection_run(self, run: DetectionRun):
        run.run_time = run.run_time or datetime.now().isoformat()
        data = run.__dict__.copy()
        data["results"] = [r.__dict__ for r in run.results]
        self._append_line("detection", data)

    def write_attack(self, record: ToolCallRecord):
        record.timestamp = record.timestamp or datetime.now().isoformat()
        self._append_line("attack", record.__dict__)

    # ---------- 读取 ----------
    def read_tool_calls(self, month: str | None = None) -> list[ToolCallRecord]:
        return [ToolCallRecord(**d) for d in self._read_lines("tool_call", month)]

    def read_detection_runs(self, month: str | None = None) -> list[DetectionRun]:
        runs = []
        for d in self._read_lines("detection", month):
            results_data = d.pop("results", [])
            run = DetectionRun(**d)
            run.results = [DetectionResult(**r) for r in results_data]
            runs.append(run)
        return runs

    def read_attacks(self, month: str | None = None) -> list[ToolCallRecord]:
        return [ToolCallRecord(**d) for d in self._read_lines("attack", month)]
    
    def get_latest_detection_run(self, server_id: str) -> DetectionRun | None:
        """读取某服务器最近一次检测记录（从最新月份倒序查找）"""
        months = self.list_months("detection")
        for m in reversed(months):
            records = self._read_lines("detection", m)
            for d in reversed(records):
                if d.get("server_id") != server_id:
                    continue
                results_data = d.pop("results", [])
                run = DetectionRun(**d)
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

    def delete_month(self, prefix: str, month: str) -> bool:
        path = self.record_dir / f"{prefix}_{month}.log"
        if path.exists():
            path.unlink()
            return True
        return False