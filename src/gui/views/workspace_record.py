# 工作区三：日志记录
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QPlainTextEdit,
)
from PySide6.QtCore import Qt
from data.records_io import RecordsIO

ALL = "全部"
STATUS_MAP = {"全部": None, "通过": "pass", "警告": "warn", "失败": "fail", "跳过": "skip"}


class WorkspaceRecord(QWidget):
    """工作区三：日志记录"""

    def __init__(self, records: RecordsIO):
        super().__init__()
        self.records = records
        self._rows: list[dict] = []
        self._setup_ui()
        self._reload_months()
        self._refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("日志项目："))
        self.category_combo = QComboBox()
        self.category_combo.addItems(["工具调用", "检测记录", "攻防记录"])
        self.category_combo.currentIndexChanged.connect(self._refresh)
        top.addWidget(self.category_combo)

        top.addWidget(QLabel("起始月份："))
        self.start_month_combo = QComboBox()
        self.start_month_combo.currentIndexChanged.connect(self._refresh)
        top.addWidget(self.start_month_combo)

        top.addWidget(QLabel("结束月份："))
        self.end_month_combo = QComboBox()
        self.end_month_combo.currentIndexChanged.connect(self._refresh)
        top.addWidget(self.end_month_combo)

        top.addWidget(QLabel("类型："))
        self.kind_combo = QComboBox()
        self.kind_combo.addItems(list(STATUS_MAP))
        self.kind_combo.currentIndexChanged.connect(self._refresh)
        top.addWidget(self.kind_combo)
        top.addStretch()
        layout.addLayout(top)

        self.table = QTableWidget()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.itemSelectionChanged.connect(self._show_detail)
        layout.addWidget(self.table)

        layout.addWidget(QLabel("详情："))
        self.detail_view = QPlainTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setMaximumHeight(160)
        layout.addWidget(self.detail_view)

    def _reload_months(self):
        months = self.records.get_available_months()
        values = [ALL] + months
        for combo in (self.start_month_combo, self.end_month_combo):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(values)
            combo.setCurrentIndex(len(values) - 1 if combo is self.end_month_combo else 0)
            combo.blockSignals(False)
        self._refresh()

    def _month(self, combo: QComboBox) -> str | None:
        text = combo.currentText()
        return None if text == ALL else text

    def _query(self):
        start = self._month(self.start_month_combo)
        end = self._month(self.end_month_combo)
        category = self.category_combo.currentText()
        if category == "工具调用":
            records = self.records.query_tool_calls(start_month=start, end_month=end)
            return records, ["时间", "ID", "服务器", "工具", "参数", "响应"], lambda r: {
                "时间": r.timestamp, "ID": r.id, "服务器": r.server_name,
                "工具": r.tool_name, "参数": r.args_json, "响应": r.response_json}
        if category == "攻防记录":
            records = self.records.query_attacks(start_month=start, end_month=end)
            return records, ["时间", "ID", "服务器", "工具", "载荷", "响应"], lambda r: {
                "时间": r.timestamp, "ID": r.id, "服务器": r.server_name,
                "工具": r.tool_name, "载荷": r.payload_content, "响应": r.response_json}
        status = STATUS_MAP[self.kind_combo.currentText()]
        record_list = self.records.query_detection_runs(
            status=status, start_month=start, end_month=end)
        rows = []
        for run in record_list:
            for res in run.results:
                rows.append({
                    "时间": run.run_time, "ID": run.id, "服务器": run.server_name,
                    "检测项": res.item_id, "状态": res.status, "证据": res.evidence})
        return rows, ["时间", "ID", "服务器", "检测项", "状态", "证据"], lambda r: r

    def _refresh(self):
        records, headers, to_row = self._query()
        self._rows = [to_row(r) for r in reversed(records)]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(0)
        self.detail_view.clear()
        for i, row in enumerate(self._rows):
            self.table.insertRow(i)
            for j, key in enumerate(headers):
                val = str(row.get(key, ""))
                table_item = QTableWidgetItem(val)
                if key == "状态":
                    table_item.setData(Qt.ItemDataRole.UserRole, val)
                self.table.setItem(i, j, table_item)

    def _show_detail(self):
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return
        idx = rows[0].row()
        if 0 <= idx < len(self._rows):
            self.detail_view.setPlainText(json.dumps(self._rows[idx], ensure_ascii=False, indent=2))