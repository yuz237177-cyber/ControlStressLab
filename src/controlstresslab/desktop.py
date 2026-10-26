"""Portable entry point: same executable runs GUI and headless calculation workers."""
import os,sys
from pathlib import Path

def main():
    if "--worker" in sys.argv:
        sys.argv.remove("--worker")
        def arg(key):return sys.argv[sys.argv.index(key)+1]
        events=Path(arg("--events"));log=Path(arg("--log"))
        os.environ["MPLBACKEND"]="Agg"
        sys.stdout=events.open("w",encoding="utf-8",buffering=1);sys.__stdout__=sys.stdout
        sys.stderr=log.open("w",encoding="utf-8",buffering=1);sys.__stderr__=sys.stderr
        try:
            from .gui_worker import main as worker
            return worker()
        finally:sys.stdout.flush();sys.stderr.flush()
    if not os.environ.get("MPLCONFIGDIR"):
        workspace=Path(sys.argv[sys.argv.index("--workspace")+1]) if "--workspace" in sys.argv else Path(os.environ.get("LOCALAPPDATA",str(Path.home()/"AppData/Local")))/"ControlStressLab"
        os.environ["MPLCONFIGDIR"]=str(workspace/"cache")
    from .gui_window import main as gui
    gui()
if __name__=="__main__":raise SystemExit(main())
