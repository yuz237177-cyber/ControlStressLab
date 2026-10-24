"""Optional figures for load-delay grids; missing and unrecovered remain explicit."""


def render(output, records, plan):
    import csv
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    import numpy as np
    from .stress_grid import CLASSIFICATIONS

    controllers = ("pid", "pid_antiwindup")
    labels = ("PID", "PID + anti-windup")
    colors = ("#2563eb", "#0f766e")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "svg.fonttype": "none", "svg.hashsalt": "controlstresslab-load-delay"})
    figures = []

    def save(fig, name, title):
        fig.suptitle(title, fontsize=14, fontweight="bold")
        fig.get_layout_engine().set(rect=(0, 0.12, 1, 0.87))
        fig.text(0.02, 0.018, "SYNTHETIC GRID | FIXED GAINS | MEASUREMENT DELAY ONLY | NO STABILITY GUARANTEE", fontsize=8, color="#92400e")
        fig.savefig(output / (name + ".png"), dpi=160, facecolor="white", metadata={"Software": "ControlStressLab"})
        path = output / (name + ".svg")
        fig.savefig(path, facecolor="white", metadata={"Creator": "ControlStressLab", "Date": None})
        path.write_text("\n".join(line.rstrip() for line in path.read_text(encoding="utf8").splitlines()) + "\n", encoding="utf8", newline="\n")
        plt.close(fig)
        figures.append((name, title))

    def edges(values):
        if len(values) == 1:
            return [values[0] - 0.01, values[0] + 0.01]
        return [values[0] - (values[1] - values[0]) / 2] + [(a + b) / 2 for a, b in zip(values, values[1:])] + [values[-1] + (values[-1] - values[-2]) / 2]

    def axes_grid(ax):
        ax.set_xlabel("Measurement delay / s")
        ax.set_ylabel("Load step / N m")
        ax.set_xticks(plan.delays_s)
        ax.set_yticks(plan.loads_Nm)
        ax.tick_params(labelsize=7)
        if min(plan.loads_Nm) <= 0.54 <= max(plan.loads_Nm) and plan.reference_rad_s == 60:
            ax.axhline(0.54, color="#c2410c", linestyle="--", linewidth=1.2)

    def matrix(subset, key):
        array = np.full((len(plan.loads_Nm), len(plan.delays_s)), np.nan)
        for record in subset:
            value = record.get(key, record["metrics"].get(key))
            if record["metrics"]["status"] == "completed" and value is not None:
                array[plan.loads_Nm.index(record["load_Nm"]), plan.delays_s.index(record["delay_s"])] = value
        return array

    legends = [Line2D([], [], color="black", marker="s", markerfacecolor="none", linestyle="", label="No recovery / missing"),
               Line2D([], [], color="red", marker="x", linestyle="", label="Execution / metric failure"),
               Line2D([], [], color="#c2410c", linestyle="--", label="Exact steady limit: 0.54 N m")]
    for key, stem, title, unit in (("iae_post_event_rad", "tracking_iae", "Post-event tracking IAE", "rad"),
                                   ("incremental_load_iae_rad", "incremental_iae", "Paired incremental load-output IAE", "rad"),
                                   ("recovery_time_s", "recovery_time", "Recovery within the observation window", "s"),
                                   ("input_total_variation_V", "input_variation", "Post-event input total variation (not energy)", "V")):
        subsets = [[r for r in records if r["controller_name"] == c] for c in controllers]
        arrays = [matrix(subset, key) for subset in subsets]
        finite = np.concatenate([a[np.isfinite(a)] for a in arrays])
        lo, hi = (float(finite.min()), float(finite.max())) if finite.size else (0, 1)
        if hi == lo:
            hi = lo + 1e-6
        fig, axes = plt.subplots(1, 2, figsize=(12, 6), layout="constrained")
        for ax, label, subset, array in zip(axes, labels, subsets, arrays):
            artist = ax.pcolormesh(edges(plan.delays_s), edges(plan.loads_Nm), np.ma.masked_invalid(array), shading="flat", cmap="viridis", vmin=lo, vmax=hi)
            axes_grid(ax)
            ax.set_title(label)
            for record in subset:
                if record["classification"] == "execution_or_metric_failure":
                    ax.plot(record["delay_s"], record["load_Nm"], "rx", markersize=5)
                elif (record.get(key, record["metrics"].get(key))) is None:
                    ax.plot(record["delay_s"], record["load_Nm"], marker="s", markerfacecolor="none", color="black", markersize=4)
        fig.colorbar(artist, ax=axes, label=f"{unit} (shared scale; interval {plan.event_s:g}-{plan.duration_s:g} s)", shrink=0.8)
        fig.legend(handles=legends, loc="center", bbox_to_anchor=(0.5, 0.065), ncol=3, fontsize=7)
        save(fig, stem, title)

    state_labels = ("Recovered", "Not recovered in window", "Exact steady reference infeasible", "Execution / metric failure")
    state_colors = ("#14b8a6", "#a78bfa", "#f59e0b", "#ef4444")
    fig, axes = plt.subplots(1, 2, figsize=(12, 6), layout="constrained")
    for ax, controller, label in zip(axes, controllers, labels):
        array = np.full((len(plan.loads_Nm), len(plan.delays_s)), np.nan)
        for record in records:
            if record["controller_name"] == controller:
                array[plan.loads_Nm.index(record["load_Nm"]), plan.delays_s.index(record["delay_s"])] = CLASSIFICATIONS.index(record["classification"])
        ax.pcolormesh(edges(plan.delays_s), edges(plan.loads_Nm), array, shading="flat", cmap=ListedColormap(state_colors), norm=BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], 4))
        axes_grid(ax)
        ax.set_title(label)
    fig.legend(handles=[Patch(facecolor=c, label=l) for c, l in zip(state_colors, state_labels)], loc="center", bbox_to_anchor=(0.5, 0.06), ncol=2, fontsize=8)
    save(fig, "operating_states", "Sampled engineering outcomes (not a mathematical stability map)")

    fig, axes = plt.subplots(1, 2, figsize=(12, 6), layout="constrained")
    for ax, controller, label in zip(axes, controllers, labels):
        array = np.full((len(plan.loads_Nm), len(plan.delays_s)), np.nan)
        for record in records:
            if record["controller_name"] == controller and record["pre_event_settled"] is not None:
                array[plan.loads_Nm.index(record["load_Nm"]), plan.delays_s.index(record["delay_s"])] = record["pre_event_settled"]
        ax.pcolormesh(edges(plan.delays_s), edges(plan.loads_Nm), np.ma.masked_invalid(array), shading="flat", cmap=ListedColormap(["#a78bfa", "#14b8a6"]), norm=BoundaryNorm([-0.5, 0.5, 1.5], 2))
        axes_grid(ax)
        ax.set_title(label)
    fig.legend(handles=[Patch(facecolor="#14b8a6", label="In error band for the whole pre-event dwell"),
                        Patch(facecolor="#a78bfa", label="Not settled before load"), Patch(facecolor="white", label="Missing observation")],
               loc="center", bbox_to_anchor=(0.5, 0.065), ncol=3, fontsize=7)
    save(fig, "pre_event_state", "Was the controller already unsettled before the load event?")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    fixed_load = plan.loads_Nm[len(plan.loads_Nm) // 2]
    for controller, label, color in zip(controllers, labels, colors):
        by_load = sorted([r for r in records if r["controller_name"] == controller and r["delay_s"] == 0], key=lambda r: r["load_Nm"])
        by_delay = sorted([r for r in records if r["controller_name"] == controller and r["load_Nm"] == fixed_load], key=lambda r: r["delay_s"])
        for ax, subset, xkey in ((axes[0], by_load, "load_Nm"), (axes[1], by_delay, "delay_s")):
            ax.plot([r[xkey] for r in subset], [r["metrics"]["iae_post_event_rad"] if r["metrics"]["status"] == "completed" else np.nan for r in subset], marker="o", color=color, label=label)
            ax.set_ylabel("Post-event tracking IAE / rad")
            ax.grid(alpha=0.2)
            ax.legend(fontsize=8)
    axes[0].set_title("Load sweep at zero delay")
    axes[0].set_xlabel("Load step / N m")
    axes[1].set_title(f"Delay sweep at load = {fixed_load:g} N m")
    axes[1].set_xlabel("Measurement delay / s")
    save(fig, "axis_slices", "Single-axis slices (separate y scales; no monotonicity assumed)")

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    for ax, (target_load, target_delay) in zip(axes.flat, ((0.15, 0), (0.15, 0.3), (0.5, 0.1), (0.6, 0.1))):
        load = min(plan.loads_Nm, key=lambda x: abs(x - target_load))
        delay = min(plan.delays_s, key=lambda x: abs(x - target_delay))
        ax.axhline(plan.reference_rad_s, color="#64748b", linestyle="--", label="Final reference")
        ax.axvline(plan.event_s, color="#c2410c", linestyle="--", linewidth=1)
        for controller, label, color in zip(controllers, labels, colors):
            record = next(r for r in records if r["controller_name"] == controller and r["load_Nm"] == load and r["delay_s"] == delay)
            with (output / record["trace_file"]).open(encoding="utf8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            ax.plot([float(r["time_s"]) for r in rows], [float(r["true_output_rad_s"]) if r["true_output_rad_s"] else np.nan for r in rows], color=color, linewidth=1, label=label)
        ax.set_title(f"Load = {load:g} N m | delay = {delay:g} s")
        ax.set_xlabel("Time / s")
        ax.set_ylabel("True output / rad/s")
        ax.legend(fontsize=7)
        ax.grid(alpha=0.2)
    save(fig, "representative_responses", "Representative sampled responses (orange: load event)")
    return figures
