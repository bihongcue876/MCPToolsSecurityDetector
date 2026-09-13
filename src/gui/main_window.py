# 主窗口类
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QStatusBar
from PySide6.QtGui import QAction

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

        # 核心管理器（整个应用只创建一次）
        self.config_manager = ConfigManager()
        self.connection = ConnectionManager()
        self.records = RecordsIO()

        # 中央堆叠区
        self.stack = QStackedWidget()
        self.stack.addWidget(WorkspaceMain(
            self.config_manager, self.connection, self.records
        ))
        self.stack.addWidget(WorkspaceSetting())
        self.stack.addWidget(WorkspaceRecord())
        self.setCentralWidget(self.stack)

        # 菜单栏
        self._build_menus()

        # 状态栏
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("就绪")

    def _build_menus(self):
        bar = self.menuBar()

        menu_start = bar.addMenu("开始")
        act_server = QAction("MCP服务器", self)
        act_server.triggered.connect(lambda: self.stack.setCurrentIndex(0))
        menu_start.addAction(act_server)

        menu_settings = bar.addMenu("设置")
        act_settings = QAction("全局设置", self)
        act_settings.triggered.connect(lambda: self.stack.setCurrentIndex(1))
        menu_settings.addAction(act_settings)

        menu_logs = bar.addMenu("日志记录")
        act_logs = QAction("查看日志", self)
        act_logs.triggered.connect(lambda: self.stack.setCurrentIndex(2))
        menu_logs.addAction(act_logs)