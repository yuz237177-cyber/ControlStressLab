# Windows onedir build. Source snapshots are intentionally bundled for audit.
from pathlib import Path
import os
from PyInstaller.utils.hooks import collect_submodules,collect_data_files,copy_metadata
root=Path(SPECPATH)
example_root=Path(os.environ.get("CSL_EXAMPLES_DIR",str(root/"examples")))
datas=[(str(p),"controlstresslab") for p in (root/"src/controlstresslab").glob("*.py")]
datas += [(str(p),"examples") for p in example_root.glob("*.cslproj")]
datas += [(str(root/"docs/PORTABLE_GUIDE.html"),"docs")]
hidden=collect_submodules("controlstresslab")+["matplotlib.backends.backend_svg"]
a=Analysis([str(root/"scripts/desktop_entry.py")],pathex=[str(root/"src")],binaries=[],datas=datas,
    hiddenimports=hidden,hookspath=[],hooksconfig={"matplotlib":{"backends":["QtAgg","Agg","svg"]}},
    excludes=["tkinter","PyQt5","PyQt6","PySide2","IPython","pytest","control","pandas","openpyxl","lxml","torch","tensorflow","jax","dask","numba","notebook"],noarchive=False)
# Qt uses the Windows ICU API; an unrelated Poppler on build PATH must not replace it.
a.binaries=[item for item in a.binaries if Path(item[0]).name.lower() not in ("icuuc.dll","icudt78.dll")]
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name="ControlStressLab",debug=False,bootloader_ignore_signals=False,
    strip=False,upx=False,console=False,disable_windowed_traceback=False)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name="ControlStressLab")
