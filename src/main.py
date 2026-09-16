# 项目入口
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from app_config import ICON_PATH, APP_NAME
from gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(ICON_PATH)))
    if sys.platform == "win32":
        import ctypes
        app_id = f"{APP_NAME}.mcp-security-detector"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    window = MainWindow()
    window.setWindowIcon(app.windowIcon())
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())