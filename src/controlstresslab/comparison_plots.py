"""Shared-axis overlays, with each original reference retained when it differs."""
COLORS = ("#2878ff", "#e7a956", "#35b69f", "#b991ee", "#e36b84", "#81a0b1", "#cbbf72", "#76a86c")


def draw(figure, views, channel="output", *, dark=False):
    from .experiment import saved_reference
    from .comparison import digest_json
    figure.clear()
    ax = figure.add_subplot()
    if dark:
        ax.set_facecolor("#121315")
        ax.tick_params(colors="#b3bac7")
        ax.xaxis.label.set_color("#b3bac7"); ax.yaxis.label.set_color("#b3bac7")
        for spine in ax.spines.values(): spine.set_color("#343943")
    seen = set()
    for index, view in enumerate(views):
        rows, record = view["rows"], view["record"]
        stride = max(1,len(rows)//8000)
        sample = rows[::stride]
        values = [r["reference"]-r["output"] if channel == "error" and r["output"] is not None else r.get(channel) for r in sample]
        name = view["label"]+(" [FAILED]" if record["metrics"]["status"] != "completed" else "")
        ax.plot([r["time_s"] for r in sample],values,label=name,color=COLORS[index%8],lw=1.8)
        if channel == "output":
            x, y = saved_reference(record)
            signature = digest_json([x,y])
            if signature not in seen:
                seen.add(signature)
                stride = max(1,len(x)//8000)
                ax.step(x[::stride],y[::stride],where="post",ls="--",lw=1,color="#929ba8",label="Reference" if len(seen) == 1 else "Reference: "+view["label"])
    units = views[0]["record"]["units"]
    ax.set_xlim(0,max(v["record"]["scenario"]["duration_s"] for v in views))
    ax.set_xlabel("Time / s")
    ax.set_ylabel(("Applied input / "+units["input"]) if channel == "applied_input" else ("Error / " if channel == "error" else "Output / ")+units["output"])
    ax.grid(alpha=.15)
    ax.legend(loc="best",fontsize=9,facecolor="#1c1e22" if dark else "white",labelcolor="#e9edf5" if dark else "black")
    return ax


def build(output, records):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .experiment import read_trace
    views = [dict(rows=read_trace(output,r),record=r,label=r["comparison_label"]) for r in records]
    (output/"figures").mkdir()
    for key in ("output", "error", "applied_input"):
        fig = plt.figure(figsize=(12,5),layout="constrained")
        draw(fig,views,key)
        fig.suptitle("ControlStressLab | Saved experiment comparison")
        fig.text(.01,.01,"Original saved metrics; common physical axes; inspect configuration differences. Synthetic simulations only.",fontsize=8)
        fig.get_layout_engine().set(rect=(0,.05,1,.95))
        fig.savefig(output/"figures"/(key+".png"),dpi=160)
        fig.savefig(output/"figures"/(key+".svg"),metadata={"Date":None})
        plt.close(fig)
