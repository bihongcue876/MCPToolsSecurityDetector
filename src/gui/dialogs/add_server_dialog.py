# 添加 / 编辑 MCP 服务器的对话框
import uuid
import json
from datetime import datetime
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QSpinBox, QDialogButtonBox, QLabel, QTextEdit
)
from core.models import ServerConfig


class AddServerDialog(QDialog):
    """添加/编辑 MCP 服务器的对话框"""

    def __init__(self, parent=None, config: ServerConfig | None = None):
        super().__init__(parent)
        self.setWindowTitle("编辑服务器" if config else "添加服务器")
        self.resize(460, 460)
        self._config = config
        self._setup_ui()
        if config:
            self._fill_form(config)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        # 名称
        self.name_edit = QLineEdit()

        # 传输类型
        self.transport_combo = QComboBox()
        self.transport_combo.addItems(["http", "stdio", "sse"])
        self.transport_combo.currentTextChanged.connect(self._on_transport_changed)

        # URL（http/sse 使用）
        self.url_label = QLabel("URL：")
        self.url_edit = QLineEdit()

        # 命令与参数（stdio 使用）
        self.command_label = QLabel("命令：")
        self.command_edit = QLineEdit()
        self.args_label = QLabel("参数（空格分隔）：")
        self.args_edit = QLineEdit()

        # 认证（http/sse 使用）
        self.auth_type_combo = QComboBox()
        self.auth_type_combo.addItems(["none", "bearer", "api_key"])
        self.auth_value_edit = QLineEdit()
        self.auth_value_edit.setPlaceholderText("凭证内容（留空则不使用）")

        # 请求头与环境变量（通用，JSON 格式）
        self.headers_edit = QTextEdit()
        self.headers_edit.setPlaceholderText('{"Accept": "application/json"}')
        self.headers_edit.setMaximumHeight(60)
        self.env_edit = QTextEdit()
        self.env_edit.setPlaceholderText('{"KEY": "value"}')
        self.env_edit.setMaximumHeight(60)

        # 超时
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 300)
        self.timeout_spin.setValue(10)

        form.addRow("名称：", self.name_edit)
        form.addRow("传输类型：", self.transport_combo)
        form.addRow(self.url_label, self.url_edit)
        form.addRow(self.command_label, self.command_edit)
        form.addRow(self.args_label, self.args_edit)
        form.addRow("认证类型：", self.auth_type_combo)
        form.addRow("认证值：", self.auth_value_edit)
        form.addRow("请求头headers：", self.headers_edit)
        form.addRow("环境变量env：", self.env_edit)
        form.addRow("超时（秒）：", self.timeout_spin)
        layout.addLayout(form)

        # 底部按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # 初始化可见性
        self._on_transport_changed(self.transport_combo.currentText())

    def _on_transport_changed(self, transport: str):
        """根据传输类型切换显示字段：http/sse 显示 URL 与认证，stdio 显示命令与参数"""
        is_http = transport in ("http", "sse")
        self.url_label.setVisible(is_http)
        self.url_edit.setVisible(is_http)
        self.command_label.setVisible(not is_http)
        self.command_edit.setVisible(not is_http)
        self.args_label.setVisible(not is_http)
        self.args_edit.setVisible(not is_http)

    def _fill_form(self, config: ServerConfig):
        """编辑模式：回填已有值"""
        self.name_edit.setText(config.name)
        idx = self.transport_combo.findText(config.transport)
        if idx >= 0:
            self.transport_combo.setCurrentIndex(idx)
        self.url_edit.setText(config.url)
        self.command_edit.setText(config.command)
        self.args_edit.setText(" ".join(config.args))
        self.auth_type_combo.setCurrentText(config.auth_type)
        self.auth_value_edit.setText(config.auth_value)
        self.headers_edit.setPlainText(json.dumps(config.headers, ensure_ascii=False))
        self.env_edit.setPlainText(json.dumps(config.env, ensure_ascii=False))
        self.timeout_spin.setValue(config.timeout)

    def get_config(self) -> ServerConfig | None:
        """根据表单内容构造 ServerConfig，名称为空时返回 None"""
        name = self.name_edit.text().strip()
        if not name:
            return None

        transport = self.transport_combo.currentText()
        now = datetime.now().isoformat()
        args = self.args_edit.text().split()
        auth_type = self.auth_type_combo.currentText()
        auth_value = self.auth_value_edit.text().strip()
        headers = self._parse_json(self.headers_edit)
        env = self._parse_json(self.env_edit)

        if self._config:
            # 编辑模式：保留原 ID 和创建时间
            return ServerConfig(
                _id=self._config._id,
                name=name,
                transport=transport,
                command=self.command_edit.text().strip(),
                args=args,
                url=self.url_edit.text().strip(),
                headers=headers,
                env=env,
                auth_type=auth_type,
                auth_value=auth_value,
                timeout=self.timeout_spin.value(),
                create_at=self._config.create_at,
                update_at=now,
            )
        else:
            # 新增模式：生成新 ID，update_at 留空（尚未被修改过）
            return ServerConfig(
                _id=uuid.uuid4().hex,
                name=name,
                transport=transport,
                command=self.command_edit.text().strip(),
                args=args,
                url=self.url_edit.text().strip(),
                headers=headers,
                env=env,
                auth_type=auth_type,
                auth_value=auth_value,
                timeout=self.timeout_spin.value(),
                create_at=now,
                update_at="",
            )

    @staticmethod
    def _parse_json(edit: QTextEdit) -> dict:
        """解析 JSON 文本框，内容为空或非法时返回空 dict"""
        text = edit.toPlainText().strip()
        if not text:
            return {}
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}