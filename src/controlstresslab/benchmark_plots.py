"""Figures from saved training logs and every held-out condition, without retuning."""

import csv


def build(output, records, training, summary, config):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from .benchmark import summarize
    from .benchmark_design import FAMILIES, spec_for

    dest = output / "figures"
    dest.mkdir()
    models, names = config["models"], config["controllers"]
    palette = dict(zip(("PI", "PID_aw", "TwoDOF_PID", "LADRC"), ("#777777", "#2268ad", "#e27b25", "#198678")))
    selections = {(g["model"], g["controller"]): min((c for c in g["candidates"] if c["assessment"]["feasible"]),
        key=lambda c: (c["assessment"]["objective"], c["candidate_index"])) for g in training}
    summary_index = {(s["model"], s["controller"], s["phase"]): s for s in summary}
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})

    def save(fig, name, title, note):
        fig.suptitle(title, fontsize=16)
        fig.text(0.015, 0.012, note+"\nSynthetic models; frozen held-out protocol; equal candidate count does not imply universal algorithm fairness.", fontsize=8.5)
        fig.get_layout_engine().set(rect=(0, 0.085, 1, 0.88))
        fig.savefig(dest / (name+".png"), dpi=160)
        svg = dest / (name+".svg")
        fig.savefig(svg, metadata={"Date": None})
        svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf8").splitlines())+"\n", encoding="utf8", newline="\n")
        plt.close(fig)

    def valid(v): return np.nan if v is None else v

    cache = {}
    def trace(r):
        name = r["trace_file"]
        if name not in cache:
            with (output / name).open(encoding="utf8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            cache[name] = {k: np.array([float(row[k]) if row[k] else np.nan for row in rows])
                           for k in ("time_s", "reference", "output", "applied_input")}
        return cache[name]

    fig, axes = plt.subplots(len(models), len(names), figsize=(4*len(names), 3.5*len(models)+1), layout="constrained", squeeze=False)
    for group in training:
        model, name = group["model"], group["controller"]
        ax = axes[models.index(model), names.index(name)]
        for c in group["candidates"]:
            a = c["assessment"]
            if a["objective"] is not None:
                ax.scatter(c["candidate_index"], a["objective"], c=palette[name] if a["feasible"] else "#c64444", marker="o" if a["feasible"] else "x", s=25)
        chosen = selections[model, name]
        ax.scatter(chosen["candidate_index"], chosen["assessment"]["objective"], marker="*", color="#111", s=110, label="Selected")
        ax.axhline(group["candidates"][0]["assessment"]["objective"], color="0.5", ls="--", lw=0.8, label="Baseline score")
        ax.set(title=f"{model} / {name}", xlabel="Candidate index (0 = baseline)", ylabel="Training mean NIAE")
        ax.grid(alpha=0.2)
        ax.legend(fontsize=7)
    save(fig, "training_search", "Training-only parameter selection", "Colored circles: feasible; red crosses: rejected by training constraints; black star: chosen without held-out scores.")

    fig, axes = plt.subplots(1, len(models), figsize=(7*len(models), 5), layout="constrained", squeeze=False)
    for ax, model in zip(axes[0], models):
        for group in (g for g in training if g["model"] == model):
            name = group["controller"]
            finite = [c for c in group["candidates"] if c["assessment"]["objective"] is not None]
            for feasible, marker in ((True, "o"), (False, "x")):
                subset = [c["assessment"] for c in finite if c["assessment"]["feasible"] == feasible]
                ax.scatter([a["worst_variation_rate"] for a in subset], [a["objective"] for a in subset],
                    marker=marker, color=palette[name], alpha=0.65, s=25, label=name if feasible else None)
        ax.axvline(config["max_training_variation_rate"], color="#b33", ls="--", label="Variation constraint")
        ax.set(title=model, xlabel="Worst training TV / (limit x duration), 1/s", ylabel="Mean training NIAE")
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    save(fig, "training_tradeoffs", "Tracking and input-motion constraints", f"Feasibility also requires worst training saturation fraction <= {config['max_training_saturation_fraction']:g}; x marks any rejected candidate.")

    fig, axes = plt.subplots(len(models), 4, figsize=(16, 3.5*len(models)+1), layout="constrained", squeeze=False)
    for i, model in enumerate(models):
        for j, family in enumerate(FAMILIES):
            ax, x = axes[i, j], np.arange(len(names))
            for phase, offset, alpha in (("baseline", -0.18, 0.35), ("tuned", 0.18, 0.95)):
                y = [valid(summary_index[model, n, phase]["families"][family]["normalized_iae"]) for n in names]
                ax.bar(x+offset, y, width=0.35, color=[palette[n] for n in names], alpha=alpha, label=phase)
            ax.set(title=model+" / "+family, xticks=x, xticklabels=names, ylabel="Held-out NIAE")
            ax.tick_params(axis="x", labelrotation=40)
            ax.grid(axis="y", alpha=0.2)
            ax.legend(fontsize=8)
    save(fig, "heldout_family_errors", "Frozen tests: error by family", "Each bar averages all parameter factors and specified seeds within its family. Failed groups are missing, never zero.")

    fig, axes = plt.subplots(1, len(models), figsize=(7*len(models), 5), layout="constrained", squeeze=False)
    for ax, model in zip(axes[0], models):
        for name in names:
            for phase, marker in (("baseline", "o"), ("tuned", "^")):
                subset = [r for r in records if r["model_name"] == model and r["controller_name"] == name and r["phase"] == phase and r["metrics"]["status"] == "completed"]
                ax.scatter([r["metrics"]["input_variation_rate"] for r in subset], [r["metrics"]["normalized_iae"] for r in subset],
                    marker=marker, color=palette[name], s=22, alpha=0.6, label=name+" / "+phase)
        ax.set(title=model, xlabel="TV / (input limit x evaluated duration), 1/s", ylabel="Held-out NIAE")
        ax.grid(alpha=0.2)
        ax.legend(fontsize=7, ncols=2)
    save(fig, "heldout_tradeoffs", "Frozen tests: error and actuation effort", "Each point is one condition, not an independent random replicate. Training constraints do not constrain held-out behavior.")

    factor = min(config["parameter_factors"], key=lambda f: abs(f-1))
    seed = config["heldout_seeds"][0]
    chosen_families = ("sine", "binary_disturbance", "noise_delay")
    for model in models:
        fig, axes = plt.subplots(3, 2, figsize=(13, 10), layout="constrained", sharey="row")
        for i, family in enumerate(chosen_families):
            for j, phase in enumerate(("baseline", "tuned")):
                ax = axes[i, j]
                for name in names:
                    r = next(r for r in records if r["model_name"] == model and r["controller_name"] == name and r["phase"] == phase and r["family"] == family and r["parameter_factor"] == factor and r["seed"] == (0 if family == "sine" else seed))
                    data = trace(r)
                    ax.plot(data["time_s"], data["output"], color=palette[name], label=name, lw=1.1)
                ax.step(data["time_s"], data["reference"], where="post", ls="--", color="#222", lw=0.9, label="Reference")
                ax.set(title=family+" / "+phase, xlabel="Time / s", ylabel="Output / "+spec_for(model)["units"]["output"])
                ax.grid(alpha=0.2)
                ax.legend(fontsize=7, ncols=3)
        save(fig, model+"_responses", model+": baseline and frozen tuned responses", f"Display rule fixed in code: factor closest to 1 ({factor:g}), first configured seed ({seed}); complete test grid retained in CSV.")

    fig, axes = plt.subplots(len(models), 2, figsize=(13, 3.5*len(models)+1), layout="constrained", squeeze=False, sharey="row")
    for i, model in enumerate(models):
        for j, phase in enumerate(("baseline", "tuned")):
            ax = axes[i, j]
            for name in names:
                r = next(r for r in records if r["model_name"] == model and r["controller_name"] == name and r["phase"] == phase and r["family"] == "noise_delay" and r["parameter_factor"] == factor and r["seed"] == seed)
                data = trace(r)
                ax.step(data["time_s"][:-1], data["applied_input"][:-1], where="post", lw=0.8, color=palette[name], label=name)
            ax.set(title=model+" / "+phase, xlabel="Time / s", ylabel="Applied input / "+spec_for(model)["units"]["input"])
            ax.grid(alpha=0.2)
            ax.legend(fontsize=8, ncols=4)
    save(fig, "noise_control_effort", "Noise + measurement delay: actual applied actions", f"Paired seed {seed}, parameter factor {factor:g}. Terminal sample has no extra command. All traces and other seeds are retained.")

    fig, axes = plt.subplots(len(models), 2, figsize=(13, 3.5*len(models)+1), layout="constrained", squeeze=False)
    for i, model in enumerate(models):
        for j, phase in enumerate(("baseline", "tuned")):
            ax = axes[i, j]
            for name in names:
                factors = sorted(config["parameter_factors"])
                values = []
                for f in factors:
                    rows = [r for r in records if r["model_name"] == model and r["controller_name"] == name and r["phase"] == phase and r["parameter_factor"] == f]
                    values.append(valid(summarize(rows)[0]["normalized_iae"]))
                ax.plot(factors, values, marker="o", color=palette[name], label=name)
            ax.set(title=model+" / "+phase, xlabel="Time constant factor" if model == "first_order" else "Mass factor", ylabel="Family-balanced held-out NIAE")
            ax.grid(alpha=0.2)
            ax.legend(fontsize=8)
    save(fig, "parameter_sensitivity", "Parameter mismatch after nominal-only tuning", "Other physical parameters stay fixed; controllers keep nominal knowledge and fixed gains. Lines connect tested factors, not a stability boundary.")
