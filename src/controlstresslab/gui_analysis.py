"""Optional desktop pages for finite-grid scans and saved experiment overlays."""
from copy import deepcopy
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from .gui_components import StageHeader, Foldout
from .gui_theme import PLOT, style_plot
from . import comparison, robustness
from .experiment import atomic_json, load_result, read_trace


def text(value, muted=False):
    result = QLabel(value)
    result.setWordWrap(True)
    if muted: result.setObjectName("muted")
    return result


def action(title, callback):
    result = QPushButton(title)
    result.clicked.connect(callback)
    return result


def choices(values):
    result = QComboBox()
    for key, label in values.items(): result.addItem(label, key)
    return result


def numbers(value):
    if not value.strip(): raise ValueError("轴取值不能为空")
    return [float(s.strip()) for s in value.split(",")]


def style_axes(ax):
    ax.set_facecolor(PLOT)
    ax.tick_params(colors="#b3bac7")
    ax.xaxis.label.set_color("#b3bac7"); ax.yaxis.label.set_color("#b3bac7")
    ax.title.set_color("#e9edf5")
    for spine in ax.spines.values(): spine.set_color("#343943")


class ScanPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.setObjectName("workspace")
        self.window = window
        self.base = deepcopy(window.config)
        self.base_selected = False
        self.loaded = None
        self._setting = False
        layout = QVBoxLayout(self)
        layout.addWidget(StageHeader("03", "参数压力扫描", "ROBUSTNESS / 冻结控制器 · 扫描工况"))
        self.base_note = text("从实验页载入对象、控制器、信号与评价条件。", True)
        layout.addWidget(self.base_note)
        self.editor = QWidget(); self.editor.setObjectName("controls")
        fields = QGridLayout(self.editor)
        fields.setContentsMargins(0,0,0,0)
        self.x_key = QComboBox(); self.y_key = QComboBox()
        self.x_values = QLineEdit("0.5, 1, 1.5")
        self.y_values = QLineEdit("0, 0.05, 0.1")
        self.second_axis = QCheckBox("启用第二轴"); self.second_axis.setChecked(True)
        self.seeds = QLineEdit("42")
        self.budget = QSpinBox(); self.budget.setRange(1,1000); self.budget.setValue(500)
        fields.addWidget(action("从实验页载入配置", self.use_current_base),0,0)
        fields.addWidget(text("扫描轴 / 逗号分隔实际取值",True),0,1)
        fields.addWidget(self.x_key,1,0); fields.addWidget(self.x_values,1,1)
        fields.addWidget(self.second_axis,2,0); fields.addWidget(self.y_key,2,1); fields.addWidget(self.y_values,2,2)
        fields.addWidget(text("噪声种子",True),1,2); fields.addWidget(self.seeds,1,3)
        fields.addWidget(text("最多运行次数",True),0,2); fields.addWidget(self.budget,0,3)
        self.thresholds = {}
        for column, (key, label, value) in enumerate((("rmse_max","RMSE上限",.25), ("saturation_fraction_max","饱和比例上限",.25), ("input_variation_rate_max","归一化输入变化率上限 /s",1))):
            box = QCheckBox(label); box.setChecked(key != "input_variation_rate_max")
            spin = QDoubleSpinBox(); spin.setDecimals(6); spin.setRange(0,1 if key == "saturation_fraction_max" else 1e6); spin.setValue(value)
            box.toggled.connect(spin.setEnabled); spin.setEnabled(box.isChecked())
            fields.addWidget(box,3,column); fields.addWidget(spin,4,column)
            self.thresholds[key] = (box,spin)
            box.toggled.connect(self.dirty); spin.valueChanged.connect(self.dirty)
        self.start_button = action("开始扫描",self.start)
        self.start_button.setProperty("primary", True)
        fields.addWidget(action("校验并统计次数",self.validate_plan),3,3)
        settings = QWidget(); settings_layout = QVBoxLayout(settings)
        settings_layout.addWidget(self.editor)
        files = QHBoxLayout()
        files.addWidget(action("导入扫描配置",self.import_config))
        files.addWidget(action("保存扫描配置",self.save_config)); files.addStretch()
        settings_layout.addLayout(files)
        self.settings_drawer = Foldout("扫描轴、运行预算与要求", settings, height=285)
        layout.addWidget(self.settings_drawer)
        self.plan_note = text("每个种子共享同一随机噪声基底；波形种子固定。阈值由你事先声明，属于本次实验要求。",True)
        layout.addWidget(self.plan_note)
        controls = QHBoxLayout()
        self.controller = QComboBox()
        self.metric_choice = choices(dict(rmse="RMSE", iae="IAE", input_total_variation="输入总变化量", saturation_fraction="饱和比例", requirement="要求检查"))
        self.seed = QComboBox()
        controls.addWidget(self.start_button); controls.addWidget(text("热力图",True)); controls.addWidget(self.controller); controls.addWidget(self.metric_choice)
        controls.addStretch(); controls.addWidget(text("轨迹种子",True)); controls.addWidget(self.seed)
        controls.addWidget(action("定位最差已完成RMSE工况",self.locate_worst))
        layout.addLayout(controls)
        self.figure = Figure(facecolor=PLOT,layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumHeight(300)
        self.canvas.mpl_connect("button_press_event",self.click_map)
        layout.addWidget(self.canvas,1)
        self.map_note = text("运行后显示离散网格。点击格子可查看该工况下全部控制器的完整轨迹。",True)
        layout.addWidget(self.map_note)
        layout.addWidget(text("格内数值＝声明种子中的最大观察值；任一种子运行失败则数值留空。有限网格不构成鲁棒稳定性证明。",True))
        for w in (self.x_values,self.y_values,self.seeds): w.textChanged.connect(self.dirty)
        for w in (self.x_key,self.y_key): w.currentIndexChanged.connect(self.dirty)
        self.second_axis.toggled.connect(self.dirty)
        self.budget.valueChanged.connect(self.dirty)
        self.controller.currentIndexChanged.connect(self.draw)
        self.metric_choice.currentIndexChanged.connect(self.draw)
        self.set_config(robustness.default_config(self.base))
        ax = self.figure.add_subplot(); ax.set_facecolor(PLOT); ax.set_axis_off()
        ax.text(.5,.5,"运行扫描后，在这里查看压力地图",ha="center",va="center",color="#b3bac7",transform=ax.transAxes,fontsize=16)

    def set_config(self, config):
        self._setting = True
        self.base = deepcopy(config["base"])
        for widget in (self.x_key,self.y_key):
            widget.clear()
            for key,title in robustness.allowed_axes(self.base["model"]).items(): widget.addItem(title,key)
        self.x_key.setCurrentIndex(self.x_key.findData(config["axes"][0]["key"]))
        self.x_values.setText(", ".join(str(x) for x in config["axes"][0]["values"]))
        self.second_axis.setChecked(len(config["axes"]) == 2)
        if len(config["axes"]) == 2:
            self.y_key.setCurrentIndex(self.y_key.findData(config["axes"][1]["key"]))
            self.y_values.setText(", ".join(str(x) for x in config["axes"][1]["values"]))
        self.seeds.setText(",".join(str(x) for x in config["seeds"]))
        self.budget.setValue(config["max_runs"])
        for key,(check,spin) in self.thresholds.items():
            v = config["thresholds"][key]
            check.setChecked(v is not None)
            if v is not None:
                from decimal import Decimal
                spin.setDecimals(min(323,max(6,-Decimal(str(v)).as_tuple().exponent)))
                if v > spin.maximum(): spin.setMaximum(v)
                spin.setValue(v)
        self.base_note.setText("扫描基准："+self.base["model"]+" / "+", ".join(self.base["selected_controllers"])+"；信号、控制器和评价条件来自该基准快照。")
        self._setting = False
        self.dirty()

    def use_current_base(self):
        try:
            config = robustness.default_config(self.window.collect_config())
            self.set_config(config)
            self.base_selected = True
            self.validate_plan()
        except Exception as exc: self.window.error(exc)

    def config(self):
        axes = [dict(key=self.x_key.currentData(),values=numbers(self.x_values.text()))]
        if self.second_axis.isChecked(): axes.append(dict(key=self.y_key.currentData(),values=numbers(self.y_values.text())))
        return dict(schema="robustness-1.0",base=deepcopy(self.base),axes=axes,
            seeds=[int(s.strip()) for s in self.seeds.text().split(",")],max_runs=self.budget.value(),
            thresholds={key:spin.value() if check.isChecked() else None for key,(check,spin) in self.thresholds.items()})

    def dirty(self,*args):
        if self._setting: return
        enabled = self.second_axis.isChecked()
        self.y_key.setEnabled(enabled); self.y_values.setEnabled(enabled)
        if self.loaded: self.plan_note.setText("草稿配置已修改时，现有热力图仍来自已保存扫描；再次运行才生成新结果。")

    def validate_plan(self):
        try:
            config = robustness.validate_config(self.config())
            self.plan_note.setText(f"计划 {robustness.run_count(config)} 次运行；控制器参数冻结；各工况按声明种子配对。全部网格已通过参数校验。")
            return config
        except Exception as exc:
            self.plan_note.setText("配置无效："+str(exc))
            return None

    def start(self):
        if self.window.running: return
        config = self.validate_plan()
        if config is None: self.window.error(self.plan_note.text()); return
        self.window.start_job("robustness",config)

    def save_config(self):
        config = self.validate_plan()
        if config is None: self.window.error(self.plan_note.text()); return
        name,_ = QFileDialog.getSaveFileName(self,"保存扫描配置",str(self.window.workspace/"scan-config.json"),"JSON (*.json)")
        if name:
            try: atomic_json(Path(name),config)
            except Exception as exc: self.window.error(exc)

    def import_config(self):
        if self.window.running: return
        name,_ = QFileDialog.getOpenFileName(self,"导入扫描配置",str(self.window.workspace),"JSON (*.json)")
        if name:
            try:
                config = robustness.validate_config(json.loads(Path(name).read_text(encoding="utf8")))
                self.set_config(config); self.base_selected = True; self.validate_plan()
            except Exception as exc: self.window.error(exc)

    def load_saved(self, loaded):
        from .gui_window import NAMES
        self.loaded = loaded
        self.base_selected = True
        self.saved_config = loaded["manifest"]["config"]
        self.set_config(self.saved_config)
        self.summary = robustness.summarize(loaded["records"],self.saved_config)
        self.controller.blockSignals(True); self.controller.clear()
        for name in self.saved_config["base"]["selected_controllers"]: self.controller.addItem(NAMES.get(name,name),name)
        self.controller.blockSignals(False)
        self.seed.clear()
        for seed in self.saved_config["seeds"]: self.seed.addItem(str(seed),seed)
        self.plan_note.setText("已保存扫描 · "+loaded["verification"]+" · "+loaded["folder"].name)
        self.draw()

    def draw(self,*args):
        if not self.loaded or not self.controller.currentData(): return
        try:
            from .robustness_plots import draw_map
            self.figure.clear()
            self.ax = self.figure.add_subplot()
            image = draw_map(self.ax,self.summary,self.saved_config,self.controller.currentData(),self.metric_choice.currentData())
            style_axes(self.ax)
            self.ax.set_xlabel(robustness.AXIS_LABELS[self.saved_config["axes"][0]["key"]])
            self.ax.set_ylabel(robustness.AXIS_LABELS[self.saved_config["axes"][1]["key"]] if len(self.saved_config["axes"]) == 2 else "单轴扫描")
            bar = self.figure.colorbar(image,ax=self.ax)
            if self.metric_choice.currentData() == "requirement":
                bar.set_ticks([0,1,2,3]); bar.set_ticklabels(["未完成","满足要求","未满足","运行失败"])
            else:
                units = self.loaded["records"][0]["units"]
                suffix = dict(rmse=units["output"],iae=units["output"]+"·s",input_total_variation=units["input"],saturation_fraction="0–1")
                bar.set_label(self.metric_choice.currentText()+" / "+suffix[self.metric_choice.currentData()],color="#b3bac7")
            self.ax.set_title(self.controller.currentText()+" · "+self.metric_choice.currentText()+" · 声明种子中的最大观察值",color="#e9edf5",fontsize=11)
            bar.ax.tick_params(colors="#b3bac7")
            self.map_note.setText("最大观察值覆盖全部声明种子；点击格子后按右侧种子打开轨迹。红色叉线＝运行失败，灰色斜线＝未完成。")
            style_plot(self.figure)
            self.canvas.draw_idle()
        except Exception as exc: self.map_note.setText("绘图失败："+str(exc))

    def click_map(self,event):
        if not self.loaded or event.inaxes != getattr(self,"ax",None) or event.xdata is None: return
        self.locate(round(event.xdata),round(event.ydata),self.seed.currentData())

    def locate(self,x,y,seed):
        records = [r for r in self.loaded["records"] if r["axis_indices"] == [x,y] and r["seed"] == seed]
        if not records:
            self.map_note.setText("该工况/种子尚无完整记录。")
            return
        self.window.open_result(self.loaded["folder"],focus_analysis=False)
        for index,group in enumerate(self.window.record_groups):
            if group[0].get("axis_indices") == [x,y] and group[0].get("seed") == seed:
                self.window.case_selector.setCurrentIndex(index)
                self.window.current_records = group
                self.window.draw_chart()
                break

    def locate_worst(self):
        if not self.loaded: return
        case_id = self.summary["worst_completed_rmse_case"].get(self.controller.currentData())
        record = next((r for r in self.loaded["records"] if r["case_id"] == case_id),None)
        if record is None: self.map_note.setText("没有已完成的有效RMSE工况；运行失败请单独检查。"); return
        self.locate(*record["axis_indices"],record["seed"])


class ComparisonPage(QWidget):
    def __init__(self,window):
        super().__init__()
        self.setObjectName("workspace")
        self.window = window
        self.sources = {}
        self.current = None
        self.snapshot = None
        layout = QVBoxLayout(self)
        layout.addWidget(StageHeader("04", "跨实验对照", "COMPARISON / 同轴轨迹 · 原始指标"))
        layout.addWidget(text("每一行选择一条已保存轨迹，最多8条。图表共用物理坐标，自动列出相对第一条轨迹的变化字段。",True))
        self.editor = QWidget(); self.editor.setObjectName("controls")
        top = QVBoxLayout(self.editor); top.setContentsMargins(0,0,0,0)
        row = QHBoxLayout()
        row.addWidget(action("添加已保存实验",self.choose_source))
        row.addWidget(action("新建对照 / 清空",self.clear))
        row.addWidget(action("指标明细",self.show_metrics))
        row.addWidget(action("变化明细",self.show_differences))
        self.save_button = action("保存完整对照快照",self.save)
        self.save_button.setEnabled(False); row.addWidget(self.save_button); row.addStretch()
        self.channel = choices(dict(output="输出与参考",error="跟踪误差",applied_input="实际输入"))
        self.channel.currentIndexChanged.connect(self.draw)
        row.addWidget(self.channel); top.addLayout(row)
        self.table = QTableWidget(0,3)
        self.table.setHorizontalHeaderLabels(["显示名称","原始工况 / 控制器","操作"])
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(2,85)
        self.table.setMaximumHeight(205)
        self.sources_drawer = Foldout("轨迹来源与显示名称", self.table, height=210)
        top.addWidget(self.sources_drawer)
        layout.addWidget(self.editor)
        self.notice = text("导入时校验完整性；导出时重新校验并复制原始数据。",True)
        layout.addWidget(self.notice)
        self.figure = Figure(facecolor=PLOT,layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure); self.canvas.setMinimumHeight(300)
        layout.addWidget(self.canvas,1)
        self.diffs = text("配置差异会显示在这里。",True)
        self.diffs.setMaximumHeight(120); layout.addWidget(self.diffs)

    def choose_source(self):
        folder = QFileDialog.getExistingDirectory(self,"添加已保存实验",str(self.window.workspace/"experiments"))
        if folder:
            try: self.add_source(Path(folder))
            except Exception as exc: self.window.error(exc)

    def clear(self):
        self.snapshot = None; self.current = None; self.sources.clear(); self.table.setRowCount(0)
        self.figure.clear(); self.canvas.draw_idle(); self.save_button.setEnabled(False)
        self.notice.setText("添加2～8条已校验轨迹。")
        self.diffs.setText("配置差异会显示在这里。")

    def add_source(self,folder,case_id=None,label=None):
        if self.table.rowCount() >= 8: raise ValueError("最多8条轨迹")
        loaded = load_result(folder)
        if loaded["verification"] != "校验通过" or not loaded["status"].get("artifacts_complete") or not loaded["records"]:
            raise ValueError("选择完整且校验通过的通用实验目录")
        if self.snapshot: self.clear()
        folder = loaded["folder"]
        self.sources[str(folder)] = loaded
        row = self.table.rowCount(); self.table.insertRow(row)
        edit = QLineEdit(label or folder.name)
        edit.setToolTip(str(folder)); edit.setProperty("folder",str(folder))
        select = QComboBox(); select.setEditable(True); select.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        for record in loaded["records"]:
            select.addItem(record["controller_name"]+" / "+record["case_id"],record["case_id"])
        if case_id is not None: select.setCurrentIndex(select.findData(case_id))
        else:
            index = next((i for i,r in enumerate(loaded["records"]) if r["controller_name"] == "PID_aw"),0)
            select.setCurrentIndex(index)
        remove = action("移除",lambda: self.remove_row(edit))
        self.table.setCellWidget(row,0,edit); self.table.setCellWidget(row,1,select); self.table.setCellWidget(row,2,remove)
        edit.textChanged.connect(self.refresh); select.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def remove_row(self,edit):
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row,0) is edit: self.table.removeRow(row); break
        self.refresh()

    def entries(self):
        return [dict(folder=self.table.cellWidget(i,0).property("folder"),case_id=self.table.cellWidget(i,1).currentData(),label=self.table.cellWidget(i,0).text()) for i in range(self.table.rowCount())]

    def refresh(self,*args):
        self.snapshot = None
        self.sources_drawer.toggle.setText(f"轨迹来源与显示名称 / {self.table.rowCount()} 条")
        try:
            self.current = comparison.build(self.entries(),cached_sources=self.sources)
            self.notice.setText("；".join(self.current["warnings"]) or "导入时校验通过；指标使用原始保存值，导出前会重新核对来源。")
            pieces = [d["label"]+"："+(", ".join(c["field"] for c in d["changes"]) or "数值配置相同") for d in self.current["differences"]]
            self.diffs.setText("相对首条轨迹的变化字段：\n"+"\n".join(pieces))
            self.diffs.setToolTip(json.dumps(self.current["differences"],indent=2,ensure_ascii=False))
            self.save_button.setEnabled(not self.window.running)
            self.draw()
        except Exception as exc:
            self.current = None; self.save_button.setEnabled(False)
            self.notice.setText(str(exc))
            self.figure.clear(); self.canvas.draw_idle()

    def draw(self,*args):
        from .comparison_plots import draw
        if self.snapshot:
            views = [dict(rows=read_trace(self.snapshot["folder"],r),record=r,label=r["comparison_label"]) for r in self.snapshot["records"]]
        elif self.current:
            views = [dict(rows=v["rows"],record=v["record"],label=v["entry"]["label"]) for v in self.current["views"]]
        else: return
        try:
            draw(self.figure,views,self.channel.currentData(),dark=True)
            style_plot(self.figure)
            self.canvas.draw_idle()
        except Exception as exc: self.notice.setText("图表不可用："+str(exc))

    def save(self):
        if self.window.running or self.current is None: return
        self.window.start_job("comparison",dict(schema="comparison-1.0",entries=self.entries()))

    def show_differences(self):
        if self.snapshot:
            path = self.snapshot["folder"]/"comparison.json"
            summary = json.loads(path.read_text(encoding="utf8")) if path.exists() else {}
        else: summary = self.current or {}
        dialog = QDialog(self); dialog.setWindowTitle("配置变化：相对首条轨迹"); dialog.resize(980,650)
        layout = QVBoxLayout(dialog); content = QTextEdit(); content.setReadOnly(True)
        content.setPlainText(json.dumps({k:summary.get(k,[]) for k in ("differences","warnings")},indent=2,ensure_ascii=False))
        layout.addWidget(content); dialog.exec()

    def show_metrics(self):
        if self.snapshot: records = [(r["comparison_label"],r) for r in self.snapshot["records"]]
        elif self.current: records = [(v["entry"]["label"],v["record"]) for v in self.current["views"]]
        else: return
        dialog = QDialog(self); dialog.setWindowTitle("原始保存指标 · 注意评价窗口和物理单位"); dialog.resize(1180,440)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(len(records),10)
        table.setHorizontalHeaderLabels(["轨迹","状态","RMSE","IAE","输入变化量","饱和比例","评价起点/s","结束/s","恢复状态","终止原因"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for i,(label,record) in enumerate(records):
            m,s = record["metrics"],record["scenario"]
            values = [label,m["status"],m["rmse"],m["iae"],m["input_total_variation"],m["saturation_fraction"],s["evaluation_start_s"],s["duration_s"],m["recovery_status"],m.get("reason","")]
            for j,v in enumerate(values): table.setItem(i,j,QTableWidgetItem("—" if v is None else str(v)))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(table)
        units = records[0][1]["units"]
        layout.addWidget(text("输出单位："+units["output"]+"；输入单位："+units["input"]+"；指标读取原保存值，不重算、不填零。",True))
        dialog.exec()

    def load_saved(self,loaded):
        self.snapshot = loaded
        self.current = None
        self.table.setRowCount(0)
        self.save_button.setEnabled(False)
        self.notice.setText("独立保存的对照快照 · "+loaded["verification"]+"；可从底栏导出完整ZIP。")
        path = loaded["folder"]/"comparison.json"
        summary = json.loads(path.read_text(encoding="utf8")) if path.exists() else {}
        self.diffs.setText("；".join(summary.get("warnings",[])) or "原始指标与来源已保留，打开实验详情查看冻结配置。")
        self.diffs.setToolTip(json.dumps(summary.get("differences",[]),indent=2,ensure_ascii=False))
        self.draw()
