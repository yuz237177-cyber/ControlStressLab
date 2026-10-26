"""Qt-free subprocess bridge: newline JSON events, cooperative cancel marker."""

import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
import traceback

from .experiment import Cancelled, atomic_json, execute, export_zip


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cancel", type=Path, required=True)
    parser.add_argument("--job-status", type=Path, required=True)
    parser.add_argument("--events",type=Path);parser.add_argument("--log",type=Path)
    args = parser.parse_args()
    def emit(value):
        print(json.dumps(value, ensure_ascii=True, allow_nan=False), flush=True)
    try:
        request = json.loads(args.request.read_text(encoding="utf8"))
        atomic_json(args.job_status, dict(state="running", output=str(args.output)))
        with redirect_stdout(sys.stderr):
            # Keep the protocol on original stdout, even when old batch functions log.
            original = sys.__stdout__
            def progress(value):
                original.write(json.dumps(value, ensure_ascii=True, allow_nan=False)+"\n")
                original.flush()
            if request["kind"] == "experiment":
                report, failed = execute(args.output, request["config"], plots=True, progress=progress, should_cancel=args.cancel.exists)
            elif request["kind"] == "model_preview":
                from .model_analysis import execute as preview
                report, failed = preview(args.output, request["config"], plots=True, progress=progress, should_cancel=args.cancel.exists)
            elif request["kind"] == "frequency":
                from .frequency import execute as analyze
                report,failed=analyze(args.output,request["config"],plots=True,progress=progress,should_cancel=args.cancel.exists)
            elif request["kind"]=="project_export":
                from .projects import export_bundle
                report=export_bundle(request["config"]["folder"],request["config"]["destination"],args.cancel.exists);failed=0
            elif request["kind"]=="project_import":
                from .projects import import_bundle
                report=import_bundle(request["config"]["archive"],request["config"]["destination"],args.cancel.exists);failed=0
            elif request["kind"] == "benchmark":
                from .benchmark import execute as benchmark
                report, failed = benchmark(args.output, request["config"], plots=True, progress=progress, should_cancel=args.cancel.exists)
            elif request["kind"] in ("robustness", "comparison"):
                from importlib import import_module
                runner = import_module("controlstresslab."+request["kind"]).execute
                report, failed = runner(args.output, request["config"], plots=True, progress=progress, should_cancel=args.cancel.exists)
            elif request["kind"] in ("tuning_search", "tuning_freeze", "tuning_validation"):
                if request["kind"] == "tuning_search":
                    from .tuning import execute as runner
                elif request["kind"] == "tuning_freeze":
                    from .tuning_validation import freeze as runner
                else:
                    from .tuning_validation import execute as runner
                report, failed = runner(args.output, request["config"], plots=True, progress=progress, should_cancel=args.cancel.exists)
            elif request["kind"] == "export":
                progress(dict(event="progress", stage="打包并逐文件校验报告", written=0, expected=1, failed=0))
                export_zip(Path(request["config"]["folder"]), Path(request["config"]["destination"]), should_cancel=args.cancel.exists)
                report, failed = Path(request["config"]["folder"]) / "report.html", 0
            else:
                raise ValueError("未知任务类型")
        state = "completed_with_failures" if failed else "completed"
        final = dict(event="finished", state=state, report=str(report), output=str(args.output), failed=failed,
                     runtime=dict(frozen=bool(getattr(sys,"frozen",False)),executable=sys.executable,prefix=sys.prefix))
        atomic_json(args.job_status, final)
        emit(final)
        return 1 if failed else 0
    except (KeyboardInterrupt, SystemExit) as exc:
        value = dict(event="finished", state="cancelled" if args.cancel.exists() or isinstance(exc, Cancelled) else "interrupted", output=str(args.output), message=str(exc))
        atomic_json(args.job_status, value)
        emit(value)
        return 2
    except Exception as exc:
        value = dict(event="finished", state="failed", output=str(args.output), message=f"{type(exc).__name__}: {exc}")
        atomic_json(args.job_status, value)
        emit(value)
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__": raise SystemExit(main())
