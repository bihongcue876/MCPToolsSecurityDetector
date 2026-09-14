# 主要功能窗口
# 工作区一：MCP 服务器（左侧列表 + 右侧选项卡）
from PySide6.QtWidgets import (
    QWidget, QSplitter, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QLineEdit, QTextEdit,
    QComboBox, QFormLayout, QMessageBox, QDialog, QMenu, QApplication, QMainWindow,
    QGroupBox, QCheckBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QScrollArea
)
from PySide6.QtCore import Qt
from datetime import datetime

from core.connection import ConnectionManager
from data.config_manager import ConfigManager
from data.records_io import RecordsIO
from core.utils import safe_json_dumps, safe_json_loads
from core.models import ToolCallRecord
from gui.dialogs.add_server_dialog import AddServerDialog
from detection import engine
from gui.dialogs.detection_summary_dialog import DetectionSummaryDialog

STATUS_CN = {"pass": "通过", "warn": "警告", "fail": "失败", "skip": "跳过"}

class WorkspaceMain(QWidget):
    """工作区一：MCP 服务器管理"""

    def __init__(self, config_manager: ConfigManager,
                 connection: ConnectionManager,
                 records: RecordsIO):
        super().__init__()
        self.config_manager = config_manager
        self.connection = connection
        self.records = records
        self._setup_ui()
        self.refresh_server_list()
        self._results_cache: list = []

    def _setup_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ---- 左侧：服务器列表 ----
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.server_list = QListWidget()
        self.server_list.currentRowChanged.connect(self._on_server_selected)
        self.server_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.server_list.customContextMenuRequested.connect(self._on_context_menu)
        self.btn_add = QPushButton("添加  (+)")
        self.btn_add.clicked.connect(self._on_add_clicked)
        left_layout.addWidget(QLabel("服务器列表"))
        left_layout.addWidget(self.server_list)
        left_layout.addWidget(self.btn_add)

        # ---- 右侧：选项卡 ----
        right = QTabWidget()
        right.addTab(self._build_tab_config(), "配置")
        right.addTab(self._build_tab_overview(), "概览")
        right.addTab(self._build_tab_scan(), "鉴别")

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        layout = QHBoxLayout(self)
        layout.addWidget(splitter)

    # ---------- 配置子页 ----------
    def _build_tab_config(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        form = QFormLayout()
        self.config_name = QLineEdit()
        self.config_transport = QComboBox()
        self.config_transport.addItems(["http", "stdio", "sse"])
        self.config_url = QLineEdit()
        self.config_command = QLineEdit()
        self.config_args = QLineEdit()
        form.addRow("名称：", self.config_name)
        form.addRow("传输：", self.config_transport)
        form.addRow("URL：", self.config_url)
        form.addRow("命令：", self.config_command)
        form.addRow("参数：", self.config_args)
        layout.addLayout(form)

        layout.addWidget(QLabel("配套 JSON："))
        self.config_json = QTextEdit()
        self.config_json.setReadOnly(True)
        layout.addWidget(self.config_json)

        btn_row = QHBoxLayout()
        self.btn_save = QPushButton("保存修改")
        self.btn_edit = QPushButton("编辑")
        self.btn_delete = QPushButton("删除")
        self.btn_test = QPushButton("测试连接")
        self.btn_disconnect = QPushButton("断开连接")
        self.btn_disconnect.setEnabled(False)
        self.btn_save.clicked.connect(self._on_save_clicked)
        self.btn_edit.clicked.connect(self._on_edit_clicked)
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        self.btn_test.clicked.connect(self._on_test_clicked)
        self.btn_disconnect.clicked.connect(self._on_disconnect_clicked)
        btn_row.addWidget(self.btn_save)
        btn_row.addWidget(self.btn_edit)
        btn_row.addWidget(self.btn_delete)
        btn_row.addWidget(self.btn_test)
        btn_row.addWidget(self.btn_disconnect)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        return w

    # ---------- 概览子页 ----------
    def _build_tab_overview(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)

        # 左侧工具列表
        left = QVBoxLayout()
        left.addWidget(QLabel("工具列表"))
        self.overview_tool_list = QListWidget()
        self.overview_tool_list.currentRowChanged.connect(self._on_tool_selected)
        left.addWidget(self.overview_tool_list)
        layout.addLayout(left, 1)

        # 右侧工具测试
        right = QVBoxLayout()
        right.addWidget(QLabel("工具测试"))

        right.addWidget(QLabel("描述："))
        self.overview_desc = QTextEdit()
        self.overview_desc.setReadOnly(True)
        self.overview_desc.setMaximumHeight(80)
        right.addWidget(self.overview_desc)

        right.addWidget(QLabel("输入（JSON 对象）："))
        self.overview_input = QTextEdit()
        right.addWidget(self.overview_input)

        btn_fill = QPushButton("根据Schema形式形成/重置输入示例")
        btn_fill.clicked.connect(self._on_fill_example_clicked)
        right.addWidget(btn_fill)

        right.addWidget(QLabel("输出："))
        self.overview_output = QTextEdit()
        self.overview_output.setReadOnly(True)
        right.addWidget(self.overview_output)

        self.btn_execute = QPushButton("执行")
        self.btn_execute.clicked.connect(self._on_execute_clicked)
        right.addWidget(self.btn_execute)
        layout.addLayout(right, 2)
        return w

    # ---------- 检测子页 ----------
    def _build_tab_scan(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)

        # 顶部：全部检测 + 状态
        top = QHBoxLayout()
        self.btn_scan_all = QPushButton("全部检测")
        self.btn_scan_all.clicked.connect(self._on_scan_all_clicked)
        self.scan_status = QLabel("未检测")
        top.addWidget(self.btn_scan_all)
        top.addWidget(self.scan_status)
        top.addStretch()
        outer.addLayout(top)

        # 中部：滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        self.group_a = self._build_group_a()
        inner_layout.addWidget(self.group_a)
        self.group_b = self._build_group_b()
        inner_layout.addWidget(self.group_b)
        inner_layout.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        # 底部：共享详情框
        outer.addWidget(QLabel("详情："))
        self.scan_detail = QTextEdit()
        self.scan_detail.setReadOnly(True)
        self.scan_detail.setMaximumHeight(140)
        outer.addWidget(self.scan_detail)

        return w

# ---------- groups ----------
    def _build_group_a(self) -> QGroupBox:
        box = QGroupBox("A组：传输与鉴权")
        layout = QVBoxLayout(box)

        row = QHBoxLayout()
        self.cb_a1 = QCheckBox("A1 TLS/明文传输")
        self.cb_a2 = QCheckBox("A2 匿名访问")
        self.cb_a3 = QCheckBox("A3 硬编码凭证")
        self.cb_a4 = QCheckBox("A4 协议握手")
        for cb in (self.cb_a1, self.cb_a2, self.cb_a3, self.cb_a4):
            cb.setChecked(True)
            row.addWidget(cb)
        row.addStretch()
        btn = QPushButton("运行A组")
        btn.clicked.connect(self._on_run_group_a)
        row.addWidget(btn)
        layout.addLayout(row)

        self.table_a = QTableWidget(0, 4)
        self.table_a.setHorizontalHeaderLabels(["编号", "名称", "状态", "证据摘要"])
        self.table_a.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table_a.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers) # 禁止编辑
        self.table_a.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows) # 整行选中
        self.table_a.setSelectionMode(QTableWidget.SelectionMode.SingleSelection) # 单选
        self.table_a.itemSelectionChanged.connect(self._on_table_a_selected)
        layout.addWidget(self.table_a)
        return box
    
    def _build_group_b(self) -> QGroupBox:
        box = QGroupBox("B组：工具与注入风险")
        layout = QVBoxLayout(box)
        row = QHBoxLayout()
        self.cb_b1 = QCheckBox("B1 工具元数据提示注入")
        self.cb_b2 = QCheckBox("B2 工具结果响应注入")
        self.cb_b3 = QCheckBox("B3 参数Schema约束不足")
        self.cb_b4 = QCheckBox("B4 危险能力声明不一致")
        for cb in (self.cb_b1, self.cb_b2, self.cb_b3, self.cb_b4):
            cb.setChecked(True)
            row.addWidget(cb)
        row.addStretch()
        btn = QPushButton("运行B组")
        btn.clicked.connect(self._on_run_group_b)
        row.addWidget(btn)
        layout.addLayout(row)
        self.table_b = QTableWidget(0, 4)
        self.table_b.setHorizontalHeaderLabels(["编号", "名称", "状态", "证据摘要"])
        self.table_b.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table_b.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_b.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_b.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_b.itemSelectionChanged.connect(self._on_table_b_selected)
        layout.addWidget(self.table_b)
        return box

    # ---------- 服务器列表 ----------
    def refresh_server_list(self):
        """重新加载服务器列表，保留之前选中的项"""
        prev_id = self._current_server_id()
        self.server_list.blockSignals(True)
        self.server_list.clear()
        restore_row = -1
        for i, cfg in enumerate(self.config_manager.get_all()):
            item = QListWidgetItem(cfg.name)
            item.setData(Qt.ItemDataRole.UserRole, cfg._id)
            self.server_list.addItem(item)
            if cfg._id == prev_id:
                restore_row = i
        self.server_list.blockSignals(False)
        if restore_row >= 0:
            self.server_list.setCurrentRow(restore_row)
        elif self.server_list.count() > 0:
            self.server_list.setCurrentRow(0)
        else:
            self._clear_config_form()

    def _current_server_id(self) -> str:
        item = self.server_list.currentItem()
        if item is None:
            return ""
        return item.data(Qt.ItemDataRole.UserRole) or ""

    def _on_server_selected(self, row: int):
        item = self.server_list.item(row)
        if item is None:
            self._clear_config_form()
            return
        cfg = self.config_manager.get_by_id(item.data(Qt.ItemDataRole.UserRole))
        if cfg is None:
            self._clear_config_form()
            return
        self._fill_config_form(cfg)
        self._load_latest_detection(cfg._id)
        
    def _load_latest_detection(self, server_id: str):
        """从记录中读取该服务器最近一次检测，回填检测页"""
        self.table_a.setRowCount(0)
        self.table_b.setRowCount(0)
        self.scan_detail.clear()
        self._results_cache = []
        self.scan_status.setText("未检测")
        try:
            run = self.records.get_latest_detection_run(server_id)
        except Exception:
            return
        if run is None or not run.results:
            return
        self._results_cache = list(run.results)
        self._fill_tables(run.results)
        self.scan_status.setText(f"上次检测：{run.run_time}")

    def _fill_config_form(self, cfg):
        self.config_name.setText(cfg.name)
        idx = self.config_transport.findText(cfg.transport)
        if idx >= 0:
            self.config_transport.setCurrentIndex(idx)
        self.config_url.setText(cfg.url)
        self.config_command.setText(cfg.command)
        self.config_args.setText(" ".join(cfg.args))
        self.config_json.setPlainText(safe_json_dumps(cfg.__dict__))

    def _clear_config_form(self):
        self.config_name.clear()
        self.config_url.clear()
        self.config_command.clear()
        self.config_args.clear()
        self.config_json.clear()

    # ---------- 增删改 ----------
    def _on_add_clicked(self):
        dialog = AddServerDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            cfg = dialog.get_config()
            if cfg is None:
                QMessageBox.warning(self, "警告", "名称不能为空")
                return
            if not self.config_manager.add(cfg):
                QMessageBox.warning(self, "警告", "服务器 ID 已存在，未添加")
                return
            self.refresh_server_list()

    def _on_edit_clicked(self):
        server_id = self._current_server_id()
        if not server_id:
            QMessageBox.information(self, "提示", "请先选择一个服务器")
            return
        cfg = self.config_manager.get_by_id(server_id)
        if cfg is None:
            return
        dialog = AddServerDialog(self, config=cfg)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_cfg = dialog.get_config()
            if new_cfg is None:
                return
            self.config_manager.update(server_id, new_cfg)
            self.refresh_server_list()

    def _on_save_clicked(self):
        server_id = self._current_server_id()
        if not server_id:
            QMessageBox.information(self, "提示", "请先选择一个服务器")
            return
        cfg = self.config_manager.get_by_id(server_id)
        if cfg is None:
            return
        cfg.name = self.config_name.text().strip() or cfg.name
        cfg.transport = self.config_transport.currentText()
        cfg.url = self.config_url.text().strip()
        cfg.command = self.config_command.text().strip()
        cfg.args = self.config_args.text().split()
        cfg.update_at = datetime.now().isoformat()
        self.config_manager.update(server_id, cfg)
        self.refresh_server_list()
        self._set_status("已保存配置")

    def _on_delete_clicked(self):
        server_id = self._current_server_id()
        if not server_id:
            QMessageBox.information(self, "提示", "请先选择一个服务器")
            return
        cfg = self.config_manager.get_by_id(server_id)
        if cfg is None:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除服务器「{cfg.name}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.config_manager.delete(server_id)
            self.refresh_server_list()
            self._set_status("已删除服务器")

    # ---------- 连接与断开 ----------
    def _on_test_clicked(self):
        """测试连接：连接后刷新工具列表"""
        server_id = self._current_server_id()
        if not server_id:
            QMessageBox.information(self, "提示", "请先选择一个服务器")
            return
        cfg = self.config_manager.get_by_id(server_id)
        if cfg is None:
            return

        # 禁用按钮，避免重复点击
        self.btn_test.setEnabled(False)
        self.btn_test.setText("连接中...")
        QApplication.processEvents()

        try:
            ok, err = self.connection.connect(cfg)
        finally:
            self.btn_test.setEnabled(True)
            self.btn_test.setText("测试连接")

        if ok:
            self.btn_disconnect.setEnabled(True)
            version = self.connection.client.protocol_version if self.connection.client else ""
            self._set_status(f"已连接：{cfg.name}  协议版本：{version}")
            self.refresh_tool_list()
        else:
            QMessageBox.warning(self, "连接失败", err)

    def _on_disconnect_clicked(self):
        """断开当前连接并清空工具列表"""
        self.connection.disconnect()
        self.btn_disconnect.setEnabled(False)
        self.overview_tool_list.clear()
        self.overview_output.clear()
        self._set_status("已断开连接")

    # ---------- 工具列表与执行 ----------
    def refresh_tool_list(self):
        self.overview_tool_list.clear()
        self._tools_cache = {}
        try:
            tools = self.connection.list_tools(refresh=True)
        except Exception as e:
            QMessageBox.warning(self, "获取工具失败", str(e))
            return
        for t in tools:
            self._tools_cache[t.name] = t
            item = QListWidgetItem(t.name)
            item.setData(Qt.ItemDataRole.UserRole, t.name)
            self.overview_tool_list.addItem(item)
        self._set_status(f"已获取 {len(tools)} 个工具")

    def _on_execute_clicked(self):
        """调用工具执行"""
        if not self.connection.is_connected():
            QMessageBox.information(self, "提示", "请先连接服务器")
            return
        tool_name = self._current_tool_name()
        if not tool_name:
            QMessageBox.information(self, "提示", "请先选择要调用的工具")
            return

        # 解析输入参数
        raw = self.overview_input.toPlainText().strip()
        if raw:
            args = safe_json_loads(raw)
            if not isinstance(args, dict):
                QMessageBox.warning(self, "参数错误", "输入内容必须是合法的 JSON 对象")
                return
        else:
            args = {}

        # 调用
        self.btn_execute.setEnabled(False)
        self.btn_execute.setText("执行中...")
        QApplication.processEvents()
        try:
            result = self.connection.call_tool(tool_name, args)
        except Exception as e:
            self.btn_execute.setEnabled(True)
            self.btn_execute.setText("执行")
            QMessageBox.warning(self, "调用失败", str(e))
            return
        finally:
            self.btn_execute.setEnabled(True)
            self.btn_execute.setText("执行")

        # 显示结果
        self.overview_output.setPlainText(safe_json_dumps(result))

        # 写入记录
        record = ToolCallRecord(
            server_id=self._current_server_id(),
            tool_name=tool_name,
            args_json=safe_json_dumps(args),
            response_json=safe_json_dumps(result),
            is_attack=False,
        )
        try:
            self.records.write_tool_call(record)
        except Exception:
            pass  # 记录失败不影响主流程

        self._set_status(f"已调用 {tool_name}")

    # ---------- 状态栏 ----------
    def _set_status(self, msg: str):
        """把消息写入主窗口状态栏"""
        from PySide6.QtWidgets import QMainWindow
        win = self.window()
        if isinstance(win, QMainWindow):
            win.statusBar().showMessage(msg)

    # ---------- 右键菜单 ----------
    def _on_context_menu(self, pos):
        item = self.server_list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        act_edit = menu.addAction("编辑")
        act_delete = menu.addAction("删除")
        action = menu.exec(self.server_list.mapToGlobal(pos))
        if action == act_edit:
            self._on_edit_clicked()
        elif action == act_delete:
            self._on_delete_clicked()
            
    # ---------- 工具选中后补充下拉描述 ----------
    def _on_tool_selected(self, row: int):
        """点击左侧工具列表时刷新描述和示例输入"""
        item = self.overview_tool_list.item(row)
        if item is None:
            self.overview_desc.clear()
            self.overview_input.clear()
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        self._show_tool_description(name)
        self._prefill_input_example(name)

    def _on_combo_changed(self, name: str):
        """下拉框变化时，同步描述和示例输入"""
        self._show_tool_description(name)
        self._prefill_input_example(name)

    def _show_tool_description(self, name: str):
        """把工具描述显示到描述框"""
        tool = getattr(self, "_tools_cache", {}).get(name)
        if tool is None:
            self.overview_desc.clear()
            return
        self.overview_desc.setPlainText(tool.description or "（无描述）")

    def _prefill_input_example(self, name: str):
        """根据 input_schema 生成一份示例输入，填入输入框"""
        tool = getattr(self, "_tools_cache", {}).get(name)
        if tool is None:
            return
        example = self._build_example_from_schema(tool.input_schema)
        self.overview_input.setPlainText(safe_json_dumps(example))

    def _current_tool_name(self) -> str:
        item = self.overview_tool_list.currentItem()
        if item is None:
            return ""
        return item.data(Qt.ItemDataRole.UserRole) or ""

    def _on_fill_example_clicked(self):
        name = self._current_tool_name()
        if not name:
            QMessageBox.information(self, "提示", "请先在左侧选择工具")
            return
        self._prefill_input_example(name)

    @staticmethod
    def _build_example_from_schema(schema: dict) -> dict:
        """根据 JSON Schema 生成一份示例参数字典"""
        if not isinstance(schema, dict):
            return {}
        properties = schema.get("properties", {})
        result = {}
        for key, prop in properties.items():
            ptype = prop.get("type", "string")
            if "default" in prop:
                result[key] = prop["default"]
            elif ptype == "string":
                result[key] = ""
            elif ptype == "integer":
                result[key] = 0
            elif ptype == "number":
                result[key] = 0.0
            elif ptype == "boolean":
                result[key] = False
            elif ptype == "array":
                result[key] = []
            elif ptype == "object":
                result[key] = {}
            else:
                result[key] = ""
        return result
    
    # ---------- A组检测 ----------
    def _on_run_group_a(self):
        checks = []
        if self.cb_a1.isChecked(): checks.append("A1")
        if self.cb_a2.isChecked(): checks.append("A2")
        if self.cb_a3.isChecked(): checks.append("A3")
        if self.cb_a4.isChecked(): checks.append("A4")
        self._run_checks(checks, "A组")
    
    # ---------- B组检测 ----------
    def _on_run_group_b(self):
        checks = []
        if self.cb_b1.isChecked(): checks.append("B1")
        if self.cb_b2.isChecked(): checks.append("B2")
        if self.cb_b3.isChecked(): checks.append("B3")
        if self.cb_b4.isChecked(): checks.append("B4")
        self._run_checks(checks, "B组")

    def _on_scan_all_clicked(self):
        checks = []
        if self.cb_a1.isChecked(): checks.append("A1")
        if self.cb_a2.isChecked(): checks.append("A2")
        if self.cb_a3.isChecked(): checks.append("A3")
        if self.cb_a4.isChecked(): checks.append("A4")
        if self.cb_b1.isChecked(): checks.append("B1")
        if self.cb_b2.isChecked(): checks.append("B2")
        if self.cb_b3.isChecked(): checks.append("B3")
        if self.cb_b4.isChecked(): checks.append("B4")
        self._run_checks(checks, "全部")

    def _run_checks(self, checks: list, label: str):
        if not checks:
            QMessageBox.information(self, "提示", "请至少选择一个检测项")
            return
        server_id = self._current_server_id()
        if not server_id:
            QMessageBox.information(self, "提示", "请先选择一个服务器")
            return
        cfg = self.config_manager.get_by_id(server_id)
        if cfg is None:
            return
        client = self.connection.client if self.connection.is_connected() else None
        self.scan_status.setText(f"{label}检测中...")
        self.btn_scan_all.setEnabled(False)
        QApplication.processEvents()
        try:
            results = engine.run_and_record(checks, cfg, client, self.records)
        except Exception as e:
            self.scan_status.setText("检测失败")
            self.btn_scan_all.setEnabled(True)
            QMessageBox.warning(self, "检测失败", str(e))
            return
        finally:
            self.btn_scan_all.setEnabled(True)
        self._results_cache = results
        self._fill_tables(results)
        pass_n = sum(1 for r in results if r.status == "pass")
        warn_n = sum(1 for r in results if r.status == "warn")
        fail_n = sum(1 for r in results if r.status == "fail")
        self.scan_status.setText(f"{label}完成：通过{pass_n}，警告{warn_n}，失败{fail_n}")
        DetectionSummaryDialog(results, self).exec()

    def _fill_tables(self, results: list):
        """按模块分别填入A表和B表"""
        a_results = [r for r in results if r.module == "A"]
        b_results = [r for r in results if r.module == "B"]
        self._fill_one_table(self.table_a, a_results)
        self._fill_one_table(self.table_b, b_results)

    def _fill_one_table(self, table: QTableWidget, results: list):
        table.setRowCount(0)
        for r in results:
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(r.item_id))
            table.setItem(row, 1, QTableWidgetItem(r.item_name))
            table.setItem(row, 2, QTableWidgetItem(STATUS_CN.get(r.status, str(r.status))))
            brief = r.evidence[:60].replace("\n", " ")
            table.setItem(row, 3, QTableWidgetItem(brief))

    def _on_table_a_selected(self):
        self._show_result_detail(self.table_a)

    def _on_table_b_selected(self):
        self._show_result_detail(self.table_b)

    def _show_result_detail(self, table: QTableWidget):
        rows = table.selectionModel().selectedRows() if table.selectionModel() else []
        if not rows:
            return
        idx = rows[0].row()
        item = table.item(idx, 0)
        if item is None:
            return
        item_id = item.text()
        # 从缓存中按编号查找，避免A/B两组行号互相干扰
        target = None
        for r in getattr(self, "_results_cache", []):
            if r.item_id == item_id:
                target = r
                break
        if target is None:
            return
        text = (f"编号：{target.item_id}\n名称：{target.item_name}\n状态：{STATUS_CN.get(target.status, target.status)}\n\n证据：\n{target.evidence}\n\n建议：\n{target.suggestion}")
        self.scan_detail.setPlainText(text)