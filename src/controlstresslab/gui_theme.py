"""Desktop-only palette; exported reports keep their own scientific style."""
PLOT = "#171e22"
INK = "#edf0e8"
MUTED = "#a8b7bc"
ACCENT = "#d7ec52"
COLORS = ("#6bd7df", "#c5a2f0", "#f0b780", "#84c6a1")


def style_plot(figure):
    """Style existing axes without changing data, limits, or normalization."""
    figure.set_facecolor(PLOT)
    for ax in figure.axes:
        ax.set_facecolor(PLOT)
        ax.tick_params(colors=MUTED, labelsize=10)
        ax.xaxis.label.set_color(MUTED); ax.yaxis.label.set_color(MUTED)
        ax.title.set_color(INK)
        ax._left_title.set_color(INK)
        ax._right_title.set_color(INK)
        for spine in ax.spines.values(): spine.set_color("#3a474d")
        for line in ax.get_xgridlines() + ax.get_ygridlines():
            line.set_color("#465359"); line.set_alpha(.3)
        legend = ax.get_legend()
        if legend:
            legend.get_frame().set_facecolor(PLOT)
            legend.get_frame().set_edgecolor("#3a474d")
            for text in legend.get_texts(): text.set_color(INK)


STYLE = """
QWidget { background: #0e1316; color: #edf0e8; font-family: 'Microsoft YaHei'; font-size: 14px; font-weight: 500; }
QWidget#workspace, QFrame#workspace, QWidget#plotArea { background: #171e22; border: none; border-radius: 0; }
QWidget#controls { background: #20292e; }
QFrame#topbar { background: #0e1316; border-bottom: 1px solid #354148; }
QWidget#library { background: #171e22; border-right: 1px solid #354148; }
QLabel { background: transparent; border: none; }
QLabel#brand { font-size: 25px; font-weight: 900; }
QLabel#section { font-size: 21px; font-weight: 800; }
QLabel#stageTitle { font-size: 29px; font-weight: 900; }
QLabel#eyebrow { color: #acb9b9; font-size: 11px; font-weight: 700; }
QLabel#stageNumber { color: #d7ec52; font-size: 58px; font-weight: 900; }
QLabel#muted { color: #a8b7bc; font-size: 12px; }
QLabel#notice { color: #9ed6d3; font-size: 12px; padding: 3px 0; }
QLabel#badge { color: #d7ec52; background: #273126; border: 1px solid #4e6039; padding: 5px 10px; font-size: 11px; font-weight: 700; }
QLabel[step="active"] { color: #d7ec52; border-bottom: 2px solid #d7ec52; padding: 7px 5px; font-weight: 800; }
QLabel[step="done"] { color: #b8d0cc; border-bottom: 2px solid #55706b; padding: 7px 5px; }
QLabel[step="pending"] { color: #829096; border-bottom: 2px solid #303d43; padding: 7px 5px; }
QPushButton { background: #263137; border: 1px solid #3d4b52; border-radius: 3px; padding: 8px 12px; min-height: 18px; font-weight: 700; }
QPushButton:hover { background: #35434a; border-color: #879b9e; }
QPushButton:pressed { background: #17292f; }
QPushButton:checked { color: #d7ec52; background: #2b3529; border-color: #9eaf50; }
QPushButton:disabled { color: #7e8a90; border-color: #2c373c; background: #20292e; }
QPushButton[primary="true"] { background: #d7ec52; color: #172014; border-color: #d7ec52; font-weight: 900; }
QPushButton[primary="true"]:hover { background: #e7f588; }
QPushButton[primary="true"]:disabled { background: #35402a; border-color: #475236; color: #9aa588; }
QPushButton[nav="true"] { border: none; border-bottom: 2px solid transparent; background: transparent; font-size: 15px; padding: 10px 15px; border-radius: 0; }
QPushButton[nav="true"]:checked { background: #202a2c; color: #d7ec52; border-bottom: 2px solid #d7ec52; }
QPushButton:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus, QLineEdit:focus { border: 2px solid #c5df53; }
QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit, QTextEdit { background: #202a30; border: 1px solid #425058; border-radius: 3px; padding: 6px 8px; min-height: 20px; selection-background-color: #527271; font-weight: 600; }
QComboBox { padding-right: 23px; }
QComboBox QAbstractItemView { background: #263137; color: #edf0e8; selection-background-color: #435652; padding: 5px; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button, QSpinBox::up-button, QSpinBox::down-button { width: 16px; border: none; }
QCheckBox { background: transparent; spacing: 8px; padding: 4px; font-weight: 600; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #7d9395; border-radius: 2px; background: #202a30; }
QCheckBox::indicator:checked { background: #d7ec52; border-color: #d7ec52; }
QListWidget { border: none; background: transparent; outline: none; }
QListWidget::item { padding: 12px; margin: 4px 0; background: #20292e; border: 1px solid transparent; border-radius: 2px; }
QListWidget::item:selected { background: #2b3529; color: #d7ec52; border: 1px solid #92a74b; }
QListWidget::item:hover { border-color: #698077; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #1d272c; width: 9px; margin: 0; }
QScrollBar::handle:vertical { background: #65787c; min-height: 24px; border-radius: 3px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSplitter::handle { background: #35434a; }
QSplitter::handle:vertical { height: 5px; }
QProgressBar { background: #303d43; border: none; height: 6px; max-height: 6px; }
QProgressBar::chunk { background: #d7ec52; }
QTableWidget { background: #171e22; gridline-color: #35434a; border: 1px solid #35434a; alternate-background-color: #202a30; selection-background-color: #40574e; }
QHeaderView::section { background: #28353b; border: none; padding: 9px; color: #c6d1ce; font-weight: 700; }
QTabWidget::pane { border: none; }
QTabBar::tab { padding: 9px 15px; background: #20292e; color: #adbbbc; font-weight: 700; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #d7ec52; background: #2b3529; border-bottom: 2px solid #d7ec52; }
QFrame#inspector, QFrame#inspector QWidget { background: #e9ece5; color: #202b2b; }
QFrame#inspector QLabel#muted, QFrame#inspector QLabel#eyebrow { color: #53615e; }
QFrame#inspector QLabel#candidateId { font-size: 60px; font-weight: 900; color: #202b2b; }
QFrame#inspector QLabel#metricValue { font-size: 25px; font-weight: 800; color: #202b2b; }
QFrame#inspector QLabel#candidateState { font-size: 13px; font-weight: 800; padding: 7px; background: #d5ddd0; }
QFrame#inspector QLabel#candidateState[state="issue"] { background: #ead1bd; color: #723b25; }
QFrame#inspector QLabel#candidateState[state="invalid"] { background: #e9cdd0; color: #71383f; }
QFrame#inspector QComboBox { border: 1px solid #9caaa1; background: #f5f6f0; color: #26332e; }
QFrame#inspector QComboBox QAbstractItemView { background: #f5f6f0; color: #26332e; selection-background-color: #d1debd; }
QFrame#inspector QScrollBar:vertical { background: #d7ded4; }
QFrame#inspector QScrollBar::handle:vertical { background: #8c9d92; }
QFrame#drawer { border-top: 1px solid #435149; background: #20292e; }
QFrame#drawer QWidget { background: #20292e; }
QLabel#metricStrip { font-size: 13px; font-weight: 700; color: #c6d5c8; padding: 10px; background: #202b2c; border-left: 3px solid #d7ec52; }
QDialog { background: #171e22; }
QToolTip { color: #edf0e8; background: #2b3b40; padding: 8px; border: 1px solid #738780; }
"""
