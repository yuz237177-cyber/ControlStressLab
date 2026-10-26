"""Project home page; immutable runs remain separate from mutable drafts."""
from pathlib import Path
import json,sys,uuid
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QPlainTextEdit,QComboBox,QTableWidget,QTableWidgetItem,QFileDialog
from .gui_components import StageHeader,Foldout
from .gui_analysis import action,text
from . import projects

class ProjectPage(QWidget):
    def __init__(self,window):
        super().__init__();self.window=window;self.folder=None;self.setObjectName("workspace")
        layout=QVBoxLayout(self);layout.addWidget(StageHeader("08","研究项目","PROJECT / 模型 · 要求 · 搜索 · 冻结 · 验证"))
        self.editor=QWidget();top=QVBoxLayout(self.editor);row=QHBoxLayout()
        for label,func in (("新建项目",self.create),("打开项目",self.open),("导入项目包",self.import_bundle),("导出完整项目包",self.export),("克隆新分支",self.clone),("独立实验",self.leave)):
            row.addWidget(action(label,func))
        top.addLayout(row)
        self.title=QLineEdit("控制方案研究");self.question=QPlainTextEdit();self.question.setPlaceholderText("研究问题、对象假设及方案取舍");self.question.setMaximumHeight(70)
        top.addWidget(self.title);top.addWidget(self.question)
        row=QHBoxLayout();row.addWidget(action("保存当前整定协议到项目",self.save));row.addWidget(action("载入项目协议",self.use))
        self.examples=QComboBox()
        for key,name in (("first-order","一阶过程"),("second-order","二阶振荡"),("custom","自定义四阶")):self.examples.addItem(name,key)
        row.addWidget(self.examples);row.addWidget(action("打开完整示例",self.example));top.addLayout(row);layout.addWidget(self.editor)
        self.note=text("可独立使用各工作台，也可建立项目统一保存模型、要求与全部阶段结果。",True);self.note.setWordWrap(True);layout.addWidget(self.note)
        self.stages=text("");self.stages.setWordWrap(True);layout.addWidget(self.stages)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(["结果ID","阶段","状态","记录时间"]);self.table.cellDoubleClicked.connect(lambda *_:self.open_selected());layout.addWidget(self.table,1)
        actions=QHBoxLayout();actions.addWidget(action("打开选中结果",self.open_selected));actions.addWidget(action("进入约束整定",lambda:self.window.switch_page(1)))
        actions.addWidget(action("进入模型工作台",lambda:self.window.switch_page(5)));actions.addWidget(action("进入频域分析",lambda:self.window.switch_page(6)));layout.addLayout(actions)
    def root(self):
        folder=self.window.workspace/"projects";folder.mkdir(exist_ok=True);return folder
    def open_folder(self,folder):
        p=projects.read(folder);self.folder=Path(folder).resolve();self.window.active_project=self.folder
        self.title.setText(p["title"]);self.question.setPlainText(p["question"]);self.window.tuning_page.set_config(p["draft"])
        self.window.apply_config(p["draft"]["base"]);self.refresh()
        self.window.switch_page(7);self.window.status_label.setText("当前项目："+p["title"]+"；新运行将保存到此项目")
    def create(self):
        if self.window.running:return
        try:
            folder=self.root()/("project-"+uuid.uuid4().hex[:10])
            projects.create(folder,self.title.text(),self.window.collect_config(),self.question.toPlainText());self.open_folder(folder)
        except Exception as exc:self.window.error(exc)
    def open(self):
        name=QFileDialog.getExistingDirectory(self,"打开项目目录",str(self.root()))
        if name:
            try:self.open_folder(name)
            except Exception as exc:self.window.error(exc)
    def refresh(self):
        if not self.folder:return
        p=projects.read(self.folder);self.note.setText(p["title"]+" · "+str(self.folder)+"；历史结果保持冻结，草稿另存。")
        labels={"experiment-1.0":"控制实验","robustness-1.0":"参数扫描","tuning-search-1.0":"候选搜索","tuning-selection-1.0":"主选冻结","tuning-validation-1.0":"新工况验证","frequency-1.0":"频域分析","model-preview-1.0":"模型预览"}
        self.table.setRowCount(len(p["entries"]))
        for row,e in enumerate(p["entries"]):
            for col,value in enumerate((e["id"],labels.get(e["schema"],e["schema"]),{"completed":"已完成","completed_with_failures":"已完成（含运行失败）","interrupted":"已中断","export_failure":"保存失败"}.get(e["status"],e["status"]),e["recorded_utc"].split(".")[0].replace("T"," ")+" UTC")):self.table.setItem(row,col,QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        schemas={e["schema"] for e in p["entries"] if e["complete"]}
        self.stages.setText("阶段记录（●已保存，是否满足要求请打开结果）：  "+"  →  ".join(("● " if schema in schemas else "○ ")+label for schema,label in (("experiment-1.0","实验"),("tuning-search-1.0","搜索"),("tuning-selection-1.0","冻结"),("tuning-validation-1.0","验证"),("frequency-1.0","频域"))))
    def leave(self):
        if self.window.running:return
        self.window.active_project=None;self.folder=None;self.table.setRowCount(0);self.stages.setText("")
        self.note.setText("已切换独立实验；新运行保存到普通实验历史，原项目保留。")

    def save(self):
        if not self.folder:return
        try:
            projects.update_draft(self.folder,self.window.tuning_page.config(),self.title.text(),self.question.toPlainText());self.refresh()
        except Exception as exc:self.window.error(exc)
    def use(self):
        if not self.folder:return
        try:self.open_folder(self.folder);self.window.switch_page(1)
        except Exception as exc:self.window.error(exc)
    def open_selected(self):
        if not self.folder:return
        try:
            row=self.table.currentRow();p=projects.read(self.folder)
            if row<0:raise ValueError("请先选择一个阶段结果")
            self.window.open_result(projects.contained(self.folder,p["entries"][row]["folder"]))
        except Exception as exc:self.window.error(exc)
    def export(self):
        if not self.folder or self.window.running:return
        name,_=QFileDialog.getSaveFileName(self,"导出完整项目包",str(self.folder.with_suffix(".cslproj")),"项目包 (*.cslproj)")
        if name:self.window.start_job("project_export",dict(folder=str(self.folder),destination=name))
    def import_bundle(self):
        if self.window.running:return
        name,_=QFileDialog.getOpenFileName(self,"导入项目包",str(self.root()),"项目包 (*.cslproj *.zip)")
        if name:self.window.start_job("project_import",dict(archive=name,destination=str(self.root()/("import-"+uuid.uuid4().hex[:10]))))
    def clone(self):
        if not self.folder or self.window.running:return
        try:self.open_folder(projects.clone(self.root()/("branch-"+uuid.uuid4().hex[:10]),self.folder,self.title.text()+" / 新分支"))
        except Exception as exc:self.window.error(exc)
    def example(self):
        if self.window.running:return
        base=Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parents[2]))
        source=base/"examples"/(self.examples.currentData()+".cslproj")
        if not source.is_file():self.window.error("示例包尚未构建，请运行示例构建脚本或使用正式桌面包");return
        self.window.start_job("project_import",dict(archive=str(source),destination=str(self.root()/("example-"+uuid.uuid4().hex[:10]))))
    def set_busy(self,active):self.editor.setEnabled(not active)
