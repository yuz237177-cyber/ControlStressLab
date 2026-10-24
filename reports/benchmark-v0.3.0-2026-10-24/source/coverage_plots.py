"""Optional unit-aware figures, built from the exported trajectories."""

import csv
import math


def build(output, records):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from .coverage import CONTROLLER_NAMES, model_spec

    destination = output / "figures"
    destination.mkdir()
    models = list(dict.fromkeys(r["model_name"] for r in records))
    scenarios = list(dict.fromkeys(r["scenario_name"] for r in records))
    index = {(r["model_name"], r["scenario_name"], r["controller_name"]): r for r in records}
    colors = dict(zip(CONTROLLER_NAMES, ("#777777", "#2268ad", "#e27b25", "#198678")))
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})

    def save(fig, name, title, note):
        fig.suptitle(title, fontsize=17)
        fig.text(0.015, 0.012, note + "\nSynthetic models; documented fixed configurations; no universal algorithm ranking.", fontsize=9)
        fig.get_layout_engine().set(rect=(0, 0.075, 1, 0.88))
        fig.savefig(destination / (name+".png"), dpi=160)
        svg = destination / (name+".svg")
        fig.savefig(svg, metadata={"Date": None})
        svg.write_text("\n".join(s.rstrip() for s in svg.read_text(encoding="utf8").splitlines())+"\n", encoding="utf8", newline="\n")
        plt.close(fig)

    def trace(record):
        with (output / record["trace_file"]).open(encoding="utf8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        return {k: np.array([float(row[k]) if row[k] else np.nan for row in rows])
                for k in ("time_s", "reference", "output", "measurement", "requested_input", "applied_input", "disturbance")}

    for family, channel in (("reference", "reference"), ("disturbance", "disturbance")):
        available = [s for s in scenarios if s.startswith(family+"_")]
        fig, axes = plt.subplots(3, 2, figsize=(13, 10), layout="constrained")
        spec = model_spec(models[0])
        scale = spec["scale"] if family == "reference" else spec["disturbance"]
        for ax, name in zip(axes.flat, available):
            data = trace(index[models[0], name, "PI"])
            ax.step(data["time_s"], data[channel]/scale, where="post", lw=1.3, color="#246c91")
            ax.set(title=name, xlabel="Time / s", ylabel="Signal / reference scale" if family == "reference" else "Signal / disturbance amplitude")
            ax.grid(alpha=0.2)
        for ax in list(axes.flat)[len(available):]: ax.set_visible(False)
        save(fig, family+"_waveforms", family.title()+" signal library", "Every displayed signal is pre-sampled on the 0.01 s control grid and held per interval.")

    preferred = ("reference_step", "reference_ramp", "reference_sine", "disturbance_prbs", "combined_sine_prbs", "measurement_noise_delay")
    chosen = [s for s in preferred if s in scenarios]
    chosen += [s for s in scenarios if s not in chosen][:max(0, 6-len(chosen))]
    for model in models:
        spec = model_spec(model)
        fig, axes = plt.subplots(3, 2, figsize=(13, 11), layout="constrained")
        for ax, name in zip(axes.flat, chosen):
            for ctrl in CONTROLLER_NAMES:
                rec = index[model, name, ctrl]
                data = trace(rec)
                ax.plot(data["time_s"], data["output"], label=ctrl, color=colors[ctrl], lw=1.2)
            ax.step(data["time_s"], data["reference"], where="post", color="#222222", ls="--", lw=1, label="Reference")
            ax.set(title=name, xlabel="Time / s", ylabel="Output / "+spec["units"]["output"])
            ax.grid(alpha=0.2)
            ax.legend(fontsize=8, ncols=3)
        for ax in list(axes.flat)[len(chosen):]: ax.set_visible(False)
        save(fig, model+"_responses", model+": tracking and disturbance responses", "All controllers receive paired reference, disturbance and noise; all 14 scenarios are retained in CSV.")

        fig, axes = plt.subplots(1, 3, figsize=(15, 9), layout="constrained")
        for ax, key, title in zip(axes, ("normalized_iae", "normalized_input_variation", "saturation_fraction"),
                                 ("NIAE", "Input variation / input limit", "Saturation time fraction")):
            matrix = np.array([[index[model, s, c]["metrics"][key] if index[model, s, c]["metrics"][key] is not None else np.nan
                                for c in CONTROLLER_NAMES] for s in scenarios])
            im = ax.imshow(np.ma.masked_invalid(matrix), aspect="auto", cmap="YlGnBu", vmin=0,
                           vmax=1 if key == "saturation_fraction" else None)
            fig.colorbar(im, ax=ax, shrink=0.7)
            ax.set(title=title, xticks=range(4), xticklabels=CONTROLLER_NAMES, yticks=range(len(scenarios)),
                   yticklabels=scenarios if key == "normalized_iae" else [])
            ax.tick_params(axis="x", labelrotation=50)
            for (i, j), value in np.ndenumerate(matrix):
                if not math.isfinite(value): label = "FAIL"
                else: label = f"{value:.2g}"
                ax.text(j, i, label, ha="center", va="center", fontsize=8,
                        color="white" if math.isfinite(value) and im.norm(value) > 0.6 else "#222")
        save(fig, model+"_metrics", model+": separate metrics", "NIAE = IAE / (reference scale x evaluated duration). Missing full-run metrics are FAIL, never zero.")

    fig, axes = plt.subplots(len(models), 1, figsize=(13, 3*len(models)), layout="constrained", squeeze=False)
    action_scenario = "measurement_noise_delay" if "measurement_noise_delay" in scenarios else scenarios[0]
    for ax, model in zip(axes[:, 0], models):
        for ctrl in CONTROLLER_NAMES:
            data = trace(index[model, action_scenario, ctrl])
            ax.step(data["time_s"][:-1], data["applied_input"][:-1], where="post", color=colors[ctrl], label=ctrl, lw=1)
        limit = model_spec(model)["limit"]
        ax.axhline(limit, ls="--", color="0.4", lw=0.7)
        ax.axhline(-limit, ls="--", color="0.4", lw=0.7)
        ax.set(title=model+": "+action_scenario, xlabel="Time / s", ylabel="Applied / "+model_spec(model)["units"]["input"])
        ax.grid(alpha=0.2)
        ax.legend(ncols=4, fontsize=8)
    save(fig, "applied_control_actions", "Applied control effort", "Only actual commands are shown. The terminal sample does not create an extra actuator command.")

    fig, axes = plt.subplots(2, 2, figsize=(13, 9), layout="constrained")
    for ax, model in zip(axes.flat, models):
        for ctrl in CONTROLLER_NAMES:
            selected = [r for r in records if r["model_name"] == model and r["controller_name"] == ctrl and r["metrics"]["status"] == "completed"]
            ax.scatter([r["metrics"]["normalized_input_variation"] for r in selected],
                       [r["metrics"]["normalized_rmse"] for r in selected], color=colors[ctrl], label=ctrl, alpha=0.8, s=28)
        ax.set(title=model, xlabel="Input variation / limit", ylabel="RMSE / reference scale")
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    for ax in list(axes.flat)[len(models):]: ax.set_visible(False)
    save(fig, "normalized_tradeoffs", "Tracking error and actuation trade-offs", "Each point is one scenario, not an independent random replicate. Units are normalized; no pooled winner is computed.")
