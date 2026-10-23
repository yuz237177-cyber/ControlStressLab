"""Rebuild committed README figures and metrics from the current simulation."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from controlstresslab import DCMotor, PID, __version__, simulate
from controlstresslab.cli import demo_scenarios
from controlstresslab.metrics import evaluate
from controlstresslab.reporting import plot


def main() -> None:
    destination = ROOT / "docs" / "examples"
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    saturation_runs = []
    for scenario in demo_scenarios(0.01, 42):
        if scenario.name not in ("load_step", "saturation_release"):
            continue
        for label, anti in (("pid", False), ("pid_antiwindup", True)):
            run = simulate(DCMotor(), PID(anti_windup=anti), scenario, fail_fast=True)
            metrics = evaluate(run)
            if metrics["status"] != "completed":
                raise RuntimeError(f"preview run failed: {scenario.name}/{label}")
            records.append({"scenario": asdict(scenario), "controller_name": label,
                            "controller": run.controller, "plant": run.plant, "metrics": metrics})
            if scenario.name == "saturation_release":
                saturation_runs.append(run)

    rows = []
    for ordinary, anti in zip(saturation_runs[0].rows, saturation_runs[1].rows):
        rows.append({**ordinary, "anti_output": anti["true_output_rad_s"], "anti_input": anti["applied_V"]})
    svg = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "viewBox": "0 0 780 625",
                             "role": "img", "aria-labelledby": "title description"})
    ET.SubElement(svg, "title", {"id": "title"}).text = "PID comparison: saturation release"
    ET.SubElement(svg, "desc", {"id": "description"}).text = (
        "Synthetic reduced DC motor. Reference drops from 140 to 60 rad/s at 4 s. "
        "Conditional integration recovers sooner for this configuration. No hardware validation.")
    ET.SubElement(svg, "rect", {"width": "780", "height": "625", "fill": "#ffffff"})
    def text(x, y, content, size=14, color="#172033"):
        ET.SubElement(svg, "text", {"x": str(x), "y": str(y), "fill": color,
                                    "font-size": str(size), "font-family": "sans-serif"}).text = content
    text(18, 28, "ControlStressLab | Saturation release", 21)
    text(18, 53, "Synthetic motor | dt = 0.01 s | input limit = +/-12 V | same PID gains")
    groups = [
        ("Speed / rad/s", "rad/s", [("reference_rad_s", "#64748b", "Reference"),
                                    ("true_output_rad_s", "#2563eb", "PID"),
                                    ("anti_output", "#0f766e", "PID + anti-windup")], False, 80),
        ("Applied input / V", "V", [("applied_V", "#2563eb", "PID"),
                                    ("anti_input", "#0f766e", "PID + anti-windup")], True, 340),
    ]
    for title, unit, channels, actions_only, offset in groups:
        text(18, offset, title)
        markup = plot(rows, channels, unit, title, actions_only=actions_only, event_s=4.0)
        chart = ET.fromstring(markup[markup.index("<svg"):markup.index("</svg>") + 6])
        chart.set("x", "0")
        chart.set("y", str(offset + 5))
        chart.set("width", "780")
        chart.set("height", "230")
        svg.append(chart)
    text(18, 585, "Blue: PID | Green: PID + anti-windup | Gray: reference | Dashed: event at 4 s", 12)
    text(18, 610, "SYNTHETIC SIMULATION - NOT HARDWARE VALIDATED. Results apply to this configuration.", 12, "#92400e")
    (destination / "saturation-release.svg").write_bytes(ET.tostring(svg, encoding="utf-8", xml_declaration=True))
    snapshot = {"project_version": __version__, "evidence": "synthetic_assumption", "hardware_validated": False,
                "source_hash_encoding": "UTF-8 with LF newlines",
                "source_files_sha256": {p.name: hashlib.sha256(p.read_text(encoding="utf8").encode("utf8")).hexdigest()
                                        for p in sorted((ROOT / "src" / "controlstresslab").glob("*.py"))},
                "runs": records}
    (destination / "preview.json").write_text(json.dumps(snapshot, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print("README preview rebuilt: docs/examples/saturation-release.svg and preview.json")


if __name__ == "__main__":
    main()
