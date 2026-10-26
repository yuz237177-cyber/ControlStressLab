"""Model-definition editor with a saved, worker-backed open-loop preview."""
from copy import deepcopy
import csv
import json
from pathlib import Path
from PySide6.QtWidgets import (QCheckBox,QComboBox,QFileDialog,QFormLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QVBoxLayout,QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from .gui_analysis import action,text
from .gui_components import StageHeader,Foldout
from .gui_theme import PLOT,COLORS,style_plot
from .linear_models import default_plant,template,validate_plant
from .experiment import atomic_json,default_config,validate_config


def array(edit):
    value=edit.text().strip()
    if value.startswith("["):return json.loads(value)
    return [float(v.strip()) for v in value.replace("，",",").split(",")]


class ModelPage(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window;self.loaded=None;self.setObjectName("workspace")
        layout=QVBoxLayout(self);layout.addWidget(StageHeader("06","通用模型工作台","MODEL / 传递函数 · 明确通道 · 模型快照"))
        row=QHBoxLayout();self.templates=QComboBox()
        for key,name in (("first_order","一阶模板"),("second_order","二阶模板"),("integrator","积分对象"),("fourth_order","四阶对象")):self.templates.addItem(name,key)
        self.template_button=action("载入模板",self.use_template);self.import_button=action("导入模型",self.import_model)
        self.save_button=action("保存模型",self.save_model)
        for w in (self.templates,self.template_button,self.import_button,self.save_button):row.addWidget(w)
        row.addStretch()
        self.send_button=action("用于控制实验",self.send);self.send_button.setProperty("primary",True);row.addWidget(self.send_button)
        layout.addLayout(row)
        self.editor=QWidget();form=QFormLayout(self.editor)
        self.name=QLineEdit();self.numerator=QLineEdit();self.denominator=QLineEdit()
        self.disturbance=QLineEdit();self.initial=QLineEdit()
        self.dist_enabled=QCheckBox("提供对象扰动通道");self.dist_enabled.setChecked(True)
        self.gain=QLineEdit("1");self.time_scale=QLineEdit("1")
        for title,w in (("模型名称",self.name),("控制通道分子 / 降幂系数",self.numerator),("公共分母 / 1～4阶",self.denominator),
                        ("扰动通道",self.dist_enabled),("扰动分子 / 使用相同分母",self.disturbance),
                        ("初始状态 / 可观测标准型",self.initial),("控制增益尺度",self.gain),("时间尺度",self.time_scale)):form.addRow(title,w)
        self.units={}
        for key,name in (("input","控制输入单位"),("output","输出单位"),("disturbance","扰动输入单位")):
            self.units[key]=QLineEdit("unit");form.addRow(name,self.units[key])
        self.drawer=Foldout("模型系数、单位与初始状态",self.editor,expanded=True,height=260)
        layout.addWidget(self.drawer)
        tools=QHBoxLayout()
        self.dt=QLineEdit("0.01");self.duration=QLineEdit("12")
        self.dt.setMaximumWidth(100);self.duration.setMaximumWidth(100)
        tools.addWidget(text("预览采样 / s",True));tools.addWidget(self.dt)
        tools.addWidget(text("预览时长 / s",True));tools.addWidget(self.duration);tools.addStretch()
        self.preview_button=action("保存并预览开环阶跃",self.preview);tools.addWidget(self.preview_button);layout.addLayout(tools)
        self.formula=text("");self.formula.setWordWrap(True);layout.addWidget(self.formula)
        self.note=text("输入系数后预览；快照保存实际模型与采样矩阵。当前自定义对象支持PI/PID族。",True);layout.addWidget(self.note)
        self.figure=Figure(facecolor=PLOT,layout="constrained");self.canvas=FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumHeight(240);layout.addWidget(self.canvas,1)
        self.dist_enabled.toggled.connect(self.disturbance.setEnabled)
        for w in (self.name,self.numerator,self.denominator,self.disturbance,self.initial,self.gain,self.time_scale,*self.units.values(),self.dt,self.duration):
            w.textChanged.connect(self.dirty)
        self.dist_enabled.toggled.connect(self.dirty)
        self.set_plant(default_plant())

    def set_busy(self,active):
        for w in (self.editor,self.templates,self.template_button,self.import_button,self.save_button,
                  self.preview_button,self.send_button,self.dt,self.duration):w.setEnabled(not active)

    def set_plant(self,p):
        p=validate_plant(p)
        for widget,value in ((self.name,p["name"]),(self.numerator,p["numerator"]),(self.denominator,p["denominator"]),
                (self.disturbance,p["disturbance_numerator"] or [0]),(self.initial,p["initial_state"])):
            widget.setText(value if isinstance(value,str) else ", ".join(map(str,value)))
        self.gain.setText(str(p["gain_scale"]));self.time_scale.setText(str(p["time_scale"]))
        self.dist_enabled.setChecked(p["disturbance_numerator"] is not None)
        self.disturbance.setEnabled(self.dist_enabled.isChecked())
        for k,w in self.units.items():w.setText(p["units"][k])
        self.update_formula()

    def plant(self):
        return validate_plant(dict(name=self.name.text(),numerator=array(self.numerator),denominator=array(self.denominator),
            disturbance_numerator=array(self.disturbance) if self.dist_enabled.isChecked() else None,
            initial_state=array(self.initial),gain_scale=float(self.gain.text()),time_scale=float(self.time_scale.text()),
            units={k:w.text() for k,w in self.units.items()}))

    def update_formula(self):
        try:
            p=self.plant()
            def polynomial(values):
                terms=[];degree=len(values)-1
                for i,v in enumerate(values):
                    if v:
                        power=degree-i
                        terms.append(format(v,"g")+("s^"+str(power) if power>1 else "s" if power else ""))
                return " + ".join(terms).replace("+ -","− ") or "0"
            control="Gu(s) = ("+polynomial(p["numerator"])+") / ("+polynomial(p["denominator"])+")"
            disturbance="Gd(s) = ("+polynomial(p["disturbance_numerator"])+") / 同分母" if p["disturbance_numerator"] is not None else "未定义扰动通道"
            self.formula.setText(str(len(p["denominator"])-1)+"阶 / "+control+"  ·  "+disturbance+
                "  ·  实际 Gu = 增益尺度 × Gu(时间尺度 × s)，Gd 同步缩放时间")
        except (ValueError,TypeError,json.JSONDecodeError):
            self.formula.setText("模型系数草稿待完善；不会修改已保存的预览。")

    def dirty(self,*args):
        self.update_formula()
        if self.loaded:self.note.setText("草稿已修改；图中仍为已保存模型的开环预览。再次预览才更新。")

    def use_template(self):
        try:self.set_plant(template(self.templates.currentData()))
        except Exception as exc:self.window.error(exc)

    def preview(self):
        if self.window.running:return
        try:
            from .model_analysis import validate_config as check
            c=check(dict(plant=self.plant(),dt_s=float(self.dt.text()),duration_s=float(self.duration.text())))
            self.window.start_job("model_preview",c)
        except Exception as exc:self.window.error(exc)

    def send(self):
        try:
            c=default_config("transfer_function");c["plant"]=self.plant();c["name"]=c["plant"]["name"]
            if c["plant"]["disturbance_numerator"] is None:c["disturbance"].update(kind="constant",offset=0.,amplitude=0.)
            self.window.apply_config(validate_config(c));self.window.switch_page(0)
            self.window.parameter_drawer.set_expanded(True)
            self.window.status_label.setText("已载入模型；闭环条件采用实验页默认值，预览时长仅用于开环预览")
        except Exception as exc:self.window.error(exc)

    def import_model(self):
        name,_=QFileDialog.getOpenFileName(self,"导入模型",str(self.window.workspace),"JSON (*.json)")
        if name:
            try:
                document=json.loads(Path(name).read_text(encoding="utf-8-sig"))
                if document.get("schema") != "model-definition-1.0" or set(document) != {"schema","plant"}:raise ValueError("未知模型文件版本")
                self.set_plant(document["plant"])
            except Exception as exc:self.window.error(exc)

    def save_model(self):
        try:p=self.plant()
        except Exception as exc:self.window.error(exc);return
        name,_=QFileDialog.getSaveFileName(self,"保存模型",str(self.window.workspace/"model.json"),"JSON (*.json)")
        if name:
            try:atomic_json(Path(name),dict(schema="model-definition-1.0",plant=p))
            except Exception as exc:self.window.error(exc)

    def load_saved(self,loaded):
        self.loaded=loaded;c=loaded["manifest"]["config"];self.set_plant(c["plant"])
        self.dt.setText(str(c["dt_s"]));self.duration.setText(str(c["duration_s"]))
        self.figure.clear();ax=self.figure.add_subplot()
        path=loaded["folder"]/"preview.csv"
        if path.is_file():
            with path.open(encoding="utf-8") as f:rows=list(csv.DictReader(f))
            ax.plot([float(r["time_s"]) for r in rows],[float(r["output"]) for r in rows],color=COLORS[0],lw=2)
            ax.set_xlabel("时间 / s");ax.set_ylabel("输出 / "+c["plant"]["units"]["output"]);ax.grid(alpha=.2)
        state={"completed":"已完成","interrupted":"已中断","export_failure":"未完成"}.get(loaded["status"]["state"],"未完成")
        self.note.setText("开环预览 · "+state+" · "+loaded["verification"]+" · "+loaded["folder"].name)
        style_plot(self.figure);self.canvas.draw_idle()

