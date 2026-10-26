"""Reproducible Windows portable build, relocation test and integrity-checked ZIP."""
import argparse,hashlib,importlib.metadata,json,os,platform,shutil,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def call(args,env,log,cwd=ROOT):
    import time
    for attempt in range(10):
        try:stream=log.open("ab");break
        except PermissionError:
            if attempt==9:raise
            time.sleep(.15)
    with stream:
        done=subprocess.run(args,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT)
    if done.returncode:raise RuntimeError("构建/检查失败，详情："+str(log))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"dist/v1.0.0")
    parser.add_argument("--work",type=Path,default=ROOT/"outputs/desktop-final-build")
    parser.add_argument("--verify",action="store_true")
    parser.add_argument("--reuse-examples",action="store_true",help="复用同一构建工作目录中已完成的示例")
    args=parser.parse_args()
    if sys.platform!="win32":raise SystemExit("Windows便携包需要在Windows构建")
    output=args.output.resolve();work=args.work.resolve()
    if output.exists():raise FileExistsError("交付目录已存在，未覆盖："+str(output))
    work.mkdir(parents=True,exist_ok=True);log=work/"build.log";env=os.environ.copy()
    # Avoid pulling unrelated native tools (e.g. Poppler ICU) into a Qt program.
    env["PATH"]=str(Path(env["WINDIR"])/"System32")+";"+env["WINDIR"]
    env["MPLBACKEND"]="Agg"
    examples=work/"generated-examples";env["CSL_EXAMPLES_DIR"]=str(examples)
    print("1/4 构建三套完整示例",flush=True)
    if not args.reuse_examples:
        call([sys.executable,str(ROOT/"scripts/build_desktop_examples.py"),"--output",str(work/"example-results"),"--examples",str(examples)],env,log)
    elif not all((examples/(name+".cslproj")).is_file() for name in ("first-order","second-order","custom")):raise ValueError("复用的三套示例不完整")
    print("2/4 构建独立Windows程序",flush=True)
    call([sys.executable,"-m","PyInstaller",str(ROOT/"ControlStressLab.spec"),"--distpath",str(output),"--workpath",str(work/"pyinstaller"),"--noconfirm"],env,log)
    app=output/"ControlStressLab"
    shutil.copyfile(ROOT/"docs/PORTABLE_GUIDE.html",app/"使用说明.html")
    shutil.copyfile(ROOT/"LICENSE",app/"LICENSE.txt")
    (app/"开始使用.txt").write_text("ControlStressLab v1.0\n解压完整文件夹，双击 ControlStressLab.exe。\n无需安装Python；请保留_internal文件夹。\n先到研究项目页打开完整示例。使用说明见同目录HTML。\n",encoding="utf-8")
    notices=app/"THIRD_PARTY_LICENSES";notices.mkdir()
    packages={}
    for name in ("numpy","scipy","matplotlib","PySide6_Essentials","shiboken6","Pillow","contourpy","cycler","fonttools","kiwisolver","packaging","pyparsing","python_dateutil","six","tzdata","pyinstaller"):
        try:dist=importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:continue
        packages[name]=dist.version
        for f in dist.files or []:
            label=str(f).lower()
            if "licens" not in label and "copying" not in label:continue
            path=Path(dist.locate_file(f))
            if not path.is_file() or path.stat().st_size>4_000_000:continue
            target=notices/name/Path(str(f))
            if ".." in target.parts:continue
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    python_license=Path(sys.base_prefix)/"LICENSE.txt"
    if python_license.exists():shutil.copyfile(python_license,notices/"PYTHON-LICENSE.txt")
    source_files=list((ROOT/"src/controlstresslab").glob("*.py"))+[ROOT/"ControlStressLab.spec",ROOT/"scripts/desktop_entry.py"]
    metadata=dict(version="1.0.0",platform=platform.platform(),architecture=platform.machine(),python=platform.python_version(),
        dependencies=packages,source_sha256={p.relative_to(ROOT).as_posix():digest(p) for p in source_files},
        example_sha256={p.name:digest(p) for p in examples.glob("*.cslproj")},
        independent_runtime=True,clean_separate_machine_test=False)
    (app/"build-info.json").write_text(json.dumps(metadata,indent=2,ensure_ascii=False),encoding="utf-8")
    print("3/4 检查独立运行、迁移和缩放",flush=True)
    if args.verify:
        relocated=work/"中文 迁移验收/ControlStressLab";relocated.parent.mkdir(exist_ok=True);shutil.copytree(app,relocated)
        isolated=env.copy()
        for key in list(isolated):
            if key.startswith(("PYTHON","QT_","QML","MPL","CSL_")):isolated.pop(key,None)
        isolated["PATH"]=str(Path(env["WINDIR"])/"System32")+";"+env["WINDIR"];isolated["QT_QPA_PLATFORM"]="windows"
        report=work/"desktop-acceptance.json"
        call([str(relocated/"ControlStressLab.exe"),"--workspace",str(work/"runtime-workspace"),"--desktop-check",str(report)],isolated,log,cwd=relocated)
        data=json.loads(report.read_text(encoding="utf-8"))
        if not data.get("passed") or not data.get("frozen") or not all(v["frozen"] for v in data["workers"]):raise RuntimeError("独立运行验收未通过")
        shutil.copyfile(report,app/"desktop-acceptance.json")
        project=data["folders"]["relocated_project"]
        layouts=[]
        for scale in (1.5,2.0):
            check=work/("layout-"+str(scale)+".json");isolated["QT_SCALE_FACTOR"]=str(scale/data["dpr"])
            call([str(relocated/"ControlStressLab.exe"),"--workspace",str(work/"layout-workspace"),"--project",project,"--layout-check",str(check)],isolated,log,cwd=relocated)
            layout=json.loads(check.read_text(encoding="utf-8"))
            if not layout.get("passed") or abs(layout["dpr"]-scale)>1e-7:raise RuntimeError("缩放检查未通过")
            layouts.append(layout)
        (app/"layout-acceptance.json").write_text(json.dumps(layouts,indent=2,ensure_ascii=False),encoding="utf-8")
    print("4/4 保存校验清单与便携ZIP",flush=True)
    checks={p.relative_to(app).as_posix():digest(p) for p in sorted(app.rglob("*")) if p.is_file()}
    (app/"checksums.json").write_text(json.dumps(checks,indent=2,ensure_ascii=False),encoding="utf-8")
    archive=output.parent/"ControlStressLab-v1.0.0-Windows-x64.zip"
    if archive.exists():raise FileExistsError("ZIP已存在，未覆盖")
    with zipfile.ZipFile(archive,"x",zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(app.rglob("*")):
            if path.is_file():z.write(path,"ControlStressLab/"+path.relative_to(app).as_posix())
    with zipfile.ZipFile(archive) as z:
        if z.testzip():raise ValueError("ZIP结构检查失败")
        for name,h in checks.items():
            if hashlib.sha256(z.read("ControlStressLab/"+name)).hexdigest()!=h:raise ValueError("交付文件校验不一致")
    receipt=dict(version="1.0.0",executable=str(app/"ControlStressLab.exe"),archive=str(archive),sha256=digest(archive),
        bytes=archive.stat().st_size,package_files=len(checks)+1,verified=args.verify,work=str(work))
    (output.parent/"ControlStressLab-v1.0.0-delivery.json").write_text(json.dumps(receipt,indent=2,ensure_ascii=False),encoding="utf-8")
    archive.with_suffix(".sha256.txt").write_text(receipt["sha256"]+"  "+archive.name+"\n",encoding="utf-8")
    print(json.dumps(receipt,ensure_ascii=False),flush=True)
if __name__=="__main__":main()

