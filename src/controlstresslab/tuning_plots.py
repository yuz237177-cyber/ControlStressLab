"""Plot saved finite-candidate evidence; no optimization or hidden reruns."""
from .experiment import read_trace

COLORS = ("#2878ff","#35b69f","#b991ee")


def draw_front(figure, summary, *, dark=False):
    figure.clear()
    ax = figure.add_subplot()
    feasible = [c for c in summary["candidates"] if c["feasible"]]
    front = set(summary["frontier_ids"])
    for c in feasible:
        ax.scatter(c["J1"],c["J2"],s=90 if c["candidate_id"] in front else 40,
                   marker="*" if c["candidate_id"] in front else "o",c="#2878ff" if c["candidate_id"] in front else "#8a95a6")
        ax.annotate(str(c["candidate_id"]),(c["J1"],c["J2"]),xytext=(5,5),textcoords="offset points",fontsize=10,color="#b3bac7" if dark else "#333333")
    if not feasible:
        ax.text(.5,.5,"No feasible candidate in the declared finite search",ha="center",transform=ax.transAxes,color="#b3bac7" if dark else "black")
    ax.set_xlabel("J1: family-balanced worst-seed normalized RMSE")
    ax.set_ylabel("J2: worst applied-input variation rate / (1/s)")
    ax.set_title("Finite feasible candidates | stars: nondominated")
    ax.grid(alpha=.15)
    if dark:
        from .gui_analysis import style_axes
        style_axes(ax)
    return ax


def draw_requirements(figure, records, *, dark=False):
    figure.clear()
    ax = figure.add_subplot()
    ids = sorted({r["candidate_id"] for r in records})
    categories = [("met","#35b69f"),("not_met","#e7a956"),("metric_invalid","#b991ee"),("run_failed","#dc6275")]
    left = [0]*len(ids)
    for state,color in categories:
        counts = [sum(r["candidate_id"]==cid and r["requirement"]==state for r in records) for cid in ids]
        ax.barh([str(i) for i in ids],counts,left=left,color=color,label=state)
        left = [a+b for a,b in zip(left,counts)]
    ax.set_xlabel("Declared run records (not independent real-world samples)")
    ax.set_ylabel("Candidate ID")
    ax.set_title("Requirements by candidate | failures kept separate")
    ax.legend(fontsize=8)
    if dark:
        from .gui_analysis import style_axes
        style_axes(ax)
    return ax


def comparison_views(folder, records, record):
    paired = [r for r in records if (r["family"],r["condition_index"],r["input_index"]) == (record["family"],record["condition_index"],record["input_index"])
              and r["candidate_id"] in (0,record["candidate_id"])]
    return [dict(rows=read_trace(folder,r),record=r,label="Baseline / c0" if r["candidate_id"]==0 else "Candidate / c"+str(r["candidate_id"])) for r in paired]


def build(output, summary, records):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .comparison_plots import draw
    target = output/"figures"; target.mkdir()
    def save(name,drawer):
        fig = plt.figure(figsize=(12,5.5),layout="constrained")
        drawer(fig)
        fig.text(.01,.01,"Synthetic finite conditions only. Applied-input variation is not energy. All raw records retained.",fontsize=8)
        fig.get_layout_engine().set(rect=(0,.045,1,.98))
        fig.savefig(target/(name+".png"),dpi=160)
        fig.savefig(target/(name+".svg"),metadata={"Date":None})
        plt.close(fig)
    if "frontier_ids" in summary: save("candidate-tradeoffs",lambda f:draw_front(f,summary))
    save("requirements",lambda f:draw_requirements(f,records))
    if "frontier_ids" in summary:
        representatives = list(dict.fromkeys(i for i in (summary["low_error_id"],summary["smooth_action_id"]) if i is not None))
    else: representatives = [summary["main_candidate_id"]]+[c["candidate_id"] for c in summary["candidates"] if "comparison" in c["roles"]]
    for cid in representatives:
        subset = [r for r in records if r["candidate_id"]==cid]
        # Preserve the hardest completed error; if none completed, show the failed trace explicitly.
        selected = max(subset,key=lambda r:r["metrics"]["normalized_rmse"] if r["metrics"]["normalized_rmse"] is not None else -1)
        views = comparison_views(output,records,selected)
        for channel in ("output","error","applied_input"):
            def drawer(fig,views=views,channel=channel,selected=selected):
                draw(fig,views,channel)
                fig.suptitle(f"{selected['subset']} | {selected['family']} | {selected['point']} | input {selected['input_index']}",fontsize=11)
            save(f"c{cid}-{channel}",drawer)
