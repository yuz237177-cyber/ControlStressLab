"""Discrete cells: common controller scale, failed cells never become zero."""


def draw_map(ax, summary, config, controller, metric):
    import numpy as np
    from matplotlib.colors import ListedColormap, BoundaryNorm
    from matplotlib.patches import Rectangle
    from .robustness import AXIS_LABELS
    nx = len(config["axes"][0]["values"])
    ny = len(config["axes"][1]["values"]) if len(config["axes"]) == 2 else 1
    values = np.full((ny, nx), np.nan)
    states = {"incomplete": 0, "met": 1, "not_met": 2, "run_failed": 3}
    cells = [c for c in summary["cells"] if c["controller_name"] == controller]
    for cell in cells:
        x, y = cell["axis_indices"]
        v = states[cell["requirement"]] if metric == "requirement" else cell["worst_observed"][metric]
        if v is not None: values[y, x] = v
    if metric == "requirement":
        cmap = ListedColormap(["#646b75", "#3f9e83", "#d8a34c", "#c95f65"])
        image = ax.imshow(values, origin="lower", interpolation="nearest", cmap=cmap, norm=BoundaryNorm([-.5,.5,1.5,2.5,3.5], 4), aspect="auto")
    else:
        all_values = [c["worst_observed"][metric] for c in summary["cells"] if c["worst_observed"][metric] is not None]
        high = max(all_values, default=1)
        image = ax.imshow(np.ma.masked_invalid(values), origin="lower", interpolation="nearest", cmap="viridis", vmin=0, vmax=high if high > 0 else 1, aspect="auto")
    for cell in cells:
        x, y = cell["axis_indices"]
        state = cell["requirement"]
        v = values[y, x]
        if metric != "requirement" and state in ("run_failed", "incomplete"):
            ax.add_patch(Rectangle((x-.5,y-.5),1,1,facecolor="#6a3038" if state == "run_failed" else "#464b55",edgecolor="#cbd1dc",hatch="xx" if state == "run_failed" else "//",lw=.4))
        if nx*ny <= 81:
            text = ("WAIT", "PASS", "LIMIT", "FAIL")[int(v)] if metric == "requirement" else "FAIL" if state == "run_failed" else "WAIT" if state == "incomplete" else f"{v:.3g}"
            ax.text(x,y,text,ha="center",va="center",color="white",fontsize=9,weight="bold")
    ax.set_xticks(range(nx), [f"{v:g}" for v in config["axes"][0]["values"]])
    ax.set_yticks(range(ny), [f"{v:g}" for v in config["axes"][1]["values"]] if len(config["axes"]) == 2 else ["fixed"])
    ax.set_xlabel(config["axes"][0]["key"])
    ax.set_ylabel(config["axes"][1]["key"] if len(config["axes"]) == 2 else "single-axis scan")
    ax.set_title(controller+" | "+metric+" | max over supplied noise seeds", fontsize=11)
    return image


def build(output, summary, config):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .robustness import METRICS
    destination = output/"figures"
    destination.mkdir()
    for name in config["base"]["selected_controllers"]:
        for key in (*METRICS, "requirement"):
            fig, ax = plt.subplots(figsize=(10,5), layout="constrained")
            image = draw_map(ax, summary, config, name, key)
            if key == "requirement":
                bar = fig.colorbar(image, ax=ax, ticks=[0,1,2,3])
                bar.ax.set_yticklabels(["Incomplete", "Requirements met", "Requirements not met", "Run failed"])
            else:
                fig.colorbar(image, ax=ax, label=key+" (physical units in config/records)")
            fig.suptitle("ControlStressLab | Finite-grid parameter scan")
            fig.text(.01,.01,"Finite grid only. Failed seed masks numeric cell. No robust stability proof or real-world failure probability.",fontsize=8)
            fig.get_layout_engine().set(rect=(0,.05,1,.95))
            fig.savefig(destination/(name+"__"+key+".png"), dpi=150)
            fig.savefig(destination/(name+"__"+key+".svg"), metadata={"Date":None})
            plt.close(fig)
