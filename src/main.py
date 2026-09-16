# 项目入口
import os
import runpy
import sys
import traceback
from pathlib import Path

from app_config import APP_NAME, BASE_DIR, DATA_DIR, DEMO_SERVER_FLAG, ICON_PATH


def _log_crash(text: str) -> Path | None:
    """把示范服务器启动期的异常写入 exe 同级 data，便于窗口程序排错"""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        log_path = DATA_DIR / "demo-server-crash.log"
        log_path.write_text(text, encoding="utf-8")
        return log_path
    except Exception:
        return None


def _bind_console() -> None:
    """打包为窗口程序时标准流为空：重新绑定到当前控制台，保证输出与输入可见

    无控制台（如直接双击运行）时退化为空设备，避免 sys.stdout/sys.stdin 为 None
    导致第三方库（如 uvicorn 的日志格式化）访问 isatty 时报错。
    """
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for name, target, mode in (
        ("stdin", "CONIN$", "r"),
        ("stdout", "CONOUT$", "w"),
        ("stderr", "CONOUT$", "w"),
    ):
        if getattr(sys, name, None) is not None:
            continue
        stream = None
        for path in (target, os.devnull):
            try:
                stream = open(path, mode, encoding="utf-8", errors="replace", buffering=1)
                break
            except OSError:
                continue
        if stream is not None:
            setattr(sys, name, stream)


def run_demo_server(script: str) -> int:
    """打包态下由 exe 自兼任服务器宿主：用自带解释器运行随包示范服务器脚本"""
    _bind_console()
    target = Path(script)
    if not target.is_absolute():
        target = BASE_DIR / target
    if not target.exists():
        print(f"未找到示范服务器脚本：{target}")
        _log_crash(f"未找到示范服务器脚本：{target}\nBASE_DIR={BASE_DIR}")
        try:
            input("按回车键关闭窗口...")
        except Exception:
            pass
        return 1
    print(f"启动示范服务器：{target}")
    print(f"运行环境：frozen={bool(getattr(sys, 'frozen', False))}  BASE_DIR={BASE_DIR}  DATA_DIR={DATA_DIR}")
    try:
        runpy.run_path(str(target), run_name="__main__")
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        if code:
            _log_crash(f"服务器以 SystemExit 退出：{e.code}\n脚本：{target}")
        return code
    except BaseException:
        text = f"示范服务器启动失败：{target}\n\n{traceback.format_exc()}"
        print(text)
        log_path = _log_crash(text)
        if log_path:
            print(f"错误详情已写入：{log_path}")
        try:
            input("按回车键关闭窗口...")
        except Exception:
            pass
        return 1
    return 0


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == DEMO_SERVER_FLAG:
        return run_demo_server(sys.argv[2])
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    from gui.main_window import MainWindow
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