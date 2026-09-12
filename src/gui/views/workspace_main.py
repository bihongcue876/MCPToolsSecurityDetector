# 主要功能窗口
# 工作区一：MCP 服务器（左侧列表 + 右侧选项卡）
from PySide6.QtWidgets import (
    QWidget, QSplitter, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QLineEdit, QTextEdit,
    QComboBox, QFormLayout
) # 相关组件
from PySide6.QtCore import Qt


class WorkspaceMain(QWidget):
    """工作区一：MCP 服务器管理"""

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        # 整体左右分栏
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ---- 左侧：服务器列表 ----
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.server_list = QListWidget()
        btn_add = QPushButton("添加  (+)")
        left_layout.addWidget(QLabel("服务器列表"))
        left_layout.addWidget(self.server_list)
        left_layout.addWidget(btn_add)

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

    def _build_tab_config(self) -> QWidget:
        """[配置] 子页：表单 + JSON 区 + 按钮"""
        w = QWidget()
        layout = QVBoxLayout(w)

        # 上方表单
        form = QFormLayout()
        form.addRow("名称：", QLineEdit())
        form.addRow("传输：", QComboBox())
        form.addRow("地址：", QLineEdit())
        layout.addLayout(form)

        # 中间 JSON 展示/编辑
        layout.addWidget(QLabel("配套 JSON："))
        layout.addWidget(QTextEdit())

        # 底部操作按钮
        btn_row = QHBoxLayout()
        btn_row.addWidget(QPushButton("保存"))
        btn_row.addWidget(QPushButton("测试连接"))
        btn_row.addStretch()
        layout.addLayout(btn_row)
        return w

    def _build_tab_overview(self) -> QWidget:
        """[概览] 子页：工具列表 + 工具测试"""
        w = QWidget()
        layout = QHBoxLayout(w)

        # 左侧：详情/工具列表
        left = QVBoxLayout()
        left.addWidget(QLabel("工具列表"))
        left.addWidget(QListWidget())
        layout.addLayout(left, 1)

        # 右侧：工具测试
        right = QVBoxLayout()
        right.addWidget(QLabel("工具测试"))
        right.addWidget(QComboBox()) # 工具可选
        right.addWidget(QLabel("输入："))
        right.addWidget(QTextEdit())
        right.addWidget(QLabel("输出："))
        right.addWidget(QTextEdit())
        right.addWidget(QPushButton("执行"))
        layout.addLayout(right, 2)
        return w

    def _build_tab_scan(self) -> QWidget:
        """[鉴别] 子页：测试 A / B / 模拟攻击"""
        w = QWidget()
        layout = QVBoxLayout(w)

        layout.addWidget(QLabel("测试 A："))
        layout.addWidget(QTextEdit("描述与情况……"))
        layout.addWidget(QLabel("测试 B："))
        layout.addWidget(QTextEdit("描述与情况……"))
        layout.addWidget(QLabel("模拟攻击："))
        layout.addWidget(QTextEdit("配置……"))

        btn_row = QHBoxLayout()
        btn_row.addWidget(QPushButton("测试（含还原）"))
        btn_row.addStretch()
        layout.addLayout(btn_row)
        return w