"""Dark, responsive desktop workbench backed by the same paired experiment CLI."""

import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

from PySide6.QtCore import QProcess, QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QFontDatabase
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox,
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSplitter, QStackedWidget,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)

import matplotlib
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from .benchmark_design import DEFAULT_CONFIG, heldout_cases, validate_config as validate_benchmark
from .experiment import (CONTROLLERS, atomic_json, default_config, export_zip, load_result,
    presets, read_trace, saved_reference, scenario_for, validate_config)
from .gui_theme import COLORS, STYLE

MODEL_LABELS = {"first_order": "一阶惯性", "second_order": "二阶振荡"}
NAMES = {"PI": "PI", "PID_aw": "抗饱和 PID", "TwoDOF_PID": "二自由度 PID", "LADRC": "LADRC"}
SIGNALS = {"constant": "常值", "step": "阶跃", "ramp": "斜坡", "sine": "正弦", "triangle": "三角波", "chirp": "扫频", "multistep": "多次阶跃", "pulse": "脉冲", "square": "方波", "prbs": "二值块"}
PARAM_LABELS = {"gain": "增益", "tau_s": "时间常数 / s", "initial_output": "初始输出", "mass_kg": "质量 / kg",
    "damping_N_s_m": "阻尼 / (N·s/m)", "stiffness_N_m": "刚度 / (N/m)", "initial_velocity_m_s": "初始速度 / (m/s)",
    "kp": "kp", "ki": "ki", "kd": "kd", "derivative_filter_s": "微分滤波 / s", "beta": "参考权重 beta",
    "relative_degree": "相对阶次", "b0": "名义输入增益 b0", "control_bandwidth": "控制带宽", "observer_bandwidth": "观察器带宽"}
PARAM_LABELS.update(anti_windup="条件积分抗饱和", offset="直流偏置", frequency_hz="频率 / Hz",
    stop_frequency_hz="扫频终点 / Hz", ramp_duration_s="斜坡时长 / s", pulse_width_s="脉冲宽度 / s", hold_s="二值块时长 / s",
    seed="随机种子", output_bound="输出越界阈值", evaluation_start_s="评价起点 / s", recovery_start_s="恢复计时起点 / s",
    recovery_band="恢复误差带", recovery_dwell_s="带内保持时长 / s", recovery_mode="恢复判定", reference_scale="归一化参考尺度")


def label(text, name=None):
    result = QLabel(text)
    if name: result.setObjectName(name)
    return result


def button(text, callback=None, *, primary=False):
    result = QPushButton(text)
    if primary: result.setProperty("primary", True)
    if callback: result.clicked.connect(callback)
    return result


def number(value=0, low=-1e6, high=1e6, decimals=6):
    widget = QDoubleSpinBox()
    widget.setRange(low, high)
    widget.setDecimals(decimals)
    widget.setValue(value)
    widget.setSingleStep(0.01)
    widget.setKeyboardTracking(False)
    widget.setMinimumWidth(70)
    widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
    return widget


def combo(values):
    widget = QComboBox()
    for key, title in values.items(): widget.addItem(title, key)
    return widget


def hash_config(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


class Workbench(QMainWindow):
    def __init__(self, workspace):
        super().__init__()
        self.workspace = Path(workspace).resolve()
        for name in ("jobs", "experiments", "profiles"):
            (self.workspace / name).mkdir(parents=True, exist_ok=True)
        self.setWindowTitle("ControlStressLab — 桌面实验工作台")
        self.resize(1650, 1000)
        self.setMinimumSize(1080, 720)
        self.config = default_config()
        self.profiles = presets()
        self.loaded = None
        self.current_records = []
        self.trace_cache = {}
        self.running = False
        self._updating = True
        self.result_config_hash = None
        self.process = None
        self.stdout_buffer = b""
        self.last_event = None
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.draw_chart)
        self._build()
        self._load_saved_profiles()
        self._refresh_profiles()
        self.apply_config(self.config)
        self._updating = False

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(22)
        rail = QWidget()
        rail.setFixedWidth(280)
        left = QVBoxLayout(rail)
        left.setContentsMargins(0, 8, 0, 0)
        left.setSpacing(13)
        left.addWidget(label("ControlStressLab", "brand"))
        left.addWidget(label("控制器评测工作台 · v0.4 桌面版", "muted"))
        left.addWidget(label("●  本地实验 / 合成模型", "notice"))
        self.new_button = button("＋ 新建实验配置", self.new_profile)
        left.addWidget(self.new_button)
        row = QHBoxLayout()
        self.import_button = button("导入配置", self.import_config)
        self.open_button = button("打开实验", self.open_experiment)
        row.addWidget(self.import_button)
        row.addWidget(self.open_button)
        left.addLayout(row)
        left.addWidget(label("实验配置", "section"))
        self.profile_list = QListWidget()
        self.profile_list.currentRowChanged.connect(self.select_profile)
        left.addWidget(self.profile_list, 1)
        self.profile_summary = label("一阶惯性 / 2 个控制器", "muted")
        self.profile_summary.setWordWrap(True)
        left.addWidget(self.profile_summary)
        self.sidebar_detail = label("每次运行独立保存原始数据与报告", "muted")
        self.sidebar_detail.setWordWrap(True)
        left.addWidget(self.sidebar_detail)
        left.addSpacing(18)
        left.addWidget(button("使用说明", self.help))
        left.addWidget(label("合成模型 · 未经硬件验证", "muted"))
        outer.addWidget(rail)
        surface = QFrame()
        surface.setObjectName("workspace")
        main = QVBoxLayout(surface)
        main.setContentsMargins(24, 16, 24, 16)
        main.setSpacing(12)
        nav = QHBoxLayout()
        self.nav = QButtonGroup(self)
        for index, title in enumerate(("实验对比", "预算整定", "历史实验")):
            b = button(title)
            b.setCheckable(True)
            b.setProperty("nav", True)
            self.nav.addButton(b, index)
            b.clicked.connect(lambda checked=False, i=index: self.switch_page(i))
            nav.addWidget(b)
        self.nav.button(0).setChecked(True)
        nav.addStretch()
        nav.addWidget(button("实验详情", self.show_details))
        self.report_button = button("打开报告", self.open_report)
        self.report_button.setEnabled(False)
        nav.addWidget(self.report_button)
        main.addLayout(nav)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._experiment_page())
        self.pages.addWidget(self._benchmark_page())
        self.pages.addWidget(self._history_page())
        main.addWidget(self.pages, 1)
        footer = QHBoxLayout()
        self.status_label = label("● 准备就绪", "notice")
        self.status_label.setWordWrap(True)
        footer.addWidget(self.status_label, 1)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(130)
        self.progress.setTextVisible(False)
        self.progress.setValue(0)
        footer.addWidget(self.progress)
        self.save_button = button("保存配置", self.save_config)
        self.export_button = button("导出完整报告", self.export_report)
        self.export_button.setEnabled(False)
        self.run_button = button("▷ 开始对比", self.start_experiment, primary=True)
        footer.addWidget(self.export_button)
        footer.addWidget(self.save_button)
        footer.addWidget(self.run_button)
        main.addLayout(footer)
        outer.addWidget(surface, 1)

    def _experiment_page(self):
        page = QWidget()
        page.setObjectName("workspace")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        response = QWidget()
        response.setObjectName("plotArea")
        top = QVBoxLayout(response)
        top.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.addWidget(label("闭环响应", "section"))
        self.chart_note = label("信号预览 · 开始对比后显示真实响应", "muted")
        heading.addWidget(self.chart_note)
        header.addLayout(heading, 1)
        self.chart_mode = combo(dict(output="输出与参考", error="跟踪误差", applied_input="实际输入", preview="信号预览"))
        self.chart_mode.currentIndexChanged.connect(self.draw_chart)
        header.addWidget(self.chart_mode)
        header.addWidget(button("复位视图", self.draw_chart))
        header.addWidget(button("逐次指标", self.show_metrics))
        header.addWidget(button("保存图片", self.save_chart))
        top.addLayout(header)
        self.case_selector = QComboBox()
        self.case_selector.setVisible(False)
        self.case_selector.currentIndexChanged.connect(self.select_case)
        top.addWidget(self.case_selector)
        matplotlib.rcParams.update({"font.family": ["Microsoft YaHei", "DejaVu Sans"], "axes.unicode_minus": False,
            "font.weight": "bold", "axes.labelweight": "bold", "axes.titleweight": "bold"})
        self.figure = Figure(facecolor="#121315", layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumHeight(250)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.canvas.mpl_connect("scroll_event", self.zoom_chart)
        self.canvas.mpl_connect("pick_event", self.toggle_curve)
        self.canvas.mpl_connect("button_press_event", self.start_pan)
        self.canvas.mpl_connect("button_release_event", lambda event: setattr(self, "pan_origin", None))
        self.canvas.mpl_connect("motion_notify_event", self.pan_chart)
        self.pan_origin = None
        top.addWidget(self.canvas, 1)
        self.metric_strip = label("RMSE  —       IAE  —       输入变化量  —       饱和比例  —       恢复状态  —", "muted")
        self.metric_strip.setWordWrap(True)
        self.metric_strip.setToolTip("指标使用完整轨迹计算；图例可点击隐藏曲线，滚轮缩放，左键拖动平移。")
        top.addWidget(self.metric_strip)
        splitter.addWidget(response)
        self.controls = QWidget()
        self.controls.setObjectName("controls")
        panels = QHBoxLayout(self.controls)
        panels.setContentsMargins(0, 4, 0, 0)
        panels.setSpacing(20)
        self.plant_boxes = {}
        plant_panel = QWidget()
        plant_panel.setObjectName("controls")
        a = QVBoxLayout(plant_panel)
        a.setContentsMargins(0, 0, 0, 0)
        a.addWidget(label("对象与控制器", "section"))
        self.model_choice = combo(MODEL_LABELS)
        self.model_choice.currentIndexChanged.connect(self.switch_model)
        a.addWidget(self.model_choice)
        self.plant_form = QGridLayout()
        a.addLayout(self.plant_form)
        grid = QGridLayout()
        self.controller_checks = {}
        for i, name in enumerate(CONTROLLERS):
            check = QCheckBox(NAMES[name])
            check.toggled.connect(self.mark_dirty)
            self.controller_checks[name] = check
            grid.addWidget(check, i//2, i%2)
        a.addLayout(grid)
        a.addWidget(button("控制器参数…", self.edit_controllers))
        a.addStretch()
        panels.addWidget(plant_panel, 1)
        signal_panel = QWidget()
        signal_panel.setObjectName("controls")
        b = QVBoxLayout(signal_panel)
        b.setContentsMargins(0, 0, 0, 0)
        b.addWidget(label("参考与扰动", "section"))
        self.reference_kind = combo(SIGNALS)
        b.addWidget(self.reference_kind)
        refgrid = QGridLayout()
        self.ref_amplitude, self.ref_start = number(1), number(0.5, 0)
        self._field(refgrid, 0, 0, "参考幅值 / 常值", self.ref_amplitude)
        self._field(refgrid, 0, 1, "起始 / s", self.ref_start)
        b.addLayout(refgrid)
        self.dist_enabled = QCheckBox("启用扰动")
        self.dist_enabled.toggled.connect(self.mark_dirty)
        b.addWidget(self.dist_enabled)
        self.disturbance_kind = combo(SIGNALS)
        b.addWidget(self.disturbance_kind)
        dg = QGridLayout()
        self.dist_amplitude, self.dist_start = number(0.2), number(6, 0)
        self._field(dg, 0, 0, "扰动幅值 / 常值", self.dist_amplitude)
        self._field(dg, 0, 1, "施加 / s", self.dist_start)
        b.addLayout(dg)
        b.addWidget(button("偏置 / 频率 / 波形参数…", self.edit_signals))
        for w in (self.reference_kind, self.disturbance_kind): w.currentIndexChanged.connect(self.mark_dirty)
        for w in (self.ref_amplitude, self.ref_start, self.dist_amplitude, self.dist_start): w.valueChanged.connect(self.mark_dirty)
        b.addStretch()
        panels.addWidget(signal_panel, 1)
        conditions = QWidget()
        conditions.setObjectName("controls")
        c = QVBoxLayout(conditions)
        c.setContentsMargins(0, 0, 0, 0)
        c.addWidget(label("实验条件", "section"))
        grid = QGridLayout()
        self.condition_boxes = {}
        for i, (key, title, low) in enumerate((("dt_s", "采样 / s", 0.000001), ("duration_s", "时长 / s", 0.01),
            ("input_limit", "输入限幅", 0.000001), ("measurement_delay_s", "测量延迟 / s", 0), ("noise_std", "噪声标准差", 0))):
            w = number(0, low)
            self.condition_boxes[key] = w
            self._field(grid, i//2, i%2, title, w)
            w.valueChanged.connect(self.mark_dirty)
        c.addLayout(grid)
        self.units_label = label("输出 / unit；输入 / unit", "muted")
        self.units_label.setWordWrap(True)
        c.addWidget(self.units_label)
        c.addWidget(button("种子 / 评价窗口 / 恢复判据…", self.edit_conditions))
        c.addStretch()
        panels.addWidget(conditions, 1)
        for panel in (plant_panel, signal_panel, conditions):
            panel.setMinimumWidth(240)
            panel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.controls)
        scroll.setMinimumHeight(190)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([600, 265])
        layout.addWidget(splitter, 1)
        self.splitter = splitter
        return page

    def _field(self, grid, row, column, title, widget):
        cell = QWidget()
        cell.setObjectName("controls")
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(label(title, "muted"))
        layout.addWidget(widget)
        grid.addWidget(cell, row, column)

    def _benchmark_page(self):
        page = QWidget()
        page.setObjectName("workspace")
        layout = QVBoxLayout(page)
        layout.addWidget(label("预算整定 · v0.3冻结测试协议", "section"))
        note = label("训练选择 → 参数冻结 → 留出测试 → 报告保存。此页使用既有协议，训练/测试波形和搜索范围固定，不读取实验对比页的自由信号配置。", "muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.benchmark_config = deepcopy(DEFAULT_CONFIG)
        row = QHBoxLayout()
        row.addWidget(button("快速体验", lambda: self.set_benchmark_preset(False)))
        row.addWidget(button("完整1152次实验", lambda: self.set_benchmark_preset(True)))
        row.addStretch()
        layout.addLayout(row)
        self.benchmark_form = QFormLayout()
        self.budget_box = number(4, 1, 128, 0)
        self.benchmark_form.addRow("每对象/算法候选预算（含基线）", self.budget_box)
        self.bench_models = QLineEdit("first_order,second_order")
        self.bench_controllers = QLineEdit(",".join(CONTROLLERS))
        self.bench_seeds = QLineEdit("101")
        self.bench_factors = QLineEdit("1")
        self.bench_search = number(9173, 0, 2**32-1, 0)
        self.bench_rate = number(0.6, 0, 100)
        self.bench_sat = number(0.25, 0, 1)
        for title, w in (("对象（逗号分隔）", self.bench_models), ("控制器（逗号分隔）", self.bench_controllers),
            ("测试种子", self.bench_seeds), ("对象参数因子", self.bench_factors), ("搜索种子", self.bench_search),
            ("训练动作变化率上限 /s", self.bench_rate), ("训练饱和比例上限", self.bench_sat)):
            self.benchmark_form.addRow(title, w)
        layout.addLayout(self.benchmark_form)
        self.benchmark_count = label("", "notice")
        self.benchmark_count.setWordWrap(True)
        layout.addWidget(self.benchmark_count)
        layout.addWidget(button("校验并查看运行次数", self.show_benchmark_count))
        self.benchmark_start = button("开始训练与冻结测试", self.start_benchmark, primary=True)
        layout.addWidget(self.benchmark_start)
        info = label("固定条件：dt=0.01 s、每次12 s；3个训练场景，4族留出测试；同候选数不代表严格公平。测试表现可能退化，约束仅针对训练场景。\n没有可行候选时明确停止，不自动放宽阈值。完整源码范围见已保存的manifest和training日志。", "muted")
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addStretch()
        self.set_benchmark_preset(False)
        return page

    def _history_page(self):
        page = QWidget()
        page.setObjectName("workspace")
        layout = QVBoxLayout(page)
        layout.addWidget(label("历史实验", "section"))
        note = label("打开保存目录读取原指标和单位，不用当前算法重算旧结果。通用实验、覆盖与预算测试可直接画图；早期电机扫描可打开原报告。", "muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        row.addWidget(button("打开实验目录", self.open_experiment))
        row.addWidget(button("刷新本机记录", self.refresh_history))
        layout.addLayout(row)
        self.history = QListWidget()
        self.history.itemDoubleClicked.connect(lambda item: self.open_result(Path(item.data(Qt.ItemDataRole.UserRole))))
        layout.addWidget(self.history, 1)
        self.refresh_history()
        return page

    def _load_saved_profiles(self):
        for p in sorted((self.workspace / "profiles").glob("*.json")):
            try: self.profiles.append(validate_config(json.loads(p.read_text(encoding="utf8"))))
            except Exception: pass

    def _refresh_profiles(self):
        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        for config in self.profiles:
            self.profile_list.addItem(config["name"]+"\n"+MODEL_LABELS[config["model"]]+" / 配置预设")
        self.profile_list.setCurrentRow(0)
        self.profile_list.blockSignals(False)

    def apply_config(self, config):
        config = validate_config(config)
        visible = list(config["plant"].items())
        for name in ("reference", "disturbance"):
            signal = config[name]
            visible.extend(((name+".value", signal["offset"] if signal["kind"] == "constant" else signal["amplitude"]),
                            (name+".start_s", signal["start_s"])))
        visible.extend((k, config["conditions"][k]) for k in self.condition_boxes)
        for key, value in visible:
            if not -1e6 <= value <= 1e6 or round(value, 6) != value:
                raise ValueError(f"{key}超出桌面表单范围（±1000000、6位小数），请使用CLI运行此配置；未更改原值")
        self._updating = True
        self.config = deepcopy(config)
        self.model_choice.setCurrentIndex(self.model_choice.findData(config["model"]))
        while self.plant_form.count():
            item = self.plant_form.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.plant_boxes = {}
        for i, (key, value) in enumerate(config["plant"].items()):
            w = number(value)
            w.valueChanged.connect(self.mark_dirty)
            self.plant_boxes[key] = w
            self._field(self.plant_form, i//2, i%2, PARAM_LABELS.get(key, key), w)
        for name, w in self.controller_checks.items(): w.setChecked(name in config["selected_controllers"])
        for target, source in ((self.reference_kind, config["reference"]), (self.disturbance_kind, config["disturbance"])):
            target.setCurrentIndex(target.findData(source["kind"]))
        self.ref_amplitude.setValue(config["reference"]["offset"] if config["reference"]["kind"] == "constant" else config["reference"]["amplitude"])
        self.ref_start.setValue(config["reference"]["start_s"])
        self.dist_amplitude.setValue(config["disturbance"]["offset"] if config["disturbance"]["kind"] == "constant" else config["disturbance"]["amplitude"])
        self.dist_start.setValue(config["disturbance"]["start_s"])
        self.dist_enabled.setChecked(config["disturbance"]["kind"] != "constant" or config["disturbance"]["offset"] != 0)
        for key, w in self.condition_boxes.items(): w.setValue(config["conditions"][key])
        self.units_label.setText("输出 / m；控制与扰动 / N" if config["model"] == "second_order" else "输出、控制、扰动 / unit")
        self._updating = False
        self.mark_dirty()

    def collect_config(self):
        c = deepcopy(self.config)
        c["plant"] = {k: w.value() for k, w in self.plant_boxes.items()}
        c["selected_controllers"] = [n for n, w in self.controller_checks.items() if w.isChecked()]
        c["reference"].update(kind=self.reference_kind.currentData(), amplitude=self.ref_amplitude.value(), start_s=self.ref_start.value())
        c["disturbance"].update(kind=self.disturbance_kind.currentData(), amplitude=self.dist_amplitude.value(), start_s=self.dist_start.value())
        for key, widget in (("reference", self.ref_amplitude), ("disturbance", self.dist_amplitude)):
            if c[key]["kind"] == "constant":
                c[key].update(offset=widget.value(), amplitude=0)
        if not self.dist_enabled.isChecked(): c["disturbance"].update(kind="constant", amplitude=0, offset=0)
        c["conditions"].update({k: w.value() for k, w in self.condition_boxes.items()})
        return c

    def mark_dirty(self, *args):
        if self._updating: return
        enabled = self.dist_enabled.isChecked()
        for w in (self.disturbance_kind, self.dist_amplitude, self.dist_start): w.setEnabled(enabled)
        self.dist_start.setEnabled(enabled and self.disturbance_kind.currentData() != "constant")
        self.ref_start.setEnabled(self.reference_kind.currentData() != "constant")
        selected = sum(w.isChecked() for w in self.controller_checks.values())
        self.profile_summary.setText(MODEL_LABELS[self.config["model"]]+f" / {selected} 个控制器\n"+self.config["name"])
        if self.loaded:
            self.update_chart_note()
        self.preview_timer.start(250)

    def switch_model(self):
        if self._updating: return
        self.apply_config(default_config(self.model_choice.currentData()))
        self.status_label.setText("已加载所选对象的默认参数；点击开始运行新实验")

    def select_profile(self, row):
        if self.running or not 0 <= row < len(self.profiles): return
        self.apply_config(self.profiles[row])
        self.switch_page(0)

    def new_profile(self):
        if self.running: return
        self.profiles.append(default_config())
        self.profiles[-1]["name"] = "新建实验 "+str(len(self.profiles))
        self._refresh_profiles()
        self.profile_list.setCurrentRow(len(self.profiles)-1)

    def switch_page(self, index):
        self.pages.setCurrentIndex(index)
        self.nav.button(index).setChecked(True)
        self.run_button.setVisible(index != 1 or self.running)
        self.save_button.setVisible(index == 0)
        if index == 2: self.refresh_history()

    def error(self, message):
        self.status_label.setText(str(message)[:200])
        QMessageBox.warning(self, "ControlStressLab", str(message))

    def import_config(self):
        name, _ = QFileDialog.getOpenFileName(self, "导入实验配置", str(self.workspace), "JSON (*.json)")
        if not name: return
        try:
            config = validate_config(json.loads(Path(name).read_text(encoding="utf8")))
            self.profiles.append(config)
            self._refresh_profiles()
            self.profile_list.setCurrentRow(len(self.profiles)-1)
        except Exception as exc: self.error("配置导入失败："+str(exc))

    def save_config(self):
        try: c = validate_config(self.collect_config())
        except Exception as exc: self.error(exc); return
        name, _ = QFileDialog.getSaveFileName(self, "保存实验配置", str(self.workspace / "profiles" / (uuid.uuid4().hex[:8]+".json")), "JSON (*.json)")
        if name:
            try: atomic_json(Path(name), c); self.status_label.setText("配置已保存")
            except Exception as exc: self.error(exc)

    def help(self):
        QMessageBox.information(self, "使用说明", "1. 选择一阶或二阶对象与控制器。\n2. 设置参考、扰动、噪声和测量延迟；高级按钮可修改频率、偏置、随机种子和评价窗口。\n3. 点击开始对比。计算在独立进程中运行，可请求取消。\n4. 滚轮缩放曲线，复位视图恢复；逐次指标可查看全部控制器。\n5. 每次运行自动保留CSV、配置和PNG/SVG；可以打开HTML报告或导出完整ZIP。\n\n全部为合成模型，训练改善不保证测试改善；输入变化量不是能耗。")

    def _dialog(self, title, groups):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(650, 700)
        layout = QVBoxLayout(dialog)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        form = QFormLayout(body)
        widgets = {}
        for group, values in groups.items():
            form.addRow(label(group, "section"))
            for key, value in values.items():
                if isinstance(value, bool):
                    w = QCheckBox(); w.setChecked(value)
                elif isinstance(value, str):
                    w = combo({v: v for v in ("auto", "settling", "tracking_only")})
                    w.setCurrentIndex(w.findData(value))
                else:
                    w = number(value, -1e6, 2**32-1 if key == "seed" else 1e6, 0 if key in ("seed", "relative_degree") else 6)
                    if w.value() != value:
                        self.error(f"{group}.{key}超出本编辑器的范围或精度；保留原值，请使用CLI编辑")
                        return None
                if (group == "PI" and key in ("kd", "anti_windup")) or (group in ("PID_aw", "TwoDOF_PID") and key == "anti_windup"):
                    w.setEnabled(False)
                    w.setToolTip("此参数由控制器定义固定")
                widgets[group, key] = w
                form.addRow(PARAM_LABELS.get(key, key), w)
        scroll.setWidget(body)
        layout.addWidget(scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted: return None
        result = deepcopy(groups)
        for (group, key), w in widgets.items():
            if isinstance(w, QCheckBox): value = w.isChecked()
            elif isinstance(w, QComboBox): value = w.currentData()
            else: value = int(w.value()) if key in ("seed", "relative_degree") else w.value()
            result[group][key] = value
        return result

    def edit_controllers(self):
        c = self.collect_config()
        groups = {x["name"]: x["parameters"] for x in c["controllers"]}
        values = self._dialog("控制器参数（运行前统一校验）", groups)
        if values:
            for x in c["controllers"]: x["parameters"] = values[x["name"]]
            self.config = c
            self.mark_dirty()

    def edit_signals(self):
        c = self.collect_config()
        fields = ("offset", "frequency_hz", "stop_frequency_hz", "ramp_duration_s", "pulse_width_s", "hold_s", "seed")
        groups = {name: {k: c[name][k] for k in fields} for name in ("reference", "disturbance")}
        values = self._dialog("波形参数：offset偏置 / frequency_hz频率 / hold_s二值块时长", groups)
        if values:
            for name, params in values.items(): c[name].update(params)
            self.config = c
            for key, w in (("reference", self.ref_amplitude), ("disturbance", self.dist_amplitude)):
                if c[key]["kind"] == "constant": w.setValue(c[key]["offset"])
            self.mark_dirty()

    def edit_conditions(self):
        c = self.collect_config()
        hidden = {k: v for k, v in c["conditions"].items() if k not in self.condition_boxes}
        values = self._dialog("高级条件：种子、评价与恢复窗口", {"conditions": hidden})
        if values:
            c["conditions"].update(values["conditions"])
            self.config = c
            self.mark_dirty()

    def set_benchmark_preset(self, full):
        c = deepcopy(DEFAULT_CONFIG)
        if not full: c.update(candidate_budget=4, heldout_seeds=[101], parameter_factors=[1.0])
        self.budget_box.setValue(c["candidate_budget"])
        self.bench_models.setText(",".join(c["models"]))
        self.bench_controllers.setText(",".join(c["controllers"]))
        self.bench_seeds.setText(",".join(map(str, c["heldout_seeds"])))
        self.bench_factors.setText(",".join(map(str, c["parameter_factors"])))
        self.bench_search.setValue(c["search_seed"])
        self.bench_rate.setValue(c["max_training_variation_rate"])
        self.bench_sat.setValue(c["max_training_saturation_fraction"])
        self.show_benchmark_count()

    def collect_benchmark(self):
        c = deepcopy(DEFAULT_CONFIG)
        c.update(candidate_budget=int(self.budget_box.value()), search_seed=int(self.bench_search.value()),
            models=[s.strip() for s in self.bench_models.text().split(",")], controllers=[s.strip() for s in self.bench_controllers.text().split(",")],
            heldout_seeds=[int(s.strip()) for s in self.bench_seeds.text().split(",")],
            parameter_factors=[float(s.strip()) for s in self.bench_factors.text().split(",")],
            max_training_variation_rate=self.bench_rate.value(), max_training_saturation_fraction=self.bench_sat.value())
        return validate_benchmark(c)

    def show_benchmark_count(self):
        try:
            c = self.collect_benchmark()
            groups = len(c["models"])*len(c["controllers"])
            train, test = groups*c["candidate_budget"]*3, groups*2*len(heldout_cases(c))
            self.benchmark_count.setText(f"训练 {train} 次 + 冻结测试 {test} 次 = {train+test} 次；每组{c['candidate_budget']}个候选")
        except Exception as exc: self.benchmark_count.setText("配置无效："+str(exc))

    def start_experiment(self):
        if self.running:
            self.cancel_job()
            return
        try:
            config = validate_config(self.collect_config())
            self.start_job("experiment", config)
        except Exception as exc: self.error(exc)

    def start_benchmark(self):
        if self.running: return
        try: self.start_job("benchmark", self.collect_benchmark())
        except Exception as exc: self.error(exc)

    def start_job(self, kind, config):
        if self.running: raise ValueError("已有一个任务正在运行")
        identifier = datetime.now().strftime("%Y%m%d-%H%M%S")+"-"+uuid.uuid4().hex[:6]
        self.job_output = self.workspace / "experiments" / identifier
        if kind == "export": self.job_output = Path(config["folder"])
        request = self.workspace / "jobs" / (identifier+".request.json")
        self.cancel_path = self.workspace / "jobs" / (identifier+".cancel")
        job_status = self.workspace / "jobs" / (identifier+".status.json")
        atomic_json(request, dict(kind=kind, config=config))
        self.job_kind = kind
        self.active_config_hash = hash_config(config)
        self.last_event = None
        self.stdout_buffer = b""
        self.process = QProcess(self)
        worker_python = Path(sys.executable)
        if worker_python.name.lower() == "pythonw.exe": worker_python = worker_python.with_name("python.exe")
        self.process.setProgram(str(worker_python))
        self.process.setArguments(["-m", "controlstresslab.gui_worker", "--request", str(request), "--output", str(self.job_output),
                                   "--cancel", str(self.cancel_path), "--job-status", str(job_status)])
        self.process.readyReadStandardOutput.connect(self.read_events)
        self.log_path = self.workspace / "jobs" / (identifier+".log")
        self.process.readyReadStandardError.connect(self.read_log)
        self.process.finished.connect(self.job_finished)
        self.process.errorOccurred.connect(self.process_error)
        self.set_running(True)
        self.process.start()

    def set_running(self, active):
        self.running = active
        self.controls.setEnabled(not active)
        self.profile_list.setEnabled(not active)
        for w in (self.new_button, self.import_button, self.save_button, self.benchmark_start): w.setEnabled(not active)
        self.run_button.setVisible(True)
        self.run_button.setText("取消运行" if active else "▷ 开始对比")
        self.progress.setRange(0, 0 if active else 100)
        if not active: self.progress.setValue(0)
        if active: self.status_label.setText("正在校验并启动独立计算进程…")

    def read_log(self):
        data = bytes(self.process.readAllStandardError())
        with self.log_path.open("ab") as stream: stream.write(data)

    def read_events(self):
        self.stdout_buffer += bytes(self.process.readAllStandardOutput())
        while b"\n" in self.stdout_buffer:
            raw, self.stdout_buffer = self.stdout_buffer.split(b"\n", 1)
            try: event = json.loads(raw)
            except (ValueError, UnicodeError): continue
            self.last_event = event
            if event.get("event") == "finished": continue
            done, total = event.get("written", 0), event.get("expected", 0)
            self.progress.setRange(0, max(total, 1))
            self.progress.setValue(done)
            self.status_label.setText(event.get("stage", "运行中")+f" · {done}/{total}")

    def cancel_job(self):
        if self.running:
            self.cancel_path.write_text("cancel", encoding="ascii")
            self.status_label.setText("已请求取消，等待当前运行/保存检查点；已有记录保留")
            self.run_button.setEnabled(False)

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.set_running(False)
            self.run_button.setEnabled(True)
            self.error("无法启动计算进程："+self.process.errorString())

    def job_finished(self, exit_code, exit_status):
        self.read_events()
        self.read_log()
        self.set_running(False)
        self.run_button.setEnabled(True)
        final = self.last_event or {}
        state = final.get("state", "failed")
        if state in ("completed", "completed_with_failures"):
            try:
                self.result_config_hash = self.active_config_hash if self.job_kind == "experiment" else None
                self.open_result(self.job_output)
                self.status_label.setText("完成，全部数据与图表已保存" if state == "completed" else "完成，但含运行失败；查看逐次指标")
                self.progress.setValue(100)
            except Exception as exc: self.error("任务结束，但读取结果失败："+str(exc))
        elif state in ("cancelled", "interrupted"):
            self.status_label.setText("任务已取消/中断，已有数据保留："+self.job_output.name)
        else:
            self.error(final.get("message", "计算进程异常结束；详细信息保存在任务日志："+str(self.log_path)))
        self.refresh_history()

    def refresh_history(self):
        self.history.clear()
        paths = list((self.workspace / "experiments").iterdir())
        for p in sorted(paths, reverse=True):
            if not (p / "status.json").is_file(): continue
            try:
                state = json.loads((p / "status.json").read_text(encoding="utf8"))
                name = p.name+"  /  "+state["state"]
            except (OSError, ValueError, KeyError): name = p.name+" / 状态文件不可读"
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, str(p))
            self.history.addItem(item)

    def open_experiment(self):
        name = QFileDialog.getExistingDirectory(self, "打开已保存实验", str(self.workspace / "experiments"))
        if name:
            try: self.open_result(Path(name))
            except Exception as exc: self.error("读取失败："+str(exc))

    def open_result(self, folder):
        loaded = load_result(folder)
        self.loaded = loaded
        self.trace_cache = {}
        self.case_selector.blockSignals(True)
        self.case_selector.clear()
        groups = {}
        for record in loaded["records"]:
            key = (record["model_name"], record.get("subset", ""), record.get("family", record.get("scenario_name", record["scenario"]["name"])),
                   record.get("parameter_factor", ""), record.get("seed", ""))
            groups.setdefault(key, []).append(record)
        self.record_groups = list(groups.values())
        for key in groups: self.case_selector.addItem(" / ".join(str(x) for x in key if x != ""))
        self.case_selector.setVisible(len(groups) > 1)
        self.case_selector.blockSignals(False)
        self.current_records = self.record_groups[0] if self.record_groups else []
        saved = loaded["manifest"].get("config")
        self.result_config_hash = hash_config(saved) if loaded["manifest"].get("schema_version") == "experiment-1.0" else None
        complete = loaded["status"].get("artifacts_complete", False)
        self.report_button.setEnabled((loaded["folder"] / "report.html").is_file())
        self.export_button.setEnabled(complete and loaded["verification"] == "校验通过")
        self.update_chart_note()
        if self.current_records:
            self.switch_page(0)
            self.chart_mode.setCurrentIndex(self.chart_mode.findData("output"))
            self.draw_chart()
        else:
            self.status_label.setText("历史格式可查看原HTML报告；"+loaded["verification"])
            self.figure.clear()
            ax = self.figure.add_subplot()
            ax.set_facecolor("#121315")
            ax.text(.5, .5, "此历史格式请点击“打开报告”查看原始结果", ha="center", color="#b3bac7", transform=ax.transAxes)
            ax.set_axis_off()
            self.metric_strip.setText("历史报告使用原始单位与原始指标")
            self.canvas.draw_idle()

    def update_chart_note(self):
        text = "已保存实验 · "+self.loaded["verification"]+" · "+self.loaded["folder"].name
        if self.result_config_hash and hash_config(self.collect_config()) != self.result_config_hash:
            text += " · 草稿已修改，响应仍为原结果"
        if self.loaded["problems"]: text += " · 存在缺失/损坏文件"
        self.chart_note.setText(text)
        self.chart_note.setToolTip(text)

    def select_case(self, index):
        if hasattr(self, "record_groups") and 0 <= index < len(self.record_groups):
            self.current_records = self.record_groups[index]
            self.draw_chart()

    def _trace(self, record):
        key = record["trace_file"]
        if key not in self.trace_cache: self.trace_cache[key] = read_trace(self.loaded["folder"], record)
        return self.trace_cache[key]

    def draw_chart(self, *args):
        if self._updating: return
        self.figure.clear()
        self.ax = self.figure.add_subplot()
        ax = self.ax
        ax.set_facecolor("#121315")
        for spine in ax.spines.values(): spine.set_color("#343943")
        ax.tick_params(colors="#b3bac7", labelsize=10)
        ax.xaxis.label.set_color("#b3bac7")
        ax.yaxis.label.set_color("#b3bac7")
        ax.grid(color="#252a33", lw=0.7)
        channel = self.chart_mode.currentData()
        try:
            if not self.loaded or channel == "preview" or not self.current_records:
                c = validate_config(self.collect_config())
                s = scenario_for(c)
                times = [i*s.dt_s for i in range(len(s.reference.values))]
                step = max(1, len(times)//5000)
                ax.step(times[::step], s.reference.values[::step], where="post", color="#b3bac7", label="参考信号", lw=2)
                other = ax.twinx()
                other.set_facecolor("#121315")
                other.step(times[::step], s.load.values[::step], where="post", color=COLORS[1], label="扰动信号", lw=1.5)
                other.tick_params(colors=COLORS[1], labelsize=9)
                other.set_ylabel("扰动 / "+("N" if c["model"] == "second_order" else "unit"), color=COLORS[1])
                for spine in other.spines.values(): spine.set_color("#343943")
                ax.set_ylabel("参考 / "+("m" if c["model"] == "second_order" else "unit"))
                ax.set_title("信号预览 · 尚未使用此配置运行响应", color="#b3bac7", fontsize=11, pad=12)
                self.metric_strip.setText("RMSE  —       IAE  —       输入变化量  —       饱和比例  —       恢复状态  —")
            else:
                for record in self.current_records:
                    rows = self._trace(record)
                    step = max(1, len(rows)//8000)
                    selected = rows[::step]
                    name = record["controller_name"]
                    text = NAMES.get(name, name)+(f" · {record['phase']}" if "phase" in record else "")
                    color = COLORS[list(CONTROLLERS).index(name)]
                    y = [r["reference"]-r["output"] if channel == "error" and r["output"] is not None else r.get(channel) for r in selected]
                    ax.plot([r["time_s"] for r in selected], y, color=color, lw=2.2,
                            ls="--" if record.get("phase") == "baseline" else "-", label=text)
                if channel == "output":
                    reference_x, reference_y = saved_reference(self.current_records[0])
                    step = max(1, len(reference_x)//8000)
                    ax.step(reference_x[::step], reference_y[::step], where="post", color="#abb2bf", ls="--", label="参考", lw=1.4)
                ax.set_xlim(0, self.current_records[0]["scenario"]["duration_s"])
                units = self.current_records[0]["units"]
                ax.set_ylabel(("实际输入 / "+units["input"]) if channel == "applied_input" else ("跟踪误差 / " if channel == "error" else "输出 / ")+units["output"])
                self.update_metric_strip()
            if channel == "preview" and self.loaded:
                self.chart_note.setText("当前草稿的信号预览 · 指标与响应仍保存在原实验中")
            elif self.loaded:
                self.update_chart_note()
            ax.set_xlabel("时间 / s")
            handles, names = [], []
            for axes in self.figure.axes:
                h, n = axes.get_legend_handles_labels()
                handles.extend(h); names.extend(n)
            legend = ax.legend(handles, names, loc="upper center", ncols=min(4, len(names)), facecolor="#1b1f27", edgecolor="#343943", labelcolor="#d9deea", fontsize=10)
            self.legend_sources = dict(zip(legend.get_lines(), handles))
            for item in self.legend_sources: item.set_picker(6)
        except Exception as exc:
            ax.text(0.5, 0.5, "配置或数据不可用\n"+str(exc), transform=ax.transAxes, ha="center", va="center", color="#e9b275", wrap=True)
        self.canvas.draw_idle()

    def zoom_chart(self, event):
        if event.inaxes != getattr(self, "ax", None) or event.xdata is None: return
        factor = 0.8 if event.button == "up" else 1.25
        ax = self.ax
        ax.set_xlim([event.xdata+(x-event.xdata)*factor for x in ax.get_xlim()])
        ax.set_ylim([event.ydata+(y-event.ydata)*factor for y in ax.get_ylim()])
        self.canvas.draw_idle()

    def toggle_curve(self, event):
        source = getattr(self, "legend_sources", {}).get(event.artist)
        if source is not None:
            source.set_visible(not source.get_visible())
            event.artist.set_alpha(1 if source.get_visible() else .25)
            self.canvas.draw_idle()

    def start_pan(self, event):
        if event.inaxes == getattr(self, "ax", None) and event.button == 1:
            self.pan_origin = (event.x, event.y, self.ax.get_xlim(), self.ax.get_ylim())

    def pan_chart(self, event):
        if not self.pan_origin or event.inaxes != self.ax: return
        x, y, limits_x, limits_y = self.pan_origin
        dx = (event.x-x)/self.ax.bbox.width*(limits_x[1]-limits_x[0])
        dy = (event.y-y)/self.ax.bbox.height*(limits_y[1]-limits_y[0])
        self.ax.set_xlim([v-dx for v in limits_x]); self.ax.set_ylim([v-dy for v in limits_y])
        self.canvas.draw_idle()

    def show_details(self):
        if not self.loaded:
            data = dict(note="当前配置草稿，尚未运行", config=self.collect_config())
        else:
            data = dict(folder=str(self.loaded["folder"]), verification=self.loaded["verification"],
                status=self.loaded["status"], manifest=self.loaded["manifest"])
        dialog = QDialog(self)
        dialog.setWindowTitle("实际配置与实验来源")
        dialog.resize(900, 680)
        layout = QVBoxLayout(dialog)
        text = QTextEdit(); text.setReadOnly(True)
        text.setPlainText(json.dumps(data, indent=2, ensure_ascii=False))
        layout.addWidget(text)
        dialog.exec()

    def update_metric_strip(self):
        def span(key, percent=False):
            values = [r["metrics"].get(key) for r in self.current_records if r["metrics"].get(key) is not None]
            if not values: return "不适用 / 无有效值"
            a, b = min(values), max(values)
            if percent: a, b = a*100, b*100
            return (f"{a:.4g}" if a == b else f"{a:.4g}–{b:.4g}")+("%" if percent else "")
        self.metric_strip.setText("本组范围（逐控制器见明细）  ·  RMSE "+span("rmse")+"    IAE "+span("iae")+
            "    输入变化量 "+span("input_total_variation")+"    饱和 "+span("saturation_fraction", True))

    def show_metrics(self):
        if not self.current_records:
            QMessageBox.information(self, "逐次指标", "先运行实验，或打开已有结果。")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("逐次指标：原始保存值，失败不计为零")
        dialog.resize(1160, 480)
        layout = QVBoxLayout(dialog)
        columns = ("控制器", "阶段", "执行状态", "RMSE", "IAE", "输入变化量", "饱和比例", "恢复时间 /s", "恢复状态", "终止原因")
        table = QTableWidget(len(self.current_records), len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for i, record in enumerate(self.current_records):
            m = record["metrics"]
            values = [NAMES.get(record["controller_name"], record["controller_name"]), record.get("phase", "固定参数"), m["status"],
                m["rmse"], m["iae"], m["input_total_variation"], m["saturation_fraction"], m["recovery_time_s"], m["recovery_status"], m.get("reason", "")]
            for j, value in enumerate(values): table.setItem(i, j, QTableWidgetItem("—" if value is None else str(value)))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(table)
        layout.addWidget(label("误差基于真实模型输出；输入变化量不是能耗，恢复时间不是稳定性证明。", "muted"))
        dialog.exec()

    def save_chart(self):
        name, _ = QFileDialog.getSaveFileName(self, "保存当前图", str(self.workspace / "response.png"), "PNG (*.png);;SVG (*.svg)")
        if name:
            try: self.figure.savefig(name, dpi=180, facecolor=self.figure.get_facecolor()); self.status_label.setText("当前图片已保存")
            except Exception as exc: self.error(exc)

    def open_report(self):
        if self.loaded: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.loaded["folder"] / "report.html")))

    def export_report(self):
        if not self.loaded: return
        folder = self.loaded["folder"]
        name, _ = QFileDialog.getSaveFileName(self, "导出完整报告ZIP（不会覆盖已有文件）", str(folder.with_name(folder.name+".zip")), "ZIP (*.zip)")
        if not name: return
        try: self.start_job("export", dict(folder=str(folder), destination=name))
        except Exception as exc: self.error(exc)

    def closeEvent(self, event):
        if self.running:
            self.cancel_job()
            QMessageBox.information(self, "正在结束任务", "已请求取消。请等待当前运行/保存结束后再次关闭窗口；已有数据会保留。")
            event.ignore()
        else:
            event.accept()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd() / "outputs/gui")
    parser.add_argument("--open", type=Path, help="打开已保存的实验目录")
    args = parser.parse_args()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    # Also supplies glyphs to offscreen QA on Windows.
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name in ("msyh.ttc", "msyhbd.ttc"):
        if (fonts / name).is_file(): QFontDatabase.addApplicationFont(str(fonts / name))
    app.setApplicationName("ControlStressLab")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    font = QFont("Microsoft YaHei")
    font.setPixelSize(14)
    font.setWeight(QFont.Weight.Bold)
    app.setFont(font)
    window = Workbench(args.workspace)
    screen = app.primaryScreen().availableGeometry()
    window.resize(min(1750, screen.width()-40), min(1060, screen.height()-60))
    window.show()
    if args.open:
        try:
            saved = load_result(args.open)
            if saved["manifest"].get("schema_version") == "experiment-1.0":
                window.apply_config(saved["manifest"]["config"])
            window.open_result(args.open)
        except Exception as exc: window.error(exc)
    raise SystemExit(app.exec())


if __name__ == "__main__": main()
