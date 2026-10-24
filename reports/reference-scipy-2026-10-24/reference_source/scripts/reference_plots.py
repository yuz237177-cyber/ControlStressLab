"""Optional Matplotlib figures from the saved product and oracle trajectories."""

def build(output, inputs, products, references, comparisons):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    destination = output / "figures"
    destination.mkdir()
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})

    def save(fig, name, note):
        fig.suptitle(name.replace("_", " ").title(), fontsize=17)
        fig.text(0.02, 0.015, note + "\nSynthetic models; numerical agreement is not hardware validation.", fontsize=9)
        # Constrained-layout rect is (left, bottom, width, height), not corners.
        fig.get_layout_engine().set(rect=(0, 0.085, 1, 0.855))
        fig.savefig(destination / (name + ".png"), dpi=160)
        svg = destination / (name + ".svg")
        fig.savefig(svg, metadata={"Date": None})
        svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf8").splitlines()) + "\n", encoding="utf8", newline="\n")
        plt.close(fig)

    fig, axes = plt.subplots(3, 1, figsize=(13, 11), layout="constrained")
    for ax, path in zip(axes, ("open_loop", "linear_pi", "ode_closed_loop")):
        selected = [c for c in comparisons if c["path"] == path]
        errors = [c["channels"]["output"]["max_abs_error"] for c in selected]
        ax.bar(range(len(selected)), [np.nan if e is None else max(e, 1e-16) for e in errors],
               color=["#247f91" if c["passed"] else "#b94b30" for c in selected])
        ax.axhline(1e-8, color="#b94b30", ls="--", label="Absolute tolerance floor (relative term additional)")
        ax.set(yscale="log", ylabel="Max |output difference|", title=path, xticks=range(len(selected)),
               xticklabels=[c["id"] for c in selected])
        ax.tick_params(axis="x", labelrotation=65, labelsize=7)
        ax.grid(axis="y", alpha=0.2)
        ax.legend(fontsize=8)
    save(fig, "maximum_output_errors", "Zero differences, if any, are displayed at 1e-16. Every sample is checked separately.")

    names = ["closed_saturation_release_aw0", "closed_saturation_release_aw1",
             "stress_0.15_0.35_aw0", "stress_0.6_0_aw1"]
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), layout="constrained")
    for ax, name in zip(axes.flat, names):
        c = next(c for c in inputs["cases"] if c["id"] == name)
        p, r = products[name]["channels"], references[name]
        ax.plot(p["time"], p["output"], lw=2.4, label="ControlStressLab")
        ax.plot(r["time"][::12], r["output"][::12], ".", ms=3, color="#d06b28", label="SciPy DOP853 (markers thinned)")
        ref = np.zeros(c["intervals"]+1)
        for t, value in c["reference"]:
            ref[round(t/c["dt_s"]):] = value
        ax.step(p["time"], ref, where="post", color="0.4", ls="--", lw=1, label="Reference")
        ax.set(title=name, xlabel="Time / s", ylabel="Speed / rad s$^{-1}$")
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    save(fig, "representative_response_overlays", "Includes saturation release, a non-recovered delay point and an unreachable exact reference.")

    names = ["open_DCMotor_0.01_2", "linear_DCMotor_0.02", "closed_noise_aw1", "derivative_filter0.03_aw1"]
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), layout="constrained")
    for ax, name in zip(axes.flat, names):
        p, r = products[name]["channels"], references[name]
        ax.plot(p["time"], np.array(p["output"])-np.array(r["output"]), lw=1, label="Output difference")
        ax.set(title=name, xlabel="Time / s", ylabel="Product - SciPy")
        ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))
        ax.grid(alpha=0.2)
    save(fig, "signed_numerical_differences", "Signed error is shown directly; overlapping response curves alone do not establish agreement.")

    selected = [c for c in comparisons if "iae_abs_error" in c["metrics"]]
    fig, axes = plt.subplots(2, 1, figsize=(13, 8), layout="constrained")
    for ax, field, label in zip(axes, ("max_tolerance_fraction", "iae_abs_error"),
                                ("Worst pointwise error / allowed error", "IAE absolute difference / rad")):
        values = ([max(c["channels"][k][field] for k in c["channels"]) for c in selected]
                  if field == "max_tolerance_fraction" else [c["metrics"][field] for c in selected])
        ax.bar(range(len(selected)), [max(v, 1e-16) for v in values], color="#5566a2")
        ax.axhline(1 if field == "max_tolerance_fraction" else 1e-6, color="#b94b30", ls="--")
        ax.set(yscale="log", ylabel=label, xticks=range(len(selected)), xticklabels=[c["id"] for c in selected])
        ax.tick_params(axis="x", labelrotation=65, labelsize=7)
        ax.grid(axis="y", alpha=0.2)
    save(fig, "closed_loop_acceptance", "Top: all ratios must be <= 1. Bottom: IAE absolute floor. Zeros shown at 1e-16; invalid metrics omitted (see report).")
