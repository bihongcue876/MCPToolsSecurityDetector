# 主窗口类
from PySide6.QtWidgets import (
    QMainWindow, QStackedWidget, QStatusBar, QToolBar
)
from PySide6.QtGui import QAction, QActionGroup

from gui.views.workspace_main import WorkspaceMain
from gui.views.workspace_setting import WorkspaceSetting
from gui.views.workspace_record import WorkspaceRecord

from core.connection import ConnectionManager
from data.config_manager import ConfigManager
from data.records_io import RecordsIO


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MCP 安全检测")
        self.resize(1000, 640)

        # 核心管理器
        self.config_manager = ConfigManager()
        self.connection = ConnectionManager()
        self.records = RecordsIO()

        # 中央堆叠区
        self.stack = QStackedWidget()
        self.stack.addWidget(WorkspaceMain(
            self.config_manager, self.connection, self.records
        ))
        self.stack.addWidget(WorkspaceSetting())
        self.stack.addWidget(WorkspaceRecord(self.records))
        self.setCentralWidget(self.stack)

        # 顶部工具栏（代替菜单栏，点击即切换）
        self._build_toolbar()

        # 状态栏
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("就绪")

    def _build_toolbar(self):
        tb = QToolBar("主工具栏")
        tb.setMovable(False)
        tb.setFloatable(False)
        self.addToolBar(tb)

        # 用 QActionGroup 让当前页按钮保持按下态
        group = QActionGroup(self)
        group.setExclusive(True)

        for idx, label in enumerate(["开始", "设置", "日志记录"]):
            act = QAction(label, self)
            act.setCheckable(True)
            act.triggered.connect(lambda checked=False, i=idx: self.stack.setCurrentIndex(i))
            group.addAction(act)
            tb.addAction(act)
            if idx == 0:
                act.setChecked(True)