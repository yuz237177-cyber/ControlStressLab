"""Physical-output metrics; missing/full-run failure metrics are never scored as zero."""

import math

from .simulation import Run


def evaluate(run: Run) -> dict:
    s = run.scenario
    metrics = {"status": run.status, "reason": run.reason,
               "observed_until_s": max((r["time_s"] for r in run.rows if r.get("true_output_rad_s") is not None), default=0.0),
               "termination_time_s": run.termination_time_s,
               "last_integrated_time_s": run.last_integrated_time_s,
               "metric_source": "model_state",
               "rmse_rad_s": None, "iae_rad": None, "max_abs_error_rad_s": None,
               "input_total_variation_V": None, "saturation_fraction": None,
               "recovery_time_s": None, "recovery_status": "run_incomplete",
               "iae_pre_event_rad": None, "iae_post_event_rad": None,
               "rmse_pre_event_rad_s": None, "rmse_post_event_rad_s": None,
               "pre_event_duration_s": None, "post_event_duration_s": None}
    # An early termination must not look superior merely because less time was integrated.
    if run.status != "completed":
        return metrics
    rows = [row for row in run.rows if row["time_s"] >= s.evaluation_start_s - 1e-12 and row["interval_s"] > 0]
    duration = sum(row["interval_s"] for row in rows)
    errors = [row["reference_rad_s"] - row["true_output_rad_s"] for row in rows]
    calculated = dict(
        rmse_rad_s=math.sqrt(sum(e * e * row["interval_s"] for e, row in zip(errors, rows)) / duration),
        iae_rad=sum(abs(e) * row["interval_s"] for e, row in zip(errors, rows)),
        max_abs_error_rad_s=max(abs(e) for e in errors),
        input_total_variation_V=sum(abs(b["applied_V"] - a["applied_V"]) for a, b in zip(rows, rows[1:])),
        saturation_fraction=sum(row["interval_s"] for row in rows if abs(row["command_V"] - row["applied_V"]) > 1e-10) / duration,
    )
    anchor = s.recovery_start_s
    for label, subset in (("pre", [r for r in rows if r["time_s"] < anchor - 1e-12]),
                          ("post", [r for r in rows if r["time_s"] >= anchor - 1e-12])):
        span = sum(r["interval_s"] for r in subset)
        calculated[f"{label}_event_duration_s"] = span
        if span:
            differences = [r["reference_rad_s"] - r["true_output_rad_s"] for r in subset]
            calculated[f"iae_{label}_event_rad"] = sum(abs(e) * r["interval_s"] for e, r in zip(differences, subset))
            calculated[f"rmse_{label}_event_rad_s"] = math.sqrt(sum(e * e * r["interval_s"] for e, r in zip(differences, subset)) / span)
    if any(isinstance(v, float) and not math.isfinite(v) for v in calculated.values()):
        metrics.update(status="metric_failure", reason="nonfinite metric; check signal scale and window", recovery_status="metrics_invalid")
        return metrics
    metrics.update(calculated)
    post = [row for row in run.rows if row["time_s"] >= s.recovery_start_s - 1e-12]
    # Settling-style recovery: final uninterrupted in-band segment must cover dwell.
    last_outside = -1
    for i, row in enumerate(post):
        if abs(row["reference_rad_s"] - row["true_output_rad_s"]) > s.recovery_band:
            last_outside = i
    start = last_outside + 1
    if start < len(post) and post[-1]["time_s"] - post[start]["time_s"] >= s.recovery_dwell_s - 1e-12:
        metrics["recovery_time_s"] = max(0.0, post[start]["time_s"] - s.recovery_start_s)
        metrics["recovery_status"] = "recovered_in_observation_window"
    else:
        metrics["recovery_status"] = "not_recovered_in_observation_window"
    return metrics
