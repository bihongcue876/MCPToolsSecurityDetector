# 工作区二：设置内容
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QFormLayout


class WorkspaceSetting(QWidget):
    """工作区二：全局设置"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("设置"))
        form = QFormLayout()
        form.addRow("默认超时（秒）：", QLineEdit())
        form.addRow("存储目录：", QLineEdit())
        layout.addLayout(form)
        layout.addStretch()