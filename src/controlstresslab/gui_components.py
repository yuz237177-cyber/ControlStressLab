"""Original code-drawn desktop elements; no third-party artwork."""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPolygonF
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget)


class StageHeader(QWidget):
    def __init__(self, number, title, caption, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(84)
        layout = QHBoxLayout(self); layout.setContentsMargins(2, 5, 18, 5)
        heading = QVBoxLayout(); heading.setSpacing(3)
        eyebrow = QLabel(caption); eyebrow.setObjectName("eyebrow")
        name = QLabel(title); name.setObjectName("stageTitle"); self.title_label = name
        heading.addWidget(eyebrow); heading.addWidget(name)
        layout.addLayout(heading, 1)
        serial = QLabel(number); serial.setObjectName("stageNumber"); self.serial_label = serial
        layout.addWidget(serial)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_compact(self, compact):
        self.setMinimumHeight(50 if compact else 84)
        self.setMaximumHeight(56 if compact else 92)
        self.title_label.setStyleSheet("font-size: 23px;" if compact else "")
        self.serial_label.setStyleSheet("font-size: 38px;" if compact else "")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor("#242e32"))
        painter.drawPolygon(QPolygonF([QPointF(w-210, 0), QPointF(w-65, 0),
            QPointF(w-105, h), QPointF(w-250, h)]))
        painter.setPen(QColor("#3c4b50")); painter.drawLine(0, h-1, w, h-1)


class Foldout(QFrame):
    """Bounded scroll panel that gives space back to the main graph."""
    def __init__(self, title, content, *, expanded=False, height=290, parent=None):
        super().__init__(parent)
        self.setObjectName("drawer")
        layout = QVBoxLayout(self); layout.setContentsMargins(10, 5, 10, 7)
        layout.setSpacing(5)
        self.toggle = QPushButton(title); self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.toggle.setToolTip("展开查看或编辑；收起后保留当前配置。")
        self.toggle.setAccessibleName(title)
        row = QHBoxLayout(); row.addWidget(self.toggle)
        self.hint = QLabel("点击展开"); self.hint.setObjectName("muted")
        row.addStretch(); row.addWidget(self.hint); layout.addLayout(row)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(content); self.scroll.setMaximumHeight(height)
        self.scroll.setMinimumHeight(min(210, height)); layout.addWidget(self.scroll)
        self.toggle.toggled.connect(self.set_expanded)
        self.set_expanded(expanded)

    def set_expanded(self, expanded):
        self.scroll.setVisible(expanded)
        self.hint.setText("再次点击收起" if expanded else "点击展开")
        if self.toggle.isChecked() != expanded: self.toggle.setChecked(expanded)
        self.updateGeometry()

