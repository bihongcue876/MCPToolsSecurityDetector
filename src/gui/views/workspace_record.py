# 工作区三：日志记录
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QListWidget
)


class WorkspaceRecord(QWidget):
    """工作区三：日志记录"""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # 顶部筛选
        top = QHBoxLayout()
        top.addWidget(QLabel("日志项目："))
        top.addWidget(QComboBox())
        top.addWidget(QLabel("日期（年-月--年-月）："))
        top.addWidget(QComboBox())
        top.addWidget(QComboBox())
        top.addWidget(QLabel("类型："))
        top.addWidget(QComboBox())
        top.addStretch()
        layout.addLayout(top)

        # 日志内容
        layout.addWidget(QLabel("日志内容"))
        layout.addWidget(QListWidget())