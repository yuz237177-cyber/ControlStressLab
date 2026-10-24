"""Shared desktop palette and optional Qt stylesheet; no Qt imports."""

COLORS = ("#2878ff", "#49cfbc", "#e5aa62", "#ac8cec")
STYLE = """
QWidget { background: #0b0c0e; color: #f2f3f5; font-family: 'Microsoft YaHei'; font-size: 14px; font-weight: 700; }
QFrame#workspace, QWidget#workspace, QWidget#controls { background: #121315; border-radius: 14px; }
QWidget#plotArea { background: #121315; }
QLabel { background: transparent; border: none; }
QLabel#brand { font-size: 27px; }
QLabel#section { font-size: 20px; }
QLabel#muted { color: #b3bac7; font-size: 12px; }
QLabel#notice { color: #8fb5f5; padding: 5px 0; }
QPushButton { background: #1c1e22; border: 1px solid #2b2e34; border-radius: 7px; padding: 8px 12px; min-height: 17px; }
QPushButton:hover { background: #282c34; border-color: #536076; }
QPushButton:pressed { background: #141c2b; }
QPushButton:checked { color: #4b93ff; background: #141c2b; border-color: #315c97; }
QPushButton:disabled { color: #666f7f; border-color: #22262d; background: #171a1f; }
QPushButton[primary="true"] { background: #2878ff; color: white; border-color: #2878ff; }
QPushButton[primary="true"]:hover { background: #4289ff; }
QPushButton[primary="true"]:disabled { background: #263d61; color: #8a99ae; }
QPushButton[nav="true"] { border: none; background: transparent; font-size: 17px; padding: 10px 16px; }
QPushButton[nav="true"]:checked { background: #1a1c21; color: #4b93ff; }
QPushButton:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus, QLineEdit:focus { border: 1px solid #619fff; }
QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit { background: #1a1c20; border: 1px solid #2b2e34; border-radius: 6px; padding: 6px 9px; min-height: 19px; selection-background-color: #2878ff; }
QComboBox QAbstractItemView { background: #1c1e22; selection-background-color: #243956; padding: 5px; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button, QSpinBox::up-button, QSpinBox::down-button { width: 15px; border: none; }
QCheckBox { background: transparent; spacing: 9px; padding: 4px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #617086; border-radius: 4px; background: #1c1e22; }
QCheckBox::indicator:checked { background: #2878ff; border-color: #65a0ff; }
QListWidget { border: none; background: transparent; outline: none; }
QListWidget::item { padding: 12px; margin: 5px 0; background: #121315; border: 1px solid transparent; border-radius: 8px; }
QListWidget::item:selected { background: #111923; color: #4b93ff; border: 1px solid #315c97; }
QListWidget::item:hover { border-color: #3c4654; }
QScrollArea { border: none; background: #121315; }
QScrollBar:vertical { background: #121315; width: 9px; margin: 0; }
QScrollBar::handle:vertical { background: #3c424e; min-height: 24px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSplitter::handle { background: #2b2e34; }
QSplitter::handle:vertical { height: 5px; }
QProgressBar { background: #232831; border: none; border-radius: 4px; height: 7px; max-height: 7px; }
QProgressBar::chunk { background: #2878ff; border-radius: 4px; }
QTableWidget { background: #121315; gridline-color: #303540; border: 1px solid #303540; alternate-background-color: #191d24; selection-background-color: #263e61; }
QHeaderView::section { background: #20242c; border: none; padding: 8px; color: #b3bac7; }
QTabWidget::pane { border: none; }
QTabBar::tab { padding: 8px 14px; background: #1a1c20; }
QTabBar::tab:selected { color: #4b93ff; background: #243145; }
QDialog { background: #121315; }
QToolTip { color: white; background: #243145; padding: 6px; border: 1px solid #50617b; }
"""
