# 工作区：示范服务器（在独立可见终端中启动、停止内置示范服务器）
from PySide6.QtWidgets import (
    QWidget, QSplitter, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QFormLayout,
    QPlainTextEdit, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer

from core.server_runner import ServerProcessManager
from core.utils import safe_json_dumps

STATUS_CN = {"pass": "通过", "warn": "警告", "fail": "失败", "skip": "跳过"}
RUNNING_TEXT = "运行中"
STOPPED_TEXT = "已停止"


class WorkspaceServer(QWidget):
    """工作区：示范服务器的启动与停止"""

    def __init__(self, manager: ServerProcessManager):
        super().__init__()
        self.manager = manager
        self._setup_ui()
        self._reload()
        # 每秒复核进程存活：服务器窗口被关闭或进程自行退出后，状态回落为“已停止”
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ---------- 界面 ----------
    def _setup_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("示范服务器列表"))
        self.server_list = QListWidget()
        self.server_list.currentRowChanged.connect(self._on_selected)
        left_layout.addWidget(self.server_list)

        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("启动")
        self.btn_stop = QPushButton("停止")
        self.btn_stop_all = QPushButton("停止全部")
        self.btn_refresh = QPushButton("刷新")
        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_stop_all.clicked.connect(self._on_stop_all)
        self.btn_refresh.clicked.connect(self._reload)
        for btn in (self.btn_start, self.btn_stop):
            btn_row.addWidget(btn)
        btn_row.addWidget(self.btn_stop_all)
        btn_row.addWidget(self.btn_refresh)
        left_layout.addLayout(btn_row)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        info = QGroupBox("服务器详情")
        form = QFormLayout(info)
        self.lb_name = QLabel("")
        self.lb_transport = QLabel("")
        self.lb_address = QLabel("")
        self.lb_script = QLabel("")
        self.lb_pid = QLabel("")
        self.lb_started = QLabel("")
        self.lb_shared = QLabel("")
        self.lb_expect = QLabel("")
        self.lb_status = QLabel("")
        self.lb_notice = QLabel("")
        for lb in (self.lb_name, self.lb_transport, self.lb_address, self.lb_script,
                   self.lb_pid, self.lb_started, self.lb_shared, self.lb_expect,
                   self.lb_status, self.lb_notice):
            lb.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lb.setWordWrap(True)
        form.addRow("名称：", self.lb_name)
        form.addRow("传输：", self.lb_transport)
        form.addRow("地址/端口：", self.lb_address)
        form.addRow("启动脚本：", self.lb_script)
        form.addRow("进程ID：", self.lb_pid)
        form.addRow("启动时间：", self.lb_started)
        form.addRow("共享条目：", self.lb_shared)
        form.addRow("预期结果：", self.lb_expect)
        form.addRow("当前状态：", self.lb_status)
        form.addRow("注意事项：", self.lb_notice)
        right_layout.addWidget(info)

        right_layout.addWidget(QLabel("连接配置参考（用于在“开始”页添加服务器）"))
        self.connect_view = QPlainTextEdit()
        self.connect_view.setReadOnly(True)
        right_layout.addWidget(self.connect_view)

        right_layout.addWidget(QLabel(
            "说明：启动会在新的系统终端窗口中进行，关闭该窗口即停止对应服务器。"
        ))
        self.lb_desc = QLabel("")
        self.lb_desc.setWordWrap(True)
        right_layout.addWidget(self.lb_desc)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout = QHBoxLayout(self)
        layout.addWidget(splitter)

    # ---------- 列表 ----------
    def _reload(self):
        current = self.current_id()
        self.server_list.blockSignals(True)
        self.server_list.clear()
        for server in self.manager.servers:
            item = QListWidgetItem(self._item_text(server))
            item.setData(Qt.ItemDataRole.UserRole, server.get("id"))
            self.server_list.addItem(item)
        self.server_list.blockSignals(False)
        row = 0
        if current:
            for i in range(self.server_list.count()):
                if self.server_list.item(i).data(Qt.ItemDataRole.UserRole) == current:
                    row = i
                    break
        if self.server_list.count():
            self.server_list.setCurrentRow(row)
        else:
            self._clear_details()

    def _item_text(self, server: dict) -> str:
        status = RUNNING_TEXT if self.manager.is_running(str(server.get("id"))) else STOPPED_TEXT
        name = server.get("name") or server.get("id")
        return f"{name}（{status}）"

    def current_id(self) -> str:
        item = self.server_list.currentItem()
        if item is None:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or "")

    def _on_selected(self, _row: int):
        self._update_details()

    # ---------- 操作 ----------
    def _on_start(self):
        server_id = self.current_id()
        if not server_id:
            return
        ok, message = self.manager.start(server_id)
        if ok:
            QMessageBox.information(
                self, "启动服务器",
                message + "\n\n请勿关闭新打开的终端窗口，关闭该窗口即停止服务器。",
            )
        else:
            QMessageBox.warning(self, "启动失败", message)
        self._refresh_list()

    def _on_stop(self):
        server_id = self.current_id()
        if not server_id:
            return
        ok, message = self.manager.stop(server_id)
        if not ok:
            QMessageBox.warning(self, "停止失败", message)
        self._refresh_list()

    def _on_stop_all(self):
        count = self.manager.stop_all()
        QMessageBox.information(self, "停止全部", f"已停止{count}个服务器")
        self._refresh_list()

    # ---------- 轮询 ----------
    def _tick(self):
        """每秒复核存活状态，仅在状态变化时刷新界面"""
        changed = False
        for i in range(self.server_list.count()):
            item = self.server_list.item(i)
            server_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
            before = item.text()
            after = self._item_text({"id": server_id, "name": self._name_of(server_id)})
            if before != after:
                item.setText(after)
                changed = True
        if changed:
            self._update_details()

    def _name_of(self, server_id: str) -> str:
        server = self.manager.get(server_id) or {}
        return str(server.get("name") or server_id)

    def _refresh_list(self):
        for i in range(self.server_list.count()):
            item = self.server_list.item(i)
            server_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
            item.setText(self._item_text({"id": server_id, "name": self._name_of(server_id)}))
        self._update_details()

    # ---------- 详情 ----------
    def _clear_details(self):
        for lb in (self.lb_name, self.lb_transport, self.lb_address, self.lb_script,
                   self.lb_pid, self.lb_started, self.lb_shared, self.lb_expect,
                   self.lb_status, self.lb_notice, self.lb_desc):
            lb.setText("")
        self.connect_view.setPlainText("")

    def _update_details(self):
        server_id = self.current_id()
        server = self.manager.get(server_id) if server_id else None
        if server is None:
            self._clear_details()
            return
        transport = str(server.get("transport") or "")
        port = server.get("port")
        address = str(server.get("url") or "")
        if not address and port:
            address = f"127.0.0.1:{port}"
        if transport == "stdio" and not address:
            address = "本地子进程（不占用端口）"
        running = self.manager.is_running(server_id)
        pid = self.manager.pid(server_id)
        self.lb_name.setText(str(server.get("name") or server_id))
        self.lb_transport.setText(transport)
        self.lb_address.setText(address)
        self.lb_script.setText(str(server.get("script") or ""))
        self.lb_pid.setText(str(pid) if pid else "-")
        self.lb_started.setText(self.manager.started_at(server_id) or "-")
        self.lb_shared.setText(f"与该条目共享同一进程的条目数：{self.manager.shared_count(server_id)}")
        self.lb_expect.setText(self._format_expect(server.get("expect")))
        self.lb_status.setText(RUNNING_TEXT if running else STOPPED_TEXT)
        self.lb_notice.setText(str(server.get("notice") or "无"))
        self.lb_desc.setText(str(server.get("description") or ""))
        self.connect_view.setPlainText(
            safe_json_dumps(server.get("connect") or {}, indent=2)
        )

    def _format_expect(self, expect) -> str:
        if not isinstance(expect, dict) or not expect:
            return "无特别预期"
        parts = []
        for item_id, status in expect.items():
            parts.append(f"{item_id}：{STATUS_CN.get(str(status), str(status))}")
        return "；".join(parts)