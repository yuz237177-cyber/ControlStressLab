"""White-background shareable figures generated in the worker, never in Qt."""


def build(output, records):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .experiment import read_trace, saved_reference

    dest = output / "figures"
    dest.mkdir()
    colors = {"PI": "#2878ff", "PID_aw": "#009b88", "TwoDOF_PID": "#d18b36", "LADRC": "#8a62c9"}
    for channel, title in (("output", "Output and reference"), ("error", "Tracking error"), ("applied_input", "Applied control actions")):
        fig, ax = plt.subplots(figsize=(12, 5), layout="constrained")
        for record in records:
            rows = read_trace(output, record)
            x = [r["time_s"] for r in rows]
            y = [r["reference"]-r["output"] if channel == "error" and r["output"] is not None else r.get(channel) for r in rows]
            ax.plot(x, y, color=colors[record["controller_name"]], label=record["controller_name"], lw=1.5)
        if channel == "output":
            reference_x, reference_y = saved_reference(records[0])
            ax.step(reference_x, reference_y, where="post", color="0.4", ls="--", label="Reference")
        ax.set_xlim(0, records[0]["scenario"]["duration_s"])
        units = records[0]["units"]
        ax.set(title=title, xlabel="Time / s", ylabel=("Input / "+units["input"]) if channel == "applied_input" else ("Error / " if channel == "error" else "Output / ")+units["output"])
        ax.grid(alpha=0.2)
        ax.legend()
        fig.suptitle("ControlStressLab | Paired controller comparison", fontsize=15)
        fig.text(0.015, 0.01, "Synthetic models; identical inputs, noise and limits. No hardware validation or universal ranking.", fontsize=9)
        fig.get_layout_engine().set(rect=(0, 0.06, 1, 0.91))
        fig.savefig(dest / (channel+".png"), dpi=160)
        fig.savefig(dest / (channel+".svg"), metadata={"Date": None})
        plt.close(fig)
