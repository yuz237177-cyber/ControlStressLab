"""Portable project indexes around immutable result directories."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,os
from pathlib import Path,PurePosixPath
import shutil,tempfile,uuid,zipfile
from .experiment import atomic_json,load_result,sha,validate_config
SCHEMA="project-1.0"
def now():return datetime.now(timezone.utc).isoformat()
def contained(root,relative):
    if not isinstance(relative,str) or "\\" in relative or ":" in relative or PurePosixPath(relative).is_absolute() or ".." in PurePosixPath(relative).parts:raise ValueError("项目引用必须是安全的相对路径")
    path=(root/relative).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError("项目引用越界")
    return path

def create(folder,title,base,question=""):
    from .tuning_protocol import default_config
    from .linear_models import snapshot,template
    folder=Path(folder).resolve();base=validate_config(base)
    if not isinstance(title,str) or not title.strip() or len(title)>120:raise ValueError("项目名称需要1～120字符")
    plan=default_config(base)
    model=base["plant"] if base["model"]=="transfer_function" else template(base["model"],base["plant"])
    frozen=snapshot(model,base["conditions"]["dt_s"])
    folder.mkdir(parents=True,exist_ok=False)
    try:
        (folder/"results").mkdir();(folder/"models").mkdir()
        atomic_json(folder/"models/initial.json",dict(base=base,model=frozen))
        project=dict(schema=SCHEMA,id=uuid.uuid4().hex,title=title,question=question,created_utc=now(),updated_utc=now(),
            draft=plan,model_snapshot="models/initial.json",model_snapshot_sha256=sha(folder/"models/initial.json"),entries=[],branches=[])
        atomic_json(folder/"project.json",project)
    except BaseException:raise
    return folder

def read(folder,verify=True):
    folder=Path(folder).resolve();p=json.loads((folder/"project.json").read_text(encoding="utf-8-sig"))
    if p.get("schema")!=SCHEMA or not isinstance(p.get("entries"),list):raise ValueError("未知项目格式")
    model=contained(folder,p["model_snapshot"])
    if not model.is_file() or sha(model)!=p["model_snapshot_sha256"]:raise ValueError("项目模型快照不一致")
    ids=set()
    for entry in p["entries"]:
        if entry["id"] in ids:raise ValueError("项目结果ID重复")
        ids.add(entry["id"]);target=contained(folder,entry["folder"])
        if verify:
            if sha(target/"manifest.json")!=entry["manifest_sha256"]:raise ValueError("项目结果来源指纹不一致："+entry["id"])
            if entry["complete"]:
                loaded=load_result(target)
                if loaded["verification"]!="校验通过" or sha(target/"checksums.json")!=entry["checksums_sha256"]:raise ValueError("项目结果完整性校验失败："+entry["id"])
    return p

def update_draft(folder,plan,title=None,question=None):
    from .tuning_protocol import prepare
    folder=Path(folder).resolve();p=read(folder);plan=prepare(plan)["config"]
    from .linear_models import snapshot,template
    base=plan["base"];model=base["plant"] if base["model"]=="transfer_function" else template(base["model"],base["plant"])
    name="models/"+uuid.uuid4().hex+".json"
    atomic_json(folder/name,dict(base=base,model=snapshot(model,base["conditions"]["dt_s"])))
    p.update(draft=deepcopy(plan),model_snapshot=name,model_snapshot_sha256=sha(folder/name),updated_utc=now())
    if title is not None:
        if not isinstance(title,str) or not title.strip() or len(title)>120:raise ValueError("项目名称需要1～120字符")
        p["title"]=title
    if question is not None:p["question"]=question
    atomic_json(folder/"project.json",p)

def register(folder,result):
    folder=Path(folder).resolve();result=Path(result).resolve()
    if result.parent!=folder/"results":raise ValueError("新结果必须位于当前项目results目录")
    p=read(folder);loaded=load_result(result)
    if any(e["id"]==result.name for e in p["entries"]):return
    complete=bool(loaded["status"].get("artifacts_complete")) and loaded["verification"]=="校验通过"
    p["entries"].append(dict(id=result.name,folder="results/"+result.name,schema=loaded["manifest"]["schema_version"],
        manifest_sha256=sha(result/"manifest.json"),checksums_sha256=sha(result/"checksums.json") if complete else None,
        complete=complete,status=loaded["status"]["state"],recorded_utc=now()))
    p["updated_utc"]=now();atomic_json(folder/"project.json",p)

def rebase_frequency(context,config):
    """Return a draft with current local paths; never mutate saved provenance."""
    config=deepcopy(config);source=config.get("source")
    if source is None:return config
    context=Path(context).resolve();root=context.parent.parent
    if context.parent.name=="results" and (root/"project.json").is_file():
        for entry in read(root)["entries"]:
            if entry["manifest_sha256"]==source["manifest_sha256"]:
                source["folder"]=str(contained(root,entry["folder"]));return config
    frozen=context/"evidence/source"
    if (frozen/"manifest.json").is_file() and sha(frozen/"manifest.json")==source["manifest_sha256"]:
        source["folder"]=str(frozen);return config
    return config


def frozen_source(selection_folder,receipt):
    """Resolve by frozen content inside a migrated project; never rewrite receipts."""
    selection_folder=Path(selection_folder).resolve();root=selection_folder.parent.parent
    if selection_folder.parent.name=="results" and (root/"project.json").is_file():
        project=read(root)
        for entry in project["entries"]:
            if entry["schema"]=="tuning-search-1.0" and entry["manifest_sha256"]==receipt["search_manifest_sha256"] and entry["checksums_sha256"]==receipt["search_checksums_sha256"]:
                return contained(root,entry["folder"])
        raise ValueError("项目内找不到冻结选择对应的原搜索记录")
    return Path(receipt["search_folder"])

def clone(folder,source,title):
    source=Path(source).resolve();old=read(source)
    target=create(folder,title,old["draft"]["base"],old["question"]);p=read(target)
    observed=set(old["draft"]["observed_inputs"])
    registry=source/"results/tuning-observations.json"
    if registry.is_file():observed.update(json.loads(registry.read_text(encoding="utf-8")).get("inputs",{}))
    for entry in old["entries"]:
        if entry["schema"] in ("tuning-search-1.0","tuning-validation-1.0"):
            observed.update(r["stimulus_sha256"] for r in load_result(contained(source,entry["folder"]))["records"])
    p["draft"]=deepcopy(old["draft"]);p["draft"]["observed_inputs"]=sorted(observed)
    p["branches"]=[dict(parent_id=old["id"],parent_project_sha256=sha(source/"project.json"),created_utc=now(),observed_inputs=len(observed))]
    atomic_json(target/"project.json",p);return target

def _safe_name(name):
    if not isinstance(name,str) or not name or "\\" in name:raise ValueError("项目包路径无效")
    parts=PurePosixPath(name).parts
    if PurePosixPath(name).is_absolute() or any(v in ("..",".") or v.endswith((" ",".")) or any(ch in v for ch in '<>:"|?*') or v.split(".")[0].upper() in {"CON","PRN","AUX","NUL",*(f"COM{i}" for i in range(1,10)),*(f"LPT{i}" for i in range(1,10))} for v in parts):raise ValueError("项目包含不安全的路径")
    return name

def export_bundle(folder,destination,should_cancel=None):
    from .experiment import Cancelled
    folder=Path(folder).resolve();read(folder);destination=Path(destination).resolve()
    if destination.exists() or destination.is_relative_to(folder):raise ValueError("项目包目标已存在或位于项目内部")
    destination.parent.mkdir(parents=True,exist_ok=True)
    temp=destination.with_name(destination.name+".partial-"+uuid.uuid4().hex)
    try:
        hashes={}
        with zipfile.ZipFile(temp,"x",zipfile.ZIP_DEFLATED) as z:
            for path in sorted(folder.rglob("*")):
                if not path.is_file():continue
                if path.is_symlink() or not path.resolve().is_relative_to(folder):raise ValueError("项目中不支持外部链接")
                if should_cancel and should_cancel():raise Cancelled("项目打包已取消")
                name=_safe_name(path.relative_to(folder).as_posix())
                if name=="bundle-checksums.json":raise ValueError("项目根目录包含保留的归档清单文件")
                data=path.read_bytes()
                hashes[name]=hashlib.sha256(data).hexdigest();z.writestr(name,data)
            z.writestr("bundle-checksums.json",json.dumps(hashes,indent=2))
        with zipfile.ZipFile(temp) as z:
            if z.testzip():raise ValueError("项目包压缩结构校验失败")
            for name,h in hashes.items():
                if hashlib.sha256(z.read(name)).hexdigest()!=h or sha(folder/name)!=h:raise ValueError("项目在导出期间发生变化")
        if should_cancel and should_cancel():raise Cancelled("项目打包已取消")
        with destination.open("xb") as out,temp.open("rb") as stream:shutil.copyfileobj(stream,out)
        return destination
    finally:
        if temp.exists():temp.unlink()

def import_bundle(archive,destination,should_cancel=None):
    from .experiment import Cancelled
    archive=Path(archive).resolve();destination=Path(destination).resolve()
    if destination.exists():raise FileExistsError("项目导入目录已存在，未覆盖")
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist()
        if len(infos)>30000 or sum(i.file_size for i in infos)>1024**3:raise ValueError("项目包超过资源预算")
        names=[_safe_name(i.filename) for i in infos]
        if len({n.casefold() for n in names})!=len(names):raise ValueError("项目包有重复或大小写冲突路径")
        if any(i.is_dir() or ((i.external_attr>>16)&0o170000)==0o120000 for i in infos):raise ValueError("项目包只接受普通文件")
        checks=json.loads(z.read("bundle-checksums.json"))
        if set(checks)!=(set(names)-{"bundle-checksums.json"}) or "project.json" not in checks:raise ValueError("项目包完整性清单缺失")
        for name,wanted in checks.items():
            if should_cancel and should_cancel():raise Cancelled("项目导入已取消")
            if hashlib.sha256(z.read(name)).hexdigest()!=wanted:raise ValueError("项目包内容校验失败："+name)
        destination.parent.mkdir(parents=True,exist_ok=True)
        stage=Path(tempfile.mkdtemp(prefix=".import-",dir=destination.parent)).resolve()
        try:
            for name in checks:
                path=contained(stage,name);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(name))
            read(stage)
            if should_cancel and should_cancel():raise Cancelled("项目导入已取消")
            # This index is mutable; immutable result files and receipts are unchanged.
            atomic_json(stage/"import-receipt.json",dict(archive_sha256=sha(archive),imported_utc=now()))
            os.rename(stage,destination)
        except BaseException:
            if stage.exists():
                assert stage.parent==destination.parent and stage.name.startswith(".import-")
                shutil.rmtree(stage)
            raise
    return destination
