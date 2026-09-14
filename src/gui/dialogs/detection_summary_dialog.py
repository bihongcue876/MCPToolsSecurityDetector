# 检测概要弹窗
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QDialogButtonBox
)


class DetectionSummaryDialog(QDialog):
    """按组显示检测概要：通过/警告/失败/跳过数量"""
    def __init__(self, results, parent=None):
        super().__init__(parent)
        self.setWindowTitle("检测概要")
        self.resize(400, 300)
        layout = QVBoxLayout(self)

        if not results:
            layout.addWidget(QLabel("无检测结果"))
        else:
            groups: dict[str, list] = {}
            for r in results:
                groups.setdefault(r.module, []).append(r)
            for mod in sorted(groups.keys()):
                items = groups[mod]
                pass_n = sum(1 for r in items if r.status == "pass")
                warn_n = sum(1 for r in items if r.status == "warn")
                fail_n = sum(1 for r in items if r.status == "fail")
                skip_n = sum(1 for r in items if r.status == "skip")
                text = f"{mod}组：通过{pass_n}，警告{warn_n}，失败{fail_n}"
                if skip_n:
                    text += f"，跳过{skip_n}"
                layout.addWidget(QLabel(text))

        layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)