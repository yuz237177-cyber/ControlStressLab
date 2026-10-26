"""Transactional artifacts for analysis jobs; experiment status is committed last."""
import hashlib
import json
from pathlib import Path
import platform
from . import __version__
from .cli import batch_status
from .experiment import atomic_json, sha, replace_file


def begin(output, schema, config, expected):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest = dict(schema_version=schema, package_version=__version__, python=platform.python_version(),
        config=config, expected_runs=expected, hardware_validated=False, evidence="synthetic_assumption",
        source_files_sha256={p.name: sha(p) for p in sorted(Path(__file__).parent.glob("*.py"))}, artifacts_complete=False)
    try:
        atomic_json(output/"status.json", batch_status("in_progress", expected, 0, 0))
        atomic_json(output/"manifest.json", manifest)
    except BaseException as exc:
        interrupted(output, manifest, [], 0, exc)
        raise
    return output, manifest


def checkpoint(output, manifest, records, failed):
    atomic_json(output/"status.json", batch_status("in_progress", manifest["expected_runs"], len(records), failed))


def finish(output, manifest, records, failed):
    if len(records) != manifest["expected_runs"]: raise ValueError("实际记录数与计划不一致，不能标记完整")
    atomic_json(output/"results.json", records)
    manifest.update(written_runs=len(records), failed_runs=failed, artifacts_complete=True)
    if (output/"config.json").is_file(): manifest["config_sha256"] = sha(output/"config.json")
    atomic_json(output/"manifest.json", manifest)
    final = batch_status("completed_with_failures" if failed else "completed", manifest["expected_runs"], len(records), failed, complete=True)
    raw = json.dumps(final, indent=2, ensure_ascii=False, allow_nan=False).encode("utf8")
    hashes = {p.relative_to(output).as_posix(): sha(p) for p in sorted(output.rglob("*")) if p.is_file() and p.relative_to(output).as_posix() not in ("status.json", "checksums.json")}
    hashes["status.json"] = hashlib.sha256(raw).hexdigest()
    atomic_json(output/"checksums.json", hashes)
    temporary = output/"status.json.tmp"
    temporary.write_bytes(raw)
    replace_file(temporary,output/"status.json")


def interrupted(output, manifest, records, failed, exc):
    manifest["artifacts_complete"] = False
    state = "interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "export_failure"
    for name, value in (("manifest.json", manifest), ("status.json", batch_status(state, manifest["expected_runs"], len(records), failed, error=exc))):
        try: atomic_json(output/name, value)
        except Exception: pass
