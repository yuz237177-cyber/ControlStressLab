"""Generate scientific figures from fresh, paired simulations (optional Matplotlib)."""

import argparse
from dataclasses import asdict
import hashlib
import html
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from controlstresslab import DCMotor, PID, __version__, simulate
from controlstresslab.cli import demo_scenarios
from controlstresslab.metrics import evaluate

COLORS = ("#2563eb", "#0f766e")
LABELS = ("PID", "PID + anti-windup")
TITLES = {"nominal": "Nominal reference step", "load_step": "Load step at 4 s",
          "measurement_noise": "Measurement noise: sigma = 1 rad/s",
          "measurement_delay": "Measurement delay: 0.1 s",
          "saturation_release": "Saturation release at 4 s"}
SHORT = ["Nominal", "Load\nstep", "Measurement\nnoise", "Measurement\ndelay", "Saturation\nrelease"]
EVIDENCE = "SYNTHETIC SIMULATION | NOT HARDWARE VALIDATED | dt = 0.01 s | seed = 42"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/examples/gallery")
    args = parser.parse_args()
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        parser.exit(1, f"Optional chart dependency missing: {exc}. Install with: python -m pip install '.[charts]'\n")
    destination = args.output
    destination.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 11,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.grid": True, "grid.alpha": 0.22, "svg.hashsalt": "controlstresslab", "svg.fonttype": "none"})
    scenarios = demo_scenarios(0.01, 42)
    pairs, records, figures = {}, [], []
    for scenario in scenarios:
        runs = []
        for label, anti in (("pid", False), ("pid_antiwindup", True)):
            run = simulate(DCMotor(), PID(anti_windup=anti), scenario, fail_fast=True)
            metrics = evaluate(run)
            if metrics["status"] != "completed":
                raise RuntimeError(f"Cannot compare incomplete run: {scenario.name}/{label}")
            records.append({"scenario": asdict(scenario), "controller_name": label,
                            "controller": run.controller, "plant": run.plant, "metrics": metrics,
                            "trace_sha256": hashlib.sha256(json.dumps(run.rows, allow_nan=False).encode("utf8")).hexdigest()})
            runs.append(run)
        pairs[scenario.name] = runs

    def save(fig, stem, title, description):
        fig.suptitle(title, fontsize=16, fontweight="bold", y=0.985)
        fig.text(0.01, 0.012, EVIDENCE, fontsize=8, color="#92400e")
        fig.subplots_adjust(top=0.89, bottom=0.13, left=0.09, right=0.97, hspace=0.55, wspace=0.28)
        fig.savefig(destination / f"{stem}.png", dpi=160, facecolor="white", metadata={"Software": f"ControlStressLab {__version__}"})
        fig.savefig(destination / f"{stem}.svg", facecolor="white", metadata={"Creator": f"ControlStressLab {__version__}", "Date": None})
        svg_path = destination / f"{stem}.svg"
        svg_text = "\n".join(line.rstrip() for line in svg_path.read_text(encoding="utf8").splitlines()) + "\n"
        svg_path.write_text(svg_text, encoding="utf8", newline="\n")
        plt.close(fig)
        figures.append({"file": stem, "title": title, "description": description})

    def event(ax, scenario):
        ax.axvline(scenario.recovery_start_s, color="#b45309", linestyle="--", linewidth=1, label="Evaluation event")
        ax.set_xlim(0, scenario.duration_s)

    def applied(ax, run, color, label, key="applied_V", linestyle="-"):
        rows = [r for r in run.rows if r["transition_completed"]]
        # Extend the final hold interval to its actual end, without issuing a new action.
        edges = [r["time_s"] for r in rows] + [rows[-1]["time_s"] + rows[-1]["interval_s"]]
        ax.stairs([r[key] for r in rows], edges, color=color, label=label, linestyle=linestyle, linewidth=1.2, baseline=None)

    descriptions = {
        "nominal": "正常参考阶跃：比较起步跟踪误差、误差带和限幅后的实际输入。",
        "load_step": "4秒加入0.15 N m负载。全程图保留起步过程，事件后指标另行比较。",
        "measurement_noise": "两控制器使用同一噪声序列；电压抖动属于控制代价，不能把输入总变差当作能耗。",
        "measurement_delay": "反馈延迟为0.1秒；控制器使用延迟测量，指标依据模型真实输出。",
        "saturation_release": "4秒参考从140回落至60 rad/s；140超过该假设模型的可达稳态转速，用于观察积分饱和后果。",
    }
    for scenario in scenarios:
        runs = pairs[scenario.name]
        fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
        rows = runs[0].rows
        axes[0].step([r["time_s"] for r in rows], [r["reference_rad_s"] for r in rows], where="post", color="#64748b", linestyle="--", label="Reference")
        axes[1].axhspan(-scenario.recovery_band, scenario.recovery_band, color="#94a3b8", alpha=0.2, label="Recovery error band")
        for run, color, label in zip(runs, COLORS, LABELS):
            times = [r["time_s"] for r in run.rows]
            axes[0].plot(times, [r["true_output_rad_s"] for r in run.rows], color=color, label=label)
            axes[1].plot(times, [r["reference_rad_s"] - r["true_output_rad_s"] for r in run.rows], color=color, label=label)
            applied(axes[2], run, color, label)
        for ax in axes:
            event(ax, scenario)
        axes[0].set_ylabel("Speed / rad/s")
        axes[1].set_ylabel("Error / rad/s")
        axes[2].set_ylabel("Applied input / V")
        axes[2].set_xlabel("Time / s")
        axes[0].legend(loc="best", ncol=2, fontsize=8)
        axes[1].legend(loc="upper right", fontsize=8)
        save(fig, scenario.name, TITLES[scenario.name], descriptions[scenario.name])

    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    specifications = [("iae_post_event_rad", "Post-event IAE / rad (log scale)", True, 1),
                      ("recovery_time_s", "Recovery within observation window / s", False, 1),
                      ("input_total_variation_V", "Full-window input total variation / V", False, 1),
                      ("saturation_fraction", "Full-window saturation time / %", False, 100)]
    for ax, (key, title, log_scale, multiplier) in zip(axes.flat, specifications):
        for j, (color, label) in enumerate(zip(COLORS, LABELS)):
            values = [evaluate(pairs[s.name][j])[key] for s in scenarios]
            x = [i + (j - 0.5) * 0.36 for i in range(len(scenarios))]
            for at, value in zip(x, values):
                if value is None:
                    ax.text(at, 0.5, "N/A", transform=ax.get_xaxis_transform(), ha="center", fontsize=8)
                    continue
                height = value * multiplier
                ax.bar(at, height, width=0.34, color=color)
                ax.annotate(f"{height:.2f}", (at, height), xytext=(0, 4), textcoords="offset points", ha="center", fontsize=7)
            ax.plot([], [], color=color, linewidth=7, label=label)
        ax.set_xticks(list(range(len(scenarios))))
        ax.set_xticklabels(SHORT, fontsize=8)
        ax.set_title(title)
        if log_scale:
            ax.set_yscale("log")
        ax.margins(y=0.28)
        ax.legend(fontsize=8)
    save(fig, "metric_overview", "Different metrics reveal different trade-offs",
         "五场景的事件后IAE、恢复时间、全评价窗口输入总变差和饱和比例。IAE面板使用对数轴；其余为线性轴。不同场景的事件含义不同，不把这些柱形合成总分。")

    fig, axes = plt.subplots(2, 2, figsize=(12, 7), sharex=True)
    for i, name in enumerate(("measurement_noise", "measurement_delay")):
        for j, (run, label) in enumerate(zip(pairs[name], LABELS)):
            ax = axes[i, j]
            subset = [r for r in run.rows if 0.4 <= r["time_s"] <= 2.0]
            times = [r["time_s"] for r in subset]
            ax.plot(times, [r["true_output_rad_s"] for r in subset], color=COLORS[j], label="True output")
            ax.plot(times, [r["measurement_rad_s"] for r in subset], color="#d97706", alpha=0.85, linewidth=1, label="Available measurement")
            ax.set_title(f"{TITLES[name]} | {label}")
            ax.set_ylabel("Speed / rad/s")
            ax.set_xlabel("Time / s (detail)")
            ax.legend(fontsize=8)
    save(fig, "feedback_detail", "What the controller actually sees",
         "放大0.4至2秒的反馈过程，上行为噪声，下行为延迟；左右分别为两种控制器。橙线是控制器可见的测量，不是真实状态。")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, name in zip(axes, ("load_step", "saturation_release")):
        for run, color, label in zip(pairs[name], COLORS, LABELS):
            cumulative, times, values = 0.0, [run.scenario.recovery_start_s], [0.0]
            for row in run.rows:
                if row["time_s"] < max(run.scenario.recovery_start_s, run.scenario.evaluation_start_s) - 1e-12 or not row["transition_completed"]:
                    continue
                cumulative += abs(row["reference_rad_s"] - row["true_output_rad_s"]) * row["interval_s"]
                times.append(row["time_s"] + row["interval_s"])
                values.append(cumulative)
            expected = evaluate(run)["iae_post_event_rad"]
            if not math.isclose(cumulative, expected, rel_tol=1e-12, abs_tol=1e-12):
                raise RuntimeError("Cumulative curve disagrees with reported post-event IAE")
            ax.plot(times, values, color=color, label=f"{label}: {cumulative:.3f} rad")
        ax.set_title(TITLES[name])
        ax.set_xlabel("Time / s (from event)")
        ax.set_ylabel("Cumulative post-event IAE / rad")
        ax.legend(fontsize=8)
    save(fig, "cumulative_error", "Error accumulated after the event",
         "积分从4秒事件起点累计，末值与对应事件后IAE逐项核对。两面板分别使用自己的纵轴范围；不能凭曲线视觉高度跨面板比较。")

    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    for ax, run, color, label in zip(axes, pairs["saturation_release"], COLORS, LABELS):
        applied(ax, run, color, "Actual input")
        applied(ax, run, "#94a3b8", "Requested input", key="command_V", linestyle="--")
        ax.axhline(12, color="#b45309", linewidth=0.8)
        ax.axhline(-12, color="#b45309", linewidth=0.8)
        event(ax, run.scenario)
        ax.set_ylabel("Input / V")
        ax.set_title(label)
        ax.legend(fontsize=8)
    axes[-1].set_xlabel("Time / s")
    save(fig, "requested_vs_applied", "Requested voltage versus actual limited action",
         "饱和回落场景的请求输入与实际输入，上下分别为普通和抗饱和PID。实际输入保持在±12 V；不同纵轴范围避免掩盖请求值的差异。")

    cards, markdown = [], ["# 图表集", "", "全部图表来自同一套合成电机仿真，未经硬件验证。每张提供PNG与SVG。", "",
                           "图表配置、指标、轨迹指纹和图片校验值见 [gallery.json](gallery.json)。", ""]
    for figure in figures:
        stem, title, description = figure["file"], figure["title"], figure["description"]
        cards.append(f'<section><h2>{html.escape(title)}</h2><p>{html.escape(description)}</p>'
                     f'<a href="{stem}.svg"><img src="{stem}.png" alt="{html.escape(title)}" loading="lazy"></a>'
                     f'<p><a href="{stem}.svg">SVG</a> · <a href="{stem}.png">PNG</a></p></section>')
        markdown.extend([f"## {title}", "", description, "", f"![{title}]({stem}.svg)", "", f"[PNG]({stem}.png) · [SVG]({stem}.svg)", ""])
    page = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            '<title>ControlStressLab 图表集</title><style>body{font:16px system-ui;max-width:1120px;margin:32px auto;padding:0 20px;color:#172033}'
            'img{width:100%;height:auto}section{border-top:1px solid #ddd;margin-top:28px;padding-top:12px}a{color:#1d4ed8}.evidence{background:#fff4d5;padding:16px}</style>'
            f'<h1>ControlStressLab {__version__} · 图表集</h1><p class="evidence">合成仿真，未经硬件验证。固定dt=0.01 s、seed=42；同场景两控制器使用相同噪声样本和增益。没有总分或普遍优劣结论。</p>'
            '<p>五场景响应、误差与实际输入；指标总览；噪声/延迟细节；事件后累计误差；请求/实际输入。</p>'
            '<p><a href="gallery.json">配置、指标和文件校验值</a></p>' + "".join(cards) + '</html>')
    (destination / "index.html").write_text(page, encoding="utf8", newline="\n")
    (destination / "README.md").write_text("\n".join(markdown), encoding="utf8", newline="\n")
    filenames = [f"{f['file']}.{extension}" for f in figures for extension in ("png", "svg")] + ["index.html", "README.md"]
    evidence = {"project_version": __version__, "evidence": "synthetic_assumption", "hardware_validated": False,
                "python": sys.version, "matplotlib": matplotlib.__version__, "source_hash_encoding": "UTF-8 with LF newlines",
                "generator_sha256": hashlib.sha256(Path(__file__).read_text(encoding="utf8").encode("utf8")).hexdigest(),
                "source_files_sha256": {p.name: hashlib.sha256(p.read_text(encoding="utf8").encode("utf8")).hexdigest()
                                        for p in sorted((ROOT / "src/controlstresslab").glob("*.py"))},
                "runs": records, "figures": figures,
                "files_sha256": {name: hashlib.sha256((destination / name).read_bytes()).hexdigest() for name in filenames}}
    (destination / "gallery.json").write_text(json.dumps(evidence, indent=2, allow_nan=False), encoding="utf8", newline="\n")
    print(f"Generated {len(figures)} figures, each as PNG and SVG: {destination}")


if __name__ == "__main__":
    main()
