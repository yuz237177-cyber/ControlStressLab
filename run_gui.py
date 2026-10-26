"""Source-checkout desktop launcher; optional dependencies stay project-local."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
paths = [str(ROOT / p) for p in ("src", "outputs/gui-deps", "outputs/chart-deps", "outputs/science-deps")]
sys.path[:0] = paths
os.environ["PYTHONPATH"] = os.pathsep.join(paths + ([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else []))
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "outputs/mpl-cache"))

if __name__ == "__main__":
    if "--workspace" not in sys.argv:
        sys.argv.extend(["--workspace", str(ROOT / "outputs/gui")])
    try:
        from controlstresslab.gui import main
        main()
    except (ImportError, SystemExit) as exc:
        if isinstance(exc, SystemExit) and exc.code in (None, 0): raise
        if sys.executable.lower().endswith("pythonw.exe"):
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(exc)+"\n请参阅 docs/GUI_GUIDE.md 安装桌面依赖。", "ControlStressLab 启动失败", 16)
        raise
