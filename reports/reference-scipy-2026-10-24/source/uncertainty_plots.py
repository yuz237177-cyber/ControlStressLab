"""Optional Matplotlib views of recorded grids; missing outcomes remain missing."""


def render(output, records, plan):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.lines import Line2D

    colors = ("#2563eb", "#0f766e")
    labels = ("PID", "PID + anti-windup")
    controllers = ("pid", "pid_antiwindup")
    scenarios = ("nominal", "load_step")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "svg.fonttype": "none", "svg.hashsalt": "controlstresslab-uncertainty"})
    figures = []

    def save(fig, stem, title):
        fig.suptitle(title, fontsize=15, fontweight="bold")
        fig.get_layout_engine().set(rect=(0, 0.11, 1, 0.88))
        fig.text(0.02, 0.015, "SYNTHETIC GRID | FIXED GAINS | NO HARDWARE VALIDATION OR CONTINUOUS-REGION GUARANTEE", fontsize=8, color="#92400e")
        fig.savefig(output / (stem + ".png"), dpi=160, facecolor="white", metadata={"Software": "ControlStressLab"})
        path = output / (stem + ".svg")
        fig.savefig(path, facecolor="white", metadata={"Creator": "ControlStressLab", "Date": None})
        path.write_text("\n".join(line.rstrip() for line in path.read_text(encoding="utf8").splitlines()) + "\n", encoding="utf8", newline="\n")
        plt.close(fig)
        figures.append((stem, title))

    def edges(levels):
        if len(levels) == 1:
            return [levels[0] - 0.1, levels[0] + 0.1]
        return [levels[0] - (levels[1] - levels[0]) / 2] + [(a + b) / 2 for a, b in zip(levels, levels[1:])] + [levels[-1] + (levels[-1] - levels[-2]) / 2]

    def axes_grid(ax):
        ax.set_xlabel("Inertia factor J / J0")
        ax.set_ylabel("Mechanical friction factor b / b0")
        ax.set_xticks(plan.inertia_factors)
        ax.set_yticks(plan.friction_factors)
        ax.tick_params(labelsize=8)
        ax.plot(1, 1, marker="*", color="white", markeredgecolor="black", markersize=13)

    def matrix(subset, key):
        data = np.full((len(plan.friction_factors), len(plan.inertia_factors)), np.nan)
        for record in subset:
            value = record[key] if key == "incremental_load_iae_rad" else record["metrics"][key]
            if record["metrics"]["status"] == "completed" and value is not None:
                data[plan.friction_factors.index(record["friction_factor"]), plan.inertia_factors.index(record["inertia_factor"])] = value
        return data

    for scenario in scenarios:
        specifications = [("iae_post_event_rad", "iae", "rad", "Post-event tracking IAE"),
                          ("recovery_time_s", "recovery", "s", "Recovery within observation window")]
        if scenario == "load_step":
            specifications.append(("incremental_load_iae_rad", "incremental", "rad", "Incremental load-output IAE"))
        for key, suffix, unit, metric_title in specifications:
            subsets = [[r for r in records if r["scenario"] == scenario and r["controller_name"] == c] for c in controllers]
            arrays = [matrix(subset, key) for subset in subsets]
            finite = np.concatenate([array[np.isfinite(array)] for array in arrays])
            lo, hi = (float(finite.min()), float(finite.max())) if finite.size else (0, 1)
            if hi == lo:
                hi = lo + 1e-6
            fig, axes = plt.subplots(1, 2, figsize=(11, 5.2), layout="constrained")
            for ax, label, subset, array in zip(axes, labels, subsets, arrays):
                artist = ax.pcolormesh(edges(plan.inertia_factors), edges(plan.friction_factors), np.ma.masked_invalid(array),
                                       shading="flat", cmap="viridis", vmin=lo, vmax=hi)
                axes_grid(ax)
                ax.set_title(label)
                for record in subset:
                    if record["metrics"]["status"] != "completed":
                        ax.plot(record["inertia_factor"], record["friction_factor"], "rx", markersize=8)
                    elif (record[key] if key == "incremental_load_iae_rad" else record["metrics"][key]) is None:
                        ax.plot(record["inertia_factor"], record["friction_factor"], marker="s", markerfacecolor="none", color="black", markersize=7)
            fig.legend(handles=[Line2D([], [], marker="*", linestyle="", color="black", label="Nominal point"),
                                   Line2D([], [], marker="x", linestyle="", color="red", label="Failed run / metric"),
                                   Line2D([], [], marker="s", linestyle="", markerfacecolor="none", color="black", label="Not recovered / missing")], fontsize=7,
                       loc="center", bbox_to_anchor=(0.5, 0.06), ncol=3)
            fig.colorbar(artist, ax=axes, label=f"{metric_title} / {unit} (shared scale)", shrink=0.75)
            save(fig, scenario + "_" + suffix, f"{scenario}: {metric_title}")

    fig, axes = plt.subplots(2, 2, figsize=(11, 7), layout="constrained")
    for row, scenario in enumerate(scenarios):
        for col, (factor, fixed, title) in enumerate((("inertia_factor", "friction_factor", "J / J0 (b fixed at b0)"),
                                                     ("friction_factor", "inertia_factor", "b / b0 (J fixed at J0)"))):
            ax = axes[row, col]
            for controller, label, color in zip(controllers, labels, colors):
                subset = sorted([r for r in records if r["scenario"] == scenario and r["controller_name"] == controller and r[fixed] == 1], key=lambda r: r[factor])
                ax.plot([r[factor] for r in subset], [(r["incremental_load_iae_rad"] if scenario == "load_step" else r["metrics"]["iae_post_event_rad"]) if r["metrics"]["status"] == "completed" else np.nan for r in subset],
                        marker="o", color=color, label=label)
            ax.set_title(scenario)
            ax.set_xlabel(title)
            ax.set_ylabel("Incremental load-output IAE / rad" if scenario == "load_step" else "Post-event IAE / rad")
            ax.grid(alpha=0.2)
            ax.legend(fontsize=8)
    save(fig, "one_factor_slices", "One-factor slices through the nominal point (separate y scales)")

    fig, axes = plt.subplots(1, 2, figsize=(11, 5), layout="constrained")
    for ax, scenario in zip(axes, scenarios):
        ordinary = matrix([r for r in records if r["scenario"] == scenario and r["controller_name"] == controllers[0]], "iae_post_event_rad")
        anti = matrix([r for r in records if r["scenario"] == scenario and r["controller_name"] == controllers[1]], "iae_post_event_rad")
        delta = anti - ordinary
        finite = delta[np.isfinite(delta)]
        span = max(float(np.abs(finite).max()), 1e-9) if finite.size else 1.0
        artist = ax.pcolormesh(edges(plan.inertia_factors), edges(plan.friction_factors), np.ma.masked_invalid(delta), shading="flat", cmap="RdBu_r", vmin=-span, vmax=span)
        for bi, ji in np.argwhere(~np.isfinite(delta)):
            ax.plot(plan.inertia_factors[ji], plan.friction_factors[bi], "rx")
        for bi, ji in np.argwhere(np.isfinite(delta) & (delta > 0)):
            ax.plot(plan.inertia_factors[ji], plan.friction_factors[bi], marker="+", color="black")
        axes_grid(ax)
        ax.set_title(scenario + " | anti-windup minus PID")
        fig.colorbar(artist, ax=ax, label="Difference in post-event IAE / rad", shrink=0.75)
    save(fig, "paired_difference", "Tracking IAE difference: blue < 0, red / '+' > 0 (separate scales)")
    return figures
