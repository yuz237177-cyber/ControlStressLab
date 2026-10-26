"""Portable GUI entry with a persistent startup error log."""
import sys,traceback,os
from pathlib import Path
if __name__=="__main__":
    try:
        from controlstresslab.desktop import main
        raise SystemExit(main())
    except Exception:
        workspace=Path(sys.argv[sys.argv.index("--workspace")+1]) if "--workspace" in sys.argv else Path(os.environ.get("LOCALAPPDATA",str(Path.home()/"AppData/Local")))/"ControlStressLab"
        workspace.mkdir(parents=True,exist_ok=True)
        log=workspace/"startup-error.log";log.write_text(traceback.format_exc(),encoding="utf-8")
        if "--desktop-check" in sys.argv:
            import json
            report=Path(sys.argv[sys.argv.index("--desktop-check")+1]);report.write_text(json.dumps(dict(passed=False,error=traceback.format_exc())),encoding="utf-8")
        elif "--worker" not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,"程序启动失败。详细信息已保存："+str(log),"ControlStressLab",16)
        raise SystemExit(1)
