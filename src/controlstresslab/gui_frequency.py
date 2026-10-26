"""Desktop frequency results: frozen sources, large plots and explicit states."""
from copy import deepcopy
import json
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QComboBox,QLabel,QTableWidget,QTableWidgetItem
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from .gui_components import StageHeader,Foldout
from .gui_analysis import action,text
from .gui_theme import PLOT,COLORS,style_plot
from .experiment import sha
from .frequency import default_config,validate_config
from .frequency_plots import draw

class FrequencyPage(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window;self.loaded=None;self.config=default_config();self.setObjectName("workspace")
        layout=QVBoxLayout(self);layout.addWidget(StageHeader("07","采样反馈分析","FREQUENCY / 数字控制器 · 内部极点 · 时域核对"))
        self.editor=QWidget();row=QHBoxLayout(self.editor)
        row.addWidget(action("从实验草稿建立",self.from_current));row.addWidget(action("从当前原始工况建立",self.from_saved))
        self.low=QLineEdit(".01");self.high=QLineEdit("100");self.points=QLineEdit("1024")
        for label,w in (("ω下限",self.low),("ω上限",self.high),("基础点数",self.points)):
            row.addWidget(text(label,True));w.setMaximumWidth(95);row.addWidget(w)
        self.start_button=action("保存并分析",self.start);self.start_button.setProperty("primary",True);row.addWidget(self.start_button)
        layout.addWidget(self.editor)
        self.note=text("先建立配置；LADRC未建立频域模型。全部结论对应未饱和线性分支。",True);self.note.setWordWrap(True);layout.addWidget(self.note)
        tools=QHBoxLayout();self.mode=QComboBox()
        for key,name in (("bode","反馈环路 Bode"),("poles","内部闭环极点"),("sensitivity","灵敏度 S / T"),("channels","参考与扰动通道")):self.mode.addItem(name,key)
        tools.addWidget(self.mode);tools.addStretch();self.summary=text("");self.summary.setWordWrap(True);tools.addWidget(self.summary,1);layout.addLayout(tools)
        self.figure=Figure(facecolor=PLOT,layout="constrained");self.canvas=FigureCanvasQTAgg(self.figure);self.canvas.setMinimumHeight(300);layout.addWidget(self.canvas,1)
        self.details=QTableWidget(0,6);self.details.setHorizontalHeaderLabels(["控制器","交越","ω / rad/s","GM","PM / °","残差"])
        self.drawer=Foldout("检出交越明细 / 数值状态见报告",self.details,height=210);layout.addWidget(self.drawer)
        self.mode.currentIndexChanged.connect(self.draw)
        for w in (self.low,self.high,self.points):w.textChanged.connect(self.dirty)
    def set_config(self,c):
        self.config=deepcopy(c);self.low.setText(str(c["omega_min"]));self.high.setText(str(c["omega_max"]));self.points.setText(str(c["points"]))
        self.note.setText("待分析："+c["base"]["model"]+" / "+", ".join(c["base"]["selected_controllers"])+"；来源："+("冻结原始工况" if c["source"] else "实验草稿"))
    def from_current(self):
        try:self.set_config(default_config(self.window.collect_config()))
        except Exception as exc:self.window.error(exc)
    def from_saved(self):
        try:
            loaded=self.window.loaded
            if not loaded or loaded["verification"]!="校验通过":raise ValueError("请先打开校验通过的原实验或定位一个扫描/候选工况")
            records=self.window.current_records
            if not records and loaded["manifest"]["schema_version"].startswith("tuning-"):
                page=self.window.tuning_page
                records=[r for r in loaded["records"] if r["case_id"]==page.case.currentData()]
            if not records:raise ValueError("当前没有可用于分析的时域工况")
            r=records[0];base=deepcopy(r.get("run_config",loaded["manifest"]["config"]))
            if "schema" not in base or base["schema"]!="experiment-1.0":raise ValueError("当前记录没有完整实验配置")
            c=default_config(base);c["source"]=dict(folder=str(loaded["folder"]),case_id=r["case_id"],
                manifest_sha256=sha(loaded["folder"]/"manifest.json"),producer_version=loaded["manifest"]["package_version"])
            self.set_config(c)
        except Exception as exc:self.window.error(exc)
    def dirty(self):
        if self.loaded:self.note.setText("配置草稿已修改；图表仍来自上一次保存的分析。")
    def start(self):
        if self.window.running:return
        try:
            c=deepcopy(self.config);c.update(omega_min=float(self.low.text()),omega_max=float(self.high.text()),points=int(self.points.text()))
            self.window.start_job("frequency",validate_config(c))
        except Exception as exc:self.window.error(exc)
    def set_busy(self,active):self.editor.setEnabled(not active)
    def load_saved(self,loaded):
        self.loaded=loaded
        from .projects import rebase_frequency
        self.set_config(rebase_frequency(loaded["folder"],loaded["manifest"]["config"]))
        self.records=json.loads((loaded["folder"]/"results.json").read_text(encoding="utf-8")) if (loaded["folder"]/"results.json").exists() else []
        labels={"stable":"内部稳定","unstable":"内部不稳定","boundary":"单位圆边界","numerically_uncertain":"数值不确定"}
        def display(r):
            info=r["summary"]
            def margin(key,unit):
                m=info["margins"][key]
                return format(m["value"],".2f")+unit if m["value"] is not None else "未检出" if m["reason"]=="not_found_in_band" else "数值受限"
            check={"passed":"通过","failed":"失败","not_applicable":"不适用"}[info["time_check"]["state"]]
            return r["controller_name"]+"："+labels[info["internal"]["state"]]+" · GM "+margin("gm","倍")+" / PM "+margin("pm_deg","°")+" · 核对"+check
        self.summary.setText("  |  ".join(display(r) for r in self.records))
        crossings=[dict(controller=r["controller_name"],**v) for r in self.records for v in r["summary"]["crossovers"]];self.details.setRowCount(len(crossings))
        for row,v in enumerate(crossings):
            for col,key in enumerate(("controller","kind","omega_rad_s","gm","pm_deg","residual")):self.details.setItem(row,col,QTableWidgetItem(str(v.get(key) if v.get(key) is not None else "—")))
        self.details.resizeColumnsToContents()
        self.note.setText("冻结分析 · "+loaded["verification"]+"；正裕度不等于稳定性保证。报告保留全部计算状态、矩阵与核对轨迹。")
        self.draw()
    def draw(self):
        if not self.loaded or not getattr(self,"records",None):return
        draw(self.figure,self.loaded["folder"],self.records,self.mode.currentData(),COLORS);style_plot(self.figure);self.canvas.draw_idle()
