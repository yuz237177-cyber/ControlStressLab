"""Preserve a complete experiment, matching source snapshots and a verified ZIP."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def archive(source: Path, destination: Path) -> Path:
    source, destination = source.resolve(), destination.resolve()
    if not source.is_relative_to(ROOT) or not destination.is_relative_to(ROOT):
        raise ValueError("archive source and destination must stay inside this project")
    if destination == source or destination.is_relative_to(source):
        raise ValueError("archive destination must be outside the source directory")
    # Directory names may contain semantic versions such as v0.3.0.
    zipped = destination.with_name(destination.name+".zip")
    if destination.exists() or zipped.exists():
        raise FileExistsError("archive destination or ZIP already exists; choose a new name")
    if any(p.is_symlink() for p in source.rglob("*")):
        raise ValueError("archive does not follow symbolic links")
    checksums = json.loads((source / "checksums.json").read_text(encoding="utf8"))
    for name, digest in checksums.items():
        path = (source / name).resolve()
        if not path.is_relative_to(source) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"source checksum mismatch: {name}")
    status = json.loads((source / "status.json").read_text(encoding="utf8"))
    if not status.get("artifacts_complete"):
        raise ValueError("source experiment is not complete")
    shutil.copytree(source, destination)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf8"))
    snapshots = {}
    for name, digest in manifest["source_files_sha256"].items():
        if Path(name).name != name:
            raise ValueError("source snapshot name must be a plain filename")
        code = ROOT / "src/controlstresslab" / name
        matches = code.is_file() and hashlib.sha256(code.read_bytes()).hexdigest() == digest
        snapshots[name] = "matching_snapshot_saved" if matches else "original_bytes_not_available"
        if matches:
            (destination / "source").mkdir(exist_ok=True)
            shutil.copyfile(code, destination / "source" / name)
    guide = destination / ("ARCHIVE_README.md" if (source / "README.md").exists() else "README.md")
    if guide.exists():
        raise FileExistsError("archive guide would replace a source file")
    guide.write_text(
        "# 固定归档\n\n打开report.html查看完整报告和图片。原始数据、配置、逐次结果和校验值一并保留。\n"
        "source目录仅保存与实验manifest指纹一致的源码；缺失情况见archive_manifest.json。\n"
        "原始checksums.json仍校验原实验文件，archive_manifest.json另覆盖归档中的全部保留文件。\n"
        "此目录是历史快照，请用新目录保存后续实验。全部结果仍为合成仿真。\n", encoding="utf8", newline="\n")
    files = {p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(destination.rglob("*")) if p.is_file()}
    (destination / "archive_manifest.json").write_text(json.dumps({"source_experiment": source.relative_to(ROOT).as_posix(),
        "source_snapshots": snapshots, "files_sha256": files}, indent=2), encoding="utf8", newline="\n")
    with zipfile.ZipFile(zipped, "x", compression=zipfile.ZIP_DEFLATED) as stream:
        for path in sorted(destination.rglob("*")):
            if path.is_file():
                stream.write(path, destination.name + "/" + path.relative_to(destination).as_posix())
    with zipfile.ZipFile(zipped) as stream:
        if stream.testzip() is not None:
            raise ValueError("ZIP integrity check failed")
        for name, digest in files.items():
            if hashlib.sha256(stream.read(destination.name + "/" + name)).hexdigest() != digest:
                raise ValueError("ZIP content differs from preserved archive")
    print(f"Preserved {len(files)} files: {destination}")
    print(f"Verified ZIP: {zipped}")
    return zipped


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    archive(args.source, args.destination)
