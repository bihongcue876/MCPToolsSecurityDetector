# 工作区二：设置内容
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QFormLayout,
    QPushButton, QHBoxLayout, QSpinBox, QMessageBox,
)
from PySide6.QtCore import Qt
from app_config import load_settings, save_settings, DATA_DIR, APP_NAME, VERSION


class WorkspaceSetting(QWidget):
    """工作区二：全局设置"""

    def __init__(self):
        super().__init__()
        self._setup_ui()
        self._load()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("设置"))
        form = QFormLayout()

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 300)
        self.log_lines_spin = QSpinBox()
        self.log_lines_spin.setRange(10, 10000)

        form.addRow("默认超时（秒）：", self.timeout_spin)
        form.addRow("日志最大行数：", self.log_lines_spin)
        layout.addLayout(form)

        # 数据目录
        self.data_dir_label = QLabel(str(DATA_DIR))
        self.data_dir_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("数据目录：", self.data_dir_label)

        btn_row = QHBoxLayout()
        self.btn_save = QPushButton("保存设置")
        self.btn_reload = QPushButton("重新载入")
        self.btn_open_dir = QPushButton("打开数据目录")
        self.btn_about = QPushButton("关于")
        self.btn_save.clicked.connect(self._save)
        self.btn_reload.clicked.connect(self._load)
        self.btn_open_dir.clicked.connect(self._open_data_dir)
        self.btn_about.clicked.connect(self._show_about)
        btn_row.addWidget(self.btn_save)
        btn_row.addWidget(self.btn_reload)
        btn_row.addWidget(self.btn_open_dir)
        btn_row.addWidget(self.btn_about)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        layout.addStretch()

    def _load(self):
        s = load_settings()
        self.timeout_spin.setValue(int(s.get("timeout", 10)))
        self.log_lines_spin.setValue(int(s.get("max_log_lines", 100)))

    def _save(self):
        save_settings({
            "timeout": self.timeout_spin.value(),
            "max_log_lines": self.log_lines_spin.value(),
        })
        QMessageBox.information(self, "设置", "已保存")

    def _open_data_dir(self):
        """在系统文件管理器中打开数据目录"""
        try:
            os.startfile(str(DATA_DIR))
        except OSError as e:
            QMessageBox.warning(self, "打开失败", f"无法打开数据目录：{e}")

    def _show_about(self):
        QMessageBox.about(
            self, "关于",
            f"{APP_NAME}\n版本：{VERSION}\n\n"
            "基于MCP工具连接的安全检测工具，用于工具检测、使用、安全鉴定与受控模拟攻击。",
        )