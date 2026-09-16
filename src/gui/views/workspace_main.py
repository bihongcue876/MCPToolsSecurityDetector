# 主要功能窗口
# 工作区一：MCP 服务器（左侧列表 + 右侧选项卡）
from PySide6.QtWidgets import (
    QWidget, QSplitter, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QLineEdit, QTextEdit,
    QComboBox, QFormLayout, QMessageBox, QDialog, QMenu, QApplication, QMainWindow,
    QGroupBox, QCheckBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QScrollArea, QStyledItemDelegate, QStyleOptionViewItem
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QTextDocument
from datetime import datetime

from core.connection import ConnectionManager
from data.config_manager import ConfigManager
from data.records_io import RecordsIO
from core.utils import safe_json_dumps, safe_json_loads
from core.models import ToolCallRecord, AttackPayload
from gui.dialogs.add_server_dialog import AddServerDialog
from detection import engine
from gui.dialogs.detection_summary_dialog import DetectionSummaryDialog
from testing.attack_simulator import AttackSimulator, load_payloads

STATUS_CN = {"pass": "通过", "warn": "警告", "fail": "失败", "skip": "跳过"}


class WrapCellDelegate(QStyledItemDelegate):
    """单元格文字自动换行，完整显示而不截断"""

    def _metrics(self, option, text: str, width: int):
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        doc.setPlainText(text)
        doc.setTextWidth(max(width, 20))
        return doc

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text or ""
        if not text:
            super().paint(painter, option, index)
            return
        doc = self._metrics(opt, text, opt.rect.width() - 8)
        painter.save()
        painter.translate(opt.rect.left() + 4, opt.rect.top() + 4)
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):
        base = super().sizeHint(option, index)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if not text:
            return base
        # 按单元格实际宽度换算换行所需高度，最小不低于默认行高
        width = option.rect.width() - 8 if option.rect.width() > 40 else 212
        doc = self._metrics(option, str(text), width)
        h = int(doc.size().height()) + 8
        return QSize(base.width(), max(base.height(), h))


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

        layout.addWidget(QLabel("配套JSON："))
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

        right.addWidget(QLabel("输入（JSON对象）："))
        self.overview_input = QTextEdit()
        right.addWidget(self.overview_input)

        btn_fill = QPushButton("根据Schema形式形成/重置输入示例")
        btn_fill.clicked.connect(self._on_fill_example_clicked)
        right.addWidget(btn_fill)

        payload_row = QHBoxLayout()
        payload_row.addWidget(QLabel("攻防载荷："))
        self.overview_payload_combo = QComboBox()
        self.overview_payload_combo.setPlaceholderText("选择固定载荷")
        payload_row.addWidget(self.overview_payload_combo, 1)
        btn_payload = QPushButton("一键填充载荷")
        btn_payload.clicked.connect(self._on_payload_fill_clicked)
        payload_row.addWidget(btn_payload)
        right.addLayout(payload_row)

        # 载荷库下拉项（与攻防检测共用默认载荷库）
        self._overview_payload_map: dict[str, AttackPayload] = {}
        for p in load_payloads():
            label = f"{p.name}（{p.category}）"
            self._overview_payload_map[label] = p
            self.overview_payload_combo.addItem(label)

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

        # 中部：滚动区（按钮 + 两个表格区域整体上下滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)

        # 顶部：全部检测 + 状态
        top = QHBoxLayout()
        self.btn_scan_all = QPushButton("全部检测")
        self.btn_scan_all.clicked.connect(self._on_scan_all_clicked)
        self.scan_status = QLabel("未检测")
        top.addWidget(self.btn_scan_all)
        top.addWidget(self.scan_status)
        top.addStretch()
        inner_layout.addLayout(top)

        self.group_a = self._build_group_a()
        inner_layout.addWidget(self.group_a)
        self.group_b = self._build_group_b()
        inner_layout.addWidget(self.group_b)
        self.group_attack = self._build_group_attack()
        inner_layout.addWidget(self.group_attack)
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
        self.cb_a2 = QCheckBox("A2匿名访问")
        self.cb_a3 = QCheckBox("A3硬编码凭证")
        self.cb_a4 = QCheckBox("A4协议握手")
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
        self.table_a.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_a.horizontalHeader().setDefaultSectionSize(150)
        self.table_a.setItemDelegate(WrapCellDelegate(self.table_a))
        self.table_a.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table_a.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table_a.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers) # 禁止编辑
        self.table_a.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows) # 整行选中
        self.table_a.setSelectionMode(QTableWidget.SelectionMode.SingleSelection) # 单选
        self.table_a.itemSelectionChanged.connect(self._on_table_a_selected)
        self.table_a.horizontalHeader().sectionResized.connect(self._refit_tables)
        layout.addWidget(self.table_a)
        return box
    
    def _build_group_b(self) -> QGroupBox:
        box = QGroupBox("B组：工具与注入风险")
        layout = QVBoxLayout(box)
        row = QHBoxLayout()
        self.cb_b1 = QCheckBox("B1工具元数据提示注入")
        self.cb_b2 = QCheckBox("B2工具结果响应注入")
        self.cb_b3 = QCheckBox("B3参数Schema约束不足")
        self.cb_b4 = QCheckBox("B4危险能力声明不一致")
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
        self.table_b.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_b.horizontalHeader().setDefaultSectionSize(150)
        self.table_b.setItemDelegate(WrapCellDelegate(self.table_b))
        self.table_b.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table_b.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table_b.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_b.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_b.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_b.itemSelectionChanged.connect(self._on_table_b_selected)
        self.table_b.horizontalHeader().sectionResized.connect(self._refit_tables)
        layout.addWidget(self.table_b)
        return box

    def _build_group_attack(self) -> QGroupBox:
        """攻防检测组：选工具 → 选载荷 → 预览 → 确认执行 → 结果框"""
        box = QGroupBox("攻防检测")
        layout = QVBoxLayout(box)

        row = QHBoxLayout()
        self.attack_tool_combo = QComboBox()
        self.attack_tool_combo.setPlaceholderText("选择工具")
        self.attack_payload_combo = QComboBox()
        self.attack_payload_combo.setPlaceholderText("选择载荷")
        self.attack_payload_combo.currentIndexChanged.connect(self._on_attack_payload_changed)
        self.attack_allow_write = QCheckBox("允许非只读工具")
        row.addWidget(QLabel("工具："))
        row.addWidget(self.attack_tool_combo, 1)
        row.addWidget(QLabel("载荷："))
        row.addWidget(self.attack_payload_combo, 1)
        row.addWidget(self.attack_allow_write)
        layout.addLayout(row)

        # 载荷预览（只读）
        layout.addWidget(QLabel("载荷预览："))
        self.attack_payload_preview = QTextEdit()
        self.attack_payload_preview.setReadOnly(True)
        self.attack_payload_preview.setMaximumHeight(70)
        layout.addWidget(self.attack_payload_preview)

        # 执行按钮 + 结果框
        self.btn_attack_execute = QPushButton("执行测试")
        self.btn_attack_execute.clicked.connect(self._on_attack_execute_clicked)
        layout.addWidget(self.btn_attack_execute)
        self.attack_result = QTextEdit()
        self.attack_result.setReadOnly(True)
        self.attack_result.setPlaceholderText("执行结果显示：请求、响应、判定")
        layout.addWidget(self.attack_result)

        # 加载载荷库
        self._payloads = load_payloads()
        self._payload_map: dict[str, AttackPayload] = {}
        for p in self._payloads:
            label = f"{p.name}（{p.category}）"
            self._payload_map[label] = p
            self.attack_payload_combo.addItem(label)
        return box

    def _on_attack_payload_changed(self, index: int):
        """载荷下拉变化时更新预览框"""
        if index < 0 or not hasattr(self, "attack_payload_preview"):
            return
        label = self.attack_payload_combo.currentText()
        p = self._payload_map.get(label)
        if p is None:
            self.attack_payload_preview.clear()
            return
        text = p.payload * max(1, p.repeat)
        extra = f"\n判定特征：{', '.join(p.detect)}" if p.detect else ""
        self.attack_payload_preview.setPlainText(text + extra)

    def _on_attack_execute_clicked(self):
        """攻防检测执行入口：确认 → attack_simulator 执行 → 展示并写日志"""
        if not self.connection.is_connected():
            QMessageBox.information(self, "提示", "请先连接服务器")
            return
        tool_name = self.attack_tool_combo.currentText()
        if not tool_name:
            QMessageBox.information(self, "提示", "请先选择工具")
            return
        label = self.attack_payload_combo.currentText()
        payload = self._payload_map.get(label)
        if payload is None:
            QMessageBox.information(self, "提示", "请先选择载荷")
            return
        tool = self._tools_cache.get(tool_name) if hasattr(self, "_tools_cache") else None
        if tool is not None and not self.attack_allow_write.isChecked():
            # 只读特征判断：名称/描述含只读词或 readOnlyHint 为 True
            name_desc = f"{tool.name} {tool.description}".lower()
            readonly_hint = tool.annotations.get("readOnlyHint", False) if tool.annotations else False
            if not readonly_hint and not any(k in name_desc for k in ("get", "list", "read", "view", "query", "search", "fetch", "show")):
                reply = QMessageBox.question(
                    self, "非只读工具",
                    f"工具「{tool_name}」不具备只读特征，确认要对它执行攻防测试吗？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
        # 确认对话框：工具名 + 载荷内容 + 预期风险
        preview = (payload.payload * max(1, payload.repeat))[:200]
        reply = QMessageBox.question(
            self, "确认执行攻防测试",
            f"工具：{tool_name}\n载荷：{payload.name}\n内容预览：{preview}\n\n"
            f"将向目标服务器发送该载荷并观察响应，属于受控探测。确认执行？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        cfg = self.config_manager.get_by_id(self._current_server_id()) if self._current_server_id() else None
        if cfg is None:
            QMessageBox.information(self, "提示", "未找到当前服务器配置")
            return
        client = self.connection.client
        if client is None:
            QMessageBox.information(self, "提示", "客户端未就绪")
            return
        sim = AttackSimulator(client, cfg, self.records)
        self.btn_attack_execute.setEnabled(False)
        self.btn_attack_execute.setText("执行中...")
        QApplication.processEvents()
        try:
            result = sim.execute(tool_name, payload, tool.input_schema if tool else None)
        except Exception as e:
            result = {
                "payload": label, "args": None, "response": None,
                "judgement": f"执行异常：{e}", "abnormal": False,
            }
        finally:
            self.btn_attack_execute.setEnabled(True)
            self.btn_attack_execute.setText("执行测试")
        resp = result.get("response")
        resp_text = safe_json_dumps(resp) if resp is not None else ""
        self.attack_result.setPlainText(
            f"载荷：{result.get('payload','')}\n"
            f"参数：{safe_json_dumps(result.get('args')) if result.get('args') else '（未注入）'}\n"
            f"响应：{resp_text}\n"
            f"判定：{result.get('judgement','')}"
        )
        self._set_status(f"攻防测试完成：{result.get('judgement','')}")

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
        self._refit_tables()
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
                QMessageBox.warning(self, "警告", "服务器ID已存在，未添加")
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
        self.attack_tool_combo.clear()
        self._set_status("已断开连接")

    # ---------- 工具列表与执行 ----------
    def refresh_tool_list(self):
        self.overview_tool_list.clear()
        self.attack_tool_combo.clear()
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
            self.attack_tool_combo.addItem(t.name)
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
                QMessageBox.warning(self, "参数错误", "输入内容必须是合法的JSON对象")
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
        cfg_now = self.config_manager.get_by_id(self._current_server_id())
        record = ToolCallRecord(
            server_id=self._current_server_id(),
            server_name=cfg_now.name if cfg_now else "",
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

    def _on_payload_fill_clicked(self):
        """把所选攻防载荷一键填入当前工具的输入框，与攻防检测形成呼应"""
        name = self._current_tool_name()
        if not name:
            QMessageBox.information(self, "提示", "请先在左侧选择工具")
            return
        label = self.overview_payload_combo.currentText()
        p = self._overview_payload_map.get(label)
        if p is None:
            QMessageBox.information(self, "提示", "请先选择载荷")
            return
        tool = getattr(self, "_tools_cache", {}).get(name)
        if tool is None:
            QMessageBox.information(self, "提示", "未获取到该工具信息")
            return
        args, note = AttackSimulator.inject(p, tool.input_schema)
        if args is None:
            QMessageBox.information(self, "提示", note)
            return
        self.overview_input.setPlainText(safe_json_dumps(args))
        self._set_status(f"已填充载荷：{p.name}")

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
            table.setItem(row, 3, QTableWidgetItem(r.evidence))
        self._fit_table_height(table)

    def _fit_table_height(self, table: QTableWidget):
        """让表格高度恰好容纳全部行，交由外层滚动区整体滚动

        表格内部不再出现滚动条，所有行完整展开；外层 QScrollArea 负责滚动。
        """
        table.resizeRowsToContents()
        header_h = table.horizontalHeader().height() or 30
        total = header_h + 2 * table.frameWidth()
        for r in range(table.rowCount()):
            total += table.rowHeight(r)
        table.setFixedHeight(total)

    def _refit_tables(self, *args):
        """列宽变化（窗口缩放/拉伸）时重算两个表格的行高"""
        for t in (self.table_a, self.table_b):
            self._fit_table_height(t)

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