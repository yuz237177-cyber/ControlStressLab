"""Constraint tuning: requirements, finite tradeoffs, receipts and validation."""
from copy import deepcopy
import json
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QScrollArea, QSpinBox,
    QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from .gui_components import StageHeader, Foldout
from .gui_theme import ACCENT, COLORS, PLOT, style_plot
from .experiment import atomic_json, contained, read_trace
from .gui_analysis import action, choices, numbers, text
from .robustness import allowed_axes
from .tuning_protocol import STRUCTURES, default_config, prepare

STATES={"met":"满足要求","not_met":"指标越限","run_failed":"运行失败","metric_invalid":"指标无效","incomplete":"未完成"}


class TuningPage(QWidget):
    def __init__(self,window):
        super().__init__()
        self.window = window; self.loaded = None
        self.search_folder = self.selection_folder = None
        self.frozen_main_id = None; self._setting = False
        self.setObjectName("workspace")
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(8)
        layout.addWidget(StageHeader("02", "约束多目标整定", "TUNING / 从要求到独立验证"))
        stages = QHBoxLayout(); stages.setSpacing(14); self.stage_labels = []
        for title in ("01  声明要求", "02  搜索与选择", "03  冻结参数", "04  新工况验证"):
            item = text(title); self.stage_labels.append(item); stages.addWidget(item, 1)
        layout.addLayout(stages)
        self.note = text("先声明工况与要求；验证结果不参与参数选择。", True)
        layout.addWidget(self.note)
        tools = QHBoxLayout(); tools.setSpacing(7)
        self.candidate = QComboBox(); self.candidate.setFixedWidth(118)
        self.case = QComboBox(); self.case.setMinimumWidth(80)
        self.case.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.case.setMinimumContentsLength(9)
        self.channel = choices(dict(front="候选取舍", output="输出与参考", error="跟踪误差", applied_input="实际输入", requirements="要求概览"))
        self.channel.setFixedWidth(148)
        tools.addWidget(self.candidate); tools.addWidget(self.channel); tools.addWidget(self.case, 1)
        tools.addStretch(1)
        tools.addWidget(action("较低误差", lambda:self.locate("low_error_id")))
        tools.addWidget(action("较平稳动作", lambda:self.locate("smooth_action_id")))
        self.inspector_button = action("候选详情", self.toggle_inspector)
        self.inspector_button.setCheckable(True); self.inspector_button.setChecked(True)
        tools.addWidget(self.inspector_button); layout.addLayout(tools)
        center = QHBoxLayout(); center.setSpacing(16)
        self.figure = Figure(facecolor=PLOT, layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure); self.canvas.setMinimumHeight(270)
        self.canvas.mpl_connect("button_press_event", self.click_front)
        center.addWidget(self.canvas, 1)
        self.inspector = QFrame(); self.inspector.setObjectName("inspector")
        self.inspector.setFixedWidth(278)
        inspector_outer = QVBoxLayout(self.inspector); inspector_outer.setContentsMargins(0, 0, 0, 0)
        inspector_content = QWidget()
        inspector_scroll = QScrollArea(); inspector_scroll.setWidgetResizable(True)
        inspector_scroll.setWidget(inspector_content); inspector_outer.addWidget(inspector_scroll)
        info = QVBoxLayout(inspector_content); info.setContentsMargins(18, 15, 18, 15); info.setSpacing(9)
        heading = text("CANDIDATE / 当前查看"); heading.setObjectName("eyebrow"); info.addWidget(heading)
        self.candidate_id = text("—"); self.candidate_id.setObjectName("candidateId"); info.addWidget(self.candidate_id)
        self.candidate_state = text("尚未搜索"); self.candidate_state.setObjectName("candidateState")
        info.addWidget(self.candidate_state)
        metrics = QHBoxLayout()
        self.j1_value = self.metric_block(metrics, "J1 / 归一化误差")
        self.j2_value = self.metric_block(metrics, "J2 / 动作变化率 · /s")
        info.addLayout(metrics)
        self.detail = text("运行搜索后查看参数与约束。", True)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail_scroll = QScrollArea(); detail_scroll.setWidgetResizable(True)
        detail_scroll.setWidget(self.detail); info.addWidget(detail_scroll, 1)
        info.addWidget(text("主选 / 冻结前确认", True))
        self.main_choice = QComboBox(); info.addWidget(self.main_choice)
        info.addWidget(text("比较 / 可选", True))
        self.compare_choice = QComboBox(); info.addWidget(self.compare_choice)
        self.rationale=QLineEdit();self.rationale.setPlaceholderText("选择依据（随主选冻结）");info.addWidget(self.rationale)
        self.use_candidate_button = action("将当前候选设为主选", self.use_candidate_as_main)
        info.addWidget(self.use_candidate_button)
        center.addWidget(self.inspector); layout.addLayout(center, 1)
        self.tabs = QTabWidget()
        self.editor=QWidget(); fields=QGridLayout(self.editor)
        self.structure=choices({s:s for s in STRUCTURES})
        self.budget=QSpinBox();self.budget.setRange(2,128)
        self.search_seed=QLineEdit()
        fields.addWidget(action("从实验页建立协议",self.use_current),0,0)
        fields.addWidget(self.structure,0,1)
        fields.addWidget(text("候选预算 / 搜索种子",True),0,2)
        fields.addWidget(self.budget,0,3);fields.addWidget(self.search_seed,0,4)
        self.axis_keys=[QComboBox(),QComboBox()];self.axis_values=[QLineEdit(),QLineEdit()]
        self.second=QCheckBox("第二轴");self.second.setChecked(True)
        for row in range(2):
            fields.addWidget(text("工况轴" if row==0 else "第二轴",True),row+1,0)
            fields.addWidget(self.axis_keys[row],row+1,1);fields.addWidget(self.axis_values[row],row+1,2)
        fields.addWidget(self.second,2,3)
        self.seeds=QLineEdit();fields.addWidget(text("搜索噪声种子",True),1,3);fields.addWidget(self.seeds,1,4)
        self.thresholds={}
        for i,(key,label) in enumerate((("error_max","归一化RMSE上限"),("saturation_max","饱和比例上限"),("variation_max","动作变化率上限 /s"))):
            edit=QLineEdit();edit.setPlaceholderText("留空关闭")
            fields.addWidget(text(label,True),3,i);fields.addWidget(edit,4,i);self.thresholds[key]=edit
        fields.addWidget(action("参数范围与信号/验证条件",self.edit_protocol),3,3,1,2)
        fields.addWidget(action("导入协议",self.import_config),4,3)
        fields.addWidget(action("保存协议",self.save_config),4,4)
        self.plan_note=text("",True);fields.addWidget(self.plan_note,5,0,1,4)
        fields.addWidget(action("检查计划与预算",self.validate_plan),5,4)
        self.tabs.addTab(self.editor,"要求与计划")
        self.table=QTableWidget();self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["候选ID","可行","J1 误差","J2 动作 /s","非支配","不满足记录数","参数"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tabs.addTab(self.table,"候选明细")
        case_panel=QWidget();case_layout=QVBoxLayout(case_panel)
        self.issues=QTableWidget();self.issues.setColumnCount(7)
        self.issues.setHorizontalHeaderLabels(["工况/种子","实际条件","要求状态","归一化RMSE","饱和比例","动作变化率 /s","不满足原因"])
        self.issues.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.issues.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.issues.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        case_layout.addWidget(self.issues)
        case_layout.addWidget(action("打开当前工况原始CSV",self.open_trace))
        self.tabs.addTab(case_panel,"逐工况要求 / 原始数据")
        self.data_drawer = Foldout("要求与计划 / 候选明细 / 逐工况要求", self.tabs, height=295)
        layout.addWidget(self.data_drawer)
        footer = QHBoxLayout()
        self.start_button = action("检查预算并搜索", self.start)
        self.freeze_button = action("冻结主选", self.freeze)
        self.validate_button = action("运行新工况验证", self.validate)
        self.send_button = action("候选送到实验页", self.send_to_experiment)
        footer.addWidget(self.start_button); footer.addWidget(self.freeze_button)
        footer.addWidget(self.validate_button); footer.addStretch(); footer.addWidget(self.send_button)
        layout.addLayout(footer)
        layout.addWidget(text("合成模型 / 搜索达标与新工况验证分别记录。", True))
        self.candidate.currentIndexChanged.connect(self.select_candidate)
        self.channel.currentIndexChanged.connect(self.draw); self.case.currentIndexChanged.connect(self.draw)
        self.table.cellClicked.connect(self.choose_table); self.issues.cellClicked.connect(self.choose_case)
        self.main_choice.currentIndexChanged.connect(self.update_freeze_label)
        self.structure.currentIndexChanged.connect(self.structure_changed)
        self.set_config(default_config(window.config)); self.draw(); self.set_busy(False)

    def metric_block(self, row, title):
        stack = QVBoxLayout(); stack.addWidget(text(title, True))
        value = text("—"); value.setObjectName("metricValue"); stack.addWidget(value)
        row.addLayout(stack, 1); return value

    def toggle_inspector(self):
        self.inspector.setVisible(self.inspector_button.isChecked())

    def use_candidate_as_main(self):
        index = self.main_choice.findData(self.candidate.currentData())
        if index >= 0: self.main_choice.setCurrentIndex(index)

    def update_freeze_label(self):
        cid = self.main_choice.currentData()
        self.freeze_button.setText("冻结主选" if cid is None else f"冻结主选 {cid:03}")

    def update_stage(self):
        schema = self.loaded["manifest"]["schema_version"] if self.loaded else ""
        current = {"tuning-search-1.0":1, "tuning-selection-1.0":2, "tuning-validation-1.0":3}.get(schema, 0)
        for index, item in enumerate(self.stage_labels):
            item.setProperty("step", "done" if index < current else "active" if index == current else "pending")
            item.style().unpolish(item); item.style().polish(item)

    def set_config(self,c):
        self._setting=True;self.draft=deepcopy(c)
        self.structure.setCurrentIndex(self.structure.findData(c["controller"]))
        self.budget.setValue(c["candidate_budget"]);self.search_seed.setText(str(c["search_seed"]))
        options=allowed_axes(c["base"]["model"])
        for i in range(2):
            self.axis_keys[i].clear()
            for k,v in options.items():self.axis_keys[i].addItem(v,k)
            if i<len(c["search"]["axes"]):
                a=c["search"]["axes"][i];self.axis_keys[i].setCurrentIndex(self.axis_keys[i].findData(a["key"]));self.axis_values[i].setText(", ".join(map(str,a["values"])))
        self.second.setChecked(len(c["search"]["axes"])==2)
        self.seeds.setText(",".join(map(str,c["search"]["seeds"])))
        for k,w in self.thresholds.items():w.setText("" if c["thresholds"][k]is None else str(c["thresholds"][k]))
        self.plan_note.setText("协议草稿："+c["base"]["model"]+"；更改工况轴时须同步编辑验证条件。草稿变化不会修改已保存结果。")
        self._setting=False

    def config(self):
        c=deepcopy(self.draft);c["controller"]=self.structure.currentData();c["base"]["selected_controllers"]=[c["controller"]]
        c["candidate_budget"]=self.budget.value();c["search_seed"]=int(self.search_seed.text())
        c["search"]["axes"]=[dict(key=self.axis_keys[i].currentData(),values=numbers(self.axis_values[i].text())) for i in range(2 if self.second.isChecked() else 1)]
        c["search"]["seeds"]=[int(s.strip()) for s in self.seeds.text().split(",")]
        c["thresholds"]={k:float(w.text()) if w.text().strip() else None for k,w in self.thresholds.items()}
        return c

    def structure_changed(self):
        if self._setting:return
        self.draft["controller"]=self.structure.currentData()
        self.draft["ranges"]=default_config(self.draft["base"],self.structure.currentData())["ranges"]

    def use_current(self):
        try:
            c=default_config(self.window.collect_config(),self.structure.currentData())
            if self.loaded:
                old=json.loads((self.loaded["folder"]/"plan.json").read_text(encoding="utf8"))
                if self.loaded["manifest"]["schema_version"]=="tuning-validation-1.0":
                    c["observed_inputs"]=list(set(self.draft.get("observed_inputs",[]))|{p["input_sha256"] for p in old["validation"]})
            self.set_config(c)
        except Exception as exc:self.window.error(exc)

    def edit_protocol(self):
        try:c=self.config()
        except Exception as exc:self.window.error(exc);return
        dialog=QDialog(self);dialog.setWindowTitle("完整协议：参数范围、信号模板与验证条件");dialog.resize(980,700)
        layout=QVBoxLayout(dialog);edit=QTextEdit();edit.setPlainText(json.dumps(c,ensure_ascii=False,indent=2));layout.addWidget(edit)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);layout.addWidget(buttons)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject)
        if dialog.exec():
            try:self.set_config(prepare(json.loads(edit.toPlainText()))["config"])
            except Exception as exc:self.window.error(exc)

    def import_config(self):
        name,_=QFileDialog.getOpenFileName(self,"导入约束整定协议",str(self.window.workspace),"JSON (*.json)")
        if name:
            try:self.set_config(prepare(json.loads(Path(name).read_text(encoding="utf8")))["config"])
            except Exception as exc:self.window.error(exc)

    def save_config(self):
        try:c=prepare(self.config())["config"]
        except Exception as exc:self.window.error(exc);return
        name,_=QFileDialog.getSaveFileName(self,"保存约束整定协议",str(self.window.workspace/"tuning-config.json"),"JSON (*.json)")
        if name:
            try:atomic_json(Path(name),c)
            except Exception as exc:self.window.error(exc)

    def start(self):
        if self.window.running:return
        try:
            c=self.validate_plan()
            if c is not None:self.window.start_job("tuning_search",c)
        except Exception as exc:self.window.error(exc)

    def validate_plan(self):
        try:
            plan=prepare(self.config());b=plan["budget"]
            self.plan_note.setText(f"{b['unique_candidates']}个唯一候选；搜索{b['search_runs']}次，验证预留{b['validation_reserved']}次，上限{b['total_upper']}次/{b['intervals_upper']}个推进区间。"+"；".join(plan['warnings']))
            return plan["config"]
        except Exception as exc:
            self.plan_note.setText("配置无效："+str(exc));self.window.error(exc)
            return None

    def freeze(self):
        if self.window.running or self.search_folder is None:return
        try:
            main=self.main_choice.currentData();other=self.compare_choice.currentData()
            if main is None:raise ValueError("没有可行候选可冻结")
            ids=list(dict.fromkeys([main]+([] if other is None else [other])))
            self.window.start_job("tuning_freeze",dict(search_folder=str(self.search_folder),candidate_ids=ids,main_candidate_id=main,rationale=self.rationale.text()))
        except Exception as exc:self.window.error(exc)

    def validate(self):
        if not self.window.running and self.selection_folder:
            self.window.start_job("tuning_validation",dict(selection_folder=str(self.selection_folder)))

    def set_busy(self,active):
        self.editor.setEnabled(not active);self.start_button.setEnabled(not active)
        self.update_stage()
        stage=self.loaded["manifest"]["schema_version"] if self.loaded and self.loaded["verification"]=="校验通过" and self.loaded["status"].get("artifacts_complete") else ""
        self.freeze_button.setEnabled(not active and stage=="tuning-search-1.0" and self.main_choice.count()>0)
        self.validate_button.setEnabled(not active and stage=="tuning-selection-1.0")
        self.main_choice.setEnabled(not active and stage=="tuning-search-1.0")
        self.compare_choice.setEnabled(not active and stage=="tuning-search-1.0")
        self.send_button.setEnabled(not active and self.candidate.currentData() is not None and stage in ("tuning-search-1.0","tuning-validation-1.0"))
        self.use_candidate_button.setEnabled(not active and stage == "tuning-search-1.0" and self.main_choice.findData(self.candidate.currentData()) >= 0)
        primary = self.validate_button if stage == "tuning-selection-1.0" else self.freeze_button if self.freeze_button.isEnabled() else self.start_button
        for b in (self.start_button, self.freeze_button, self.validate_button):
            b.setProperty("primary", b is primary); b.style().unpolish(b); b.style().polish(b)

    def load_saved(self,loaded):
        self.loaded=loaded;folder=loaded["folder"];schema=loaded["manifest"]["schema_version"]
        self.frozen_main_id = None
        self.set_config(loaded["manifest"]["config"])
        self.main_choice.clear();self.compare_choice.clear();self.compare_choice.addItem("不添加",None)
        if schema=="tuning-selection-1.0":
            selection=json.loads((folder/"selection.json").read_text(encoding="utf8"))
            from .projects import frozen_source
            self.selection_folder=folder;self.search_folder=frozen_source(folder,selection)
            self.frozen_main_id = selection["main_candidate_id"]
            self.summary=json.loads((folder/"search-summary.json").read_text(encoding="utf8"))
            self.note.setText(f"主选候选{selection['main_candidate_id']}已冻结；尚未验证。参数和验证计划不可原地修改。")
        else:
            self.summary=json.loads((folder/"summary.json").read_text(encoding="utf8")) if (folder/"summary.json").exists() else {}
            self.search_folder=folder if schema=="tuning-search-1.0" else None
            self.selection_folder=None
            if schema=="tuning-search-1.0":
                for c in self.summary.get("candidates",[]):
                    if c["feasible"]:
                        self.main_choice.addItem(str(c["candidate_id"]),c["candidate_id"]);self.compare_choice.addItem(str(c["candidate_id"]),c["candidate_id"])
                self.note.setText(f"搜索结果：{self.summary.get('feasible_count',0)}个可行候选。选择基于已保存结果；草稿变化须重新搜索。"+loaded["verification"])
            else:self.note.setText(f"主选候选{self.summary.get('main_candidate_id')}验证：{STATES.get(self.summary.get('main_outcome'),'未完成')}。验证不重新选参；输入历史状态保存在报告。"+loaded["verification"])
        if schema == "tuning-selection-1.0":
            self.main_choice.addItem(str(self.frozen_main_id), self.frozen_main_id)
            for value in selection["candidate_ids"]:
                if value != self.frozen_main_id:
                    self.compare_choice.addItem(str(value), value)
                    self.compare_choice.setCurrentIndex(self.compare_choice.count()-1)
        self.candidate.blockSignals(True);self.candidate.clear()
        for c in self.summary.get("candidates",[]):self.candidate.addItem("候选 "+str(c["candidate_id"]),c["candidate_id"])
        self.candidate.blockSignals(False)
        candidates=self.summary.get("candidates",[]);self.table.setRowCount(len(candidates))
        for row,c in enumerate(candidates):
            values=[c["candidate_id"],c.get("feasible",c.get("outcome")),c.get("J1"),c.get("J2"),c["candidate_id"] in self.summary.get("frontier_ids",[]),len(c.get("issues",[])),json.dumps(c.get("parameters",{}),ensure_ascii=False)]
            for col,value in enumerate(values):
                item=QTableWidgetItem("—" if value is None else str(value));item.setData(Qt.ItemDataRole.UserRole,c["candidate_id"]);self.table.setItem(row,col,item)
        if "frontier_ids" not in self.summary:self.channel.setCurrentIndex(self.channel.findData("requirements"))
        else:self.channel.setCurrentIndex(self.channel.findData("front"))
        if loaded["verification"]!="校验通过" or not loaded["status"].get("artifacts_complete"):
            self.note.setText("结果未完整或校验不通过；仅供查看，禁止冻结和验证。")
        preferred = self.frozen_main_id if self.frozen_main_id is not None else self.summary.get("main_candidate_id", self.summary.get("low_error_id"))
        if preferred is not None: self.candidate.setCurrentIndex(self.candidate.findData(preferred))
        self.select_candidate();self.set_busy(False)
        if loaded["verification"]!="校验通过" or not loaded["status"].get("artifacts_complete"):
            self.freeze_button.setEnabled(False);self.validate_button.setEnabled(False)

    def select_candidate(self,*args):
        self.case.blockSignals(True);self.case.clear()
        cid=self.candidate.currentData()
        records=[r for r in self.loaded["records"] if r["candidate_id"]==cid] if self.loaded else []
        self.issues.setRowCount(len(records))
        for row,r in enumerate(records):
            self.case.addItem(f"{r['family']} / {r['point']} / seed {r['seed']}",r["case_id"])
            m=r["metrics"];values=[r["case_id"],r["point"],STATES.get(r["requirement"],r["requirement"]),m["normalized_rmse"],m["saturation_fraction"],m["input_variation_rate"],r["issues"]]
            for col,value in enumerate(values):
                item=QTableWidgetItem("—" if value is None else str(value));item.setData(Qt.ItemDataRole.UserRole,r["case_id"]);self.issues.setItem(row,col,item)
        self.case.blockSignals(False)
        c=next((c for c in getattr(self,"summary",{}).get("candidates",[]) if c["candidate_id"]==cid),None)
        if c:
            params=c.get("parameters",{})
            if not params and records:
                params=next(d["parameters"] for d in records[0]["run_config"]["controllers"] if d["name"]==records[0]["controller_name"])
            shown="\n".join(f"{k}: {v:.6g}" if type(v) in (int,float) else f"{k}: {v}" for k,v in params.items())
            self.candidate_id.setText(f"{cid:03}")
            self.j1_value.setText("—" if c.get("J1") is None else f"{c['J1']:.4f}")
            self.j2_value.setText("—" if c.get("J2") is None else f"{c['J2']:.3f}")
            schema = self.loaded["manifest"]["schema_version"]
            state = "normal"
            if self.loaded["verification"] != "校验通过" or not self.loaded["status"].get("artifacts_complete"):
                title = "文件不完整或校验未通过"; state = "invalid"
            elif schema == "tuning-selection-1.0":
                title = "主选已冻结 · 尚未验证" if cid == self.frozen_main_id else "搜索记录 · 非冻结主选"
            elif "feasible" in c:
                title = "搜索要求满足 · 尚未验证" if c["feasible"] else "搜索要求未满足"
                if not c["feasible"]: state = "issue"
            else:
                title = "验证：" + STATES.get(c.get("outcome"), "未完成")
                if c.get("outcome") != "met": state = "issue"
            self.candidate_state.setText(title); self.candidate_state.setProperty("state", state)
            self.candidate_state.style().unpolish(self.candidate_state); self.candidate_state.style().polish(self.candidate_state)
            self.detail.setText("参数快照\n" + shown + f"\n\n不满足记录：{len(c.get('issues', []))}\n逐工况要求可展开查看。")
        else:
            self.candidate_id.setText("—"); self.j1_value.setText("—"); self.j2_value.setText("—")
            self.candidate_state.setText("尚无候选数据"); self.detail.setText("声明要求后运行搜索。")
        if hasattr(self, "use_candidate_button"):
            self.use_candidate_button.setEnabled(not self.window.running and self.loaded is not None
                and self.loaded["verification"] == "校验通过" and self.loaded["status"].get("artifacts_complete", False)
                and self.loaded["manifest"]["schema_version"] == "tuning-search-1.0"
                and self.main_choice.findData(cid) >= 0)
        self.draw()

    def choose_table(self,row,column):
        item=self.table.item(row,0)
        if item:self.candidate.setCurrentIndex(self.candidate.findData(item.data(Qt.ItemDataRole.UserRole)))

    def choose_case(self,row,column):
        item=self.issues.item(row,0)
        if item:self.case.setCurrentIndex(self.case.findData(item.data(Qt.ItemDataRole.UserRole)));self.channel.setCurrentIndex(self.channel.findData("output"))

    def locate(self,key):
        cid=getattr(self,"summary",{}).get(key)
        if cid is not None:self.candidate.setCurrentIndex(self.candidate.findData(cid))

    def click_front(self,event):
        if self.channel.currentData()!="front" or event.inaxes is None or event.xdata is None:return
        candidates=[c for c in getattr(self,"summary",{}).get("candidates",[]) if c.get("feasible")]
        if not candidates:return
        # Use screen distance so axes with different units cannot bias selection.
        nearest=min(candidates,key=lambda c:sum((a-b)**2 for a,b in zip(event.inaxes.transData.transform((c["J1"],c["J2"])),(event.x,event.y))))
        self.candidate.setCurrentIndex(self.candidate.findData(nearest["candidate_id"]))

    def draw(self,*args):
        self.figure.clear()
        records=self.loaded["records"] if self.loaded else []
        channel=self.channel.currentData()
        if channel=="front" and "frontier_ids" in getattr(self,"summary",{}):
            from .tuning_plots import draw_front
            ax = draw_front(self.figure,self.summary,dark=True)
            feasible = [c for c in self.summary["candidates"] if c["feasible"]]
            for artist, candidate in zip(ax.collections, feasible):
                artist.set_facecolor(COLORS[0] if candidate["candidate_id"] in self.summary["frontier_ids"] else "#7e939c")
            for annotation, candidate in zip(ax.texts, feasible):
                annotation.set_visible(candidate["candidate_id"] in self.summary["frontier_ids"] or candidate["candidate_id"] in (0, self.candidate.currentData()))
            if not feasible:
                ax.texts[0].set_text("当前声明要求下，没有可行候选")
            current = next((c for c in feasible if c["candidate_id"] == self.candidate.currentData()), None)
            if current:
                ax.scatter(current["J1"], current["J2"], s=310, facecolors="none", edgecolors=ACCENT, linewidths=2.2, zorder=8)
            ax.set_title("")
            ax.set_xlabel("J1 · 归一化误差（族均衡 / 最差种子）")
            ax.set_ylabel("J2 · 最差控制动作变化率 / s⁻¹")
            ax.set_title("星标：有限候选中的非支配项    圆环：当前查看", fontsize=11, loc="left", pad=17)
        elif channel=="requirements" and records:
            from .tuning_plots import draw_requirements
            draw_requirements(self.figure,records,dark=True)
        elif channel in ("output","error","applied_input") and records:
            record=next((r for r in records if r["case_id"]==self.case.currentData()),None)
            if record:
                from .tuning_plots import comparison_views
                from .comparison_plots import draw
                draw(self.figure,comparison_views(self.loaded["folder"],records,record),channel,dark=True)
        if not self.figure.axes:
            ax=self.figure.add_subplot();ax.set_axis_off();ax.set_facecolor(PLOT)
            ax.text(.5,.5,"声明要求并运行搜索后，在这里比较候选；冻结后才能验证",ha="center",transform=ax.transAxes,color="#b3bac7")
        style_plot(self.figure)
        self.case.setVisible(channel in ("output", "error", "applied_input"))
        self.canvas.draw_idle()

    def open_trace(self):
        if not self.loaded:return
        record=next((r for r in self.loaded["records"] if r["case_id"]==self.case.currentData()),None)
        if record:QDesktopServices.openUrl(QUrl.fromLocalFile(str(contained(self.loaded["folder"],record["trace_file"]))))

    def send_to_experiment(self):
        if not self.loaded:return
        record=next((r for r in self.loaded["records"] if r["case_id"]==self.case.currentData()),None)
        if record:
            try:self.window.apply_config(record["run_config"]);self.window.switch_page(0)
            except Exception as exc:self.window.error(exc)
