# 项目入口
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from app_config import ICON_PATH
from gui.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(ICON_PATH)))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())