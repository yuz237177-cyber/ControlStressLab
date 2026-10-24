"""Offline report preview with explicit state, measurement and action channels."""

import html
import math


def plot(rows: list[dict], channels: list[tuple[str, str, str]], unit: str,
         title: str, *, actions_only: bool = False, event_s: float | None = None) -> str:
    series = []
    for key, color, label in channels:
        points = [(row["time_s"], row.get(key)) for row in rows
                  if not actions_only or row.get("action_taken", row.get("interval_s", 0) > 0)]
        points = [(t, y) for t, y in points if isinstance(y, (int, float)) and math.isfinite(y)]
        if points:
            series.append((points, color, label))
    if not series:
        return f"<p>{html.escape(title)}：没有有效数据。</p>"
    width, height, left, right, top, bottom = 780, 230, 62, 16, 25, 38
    values = [y for points, _, _ in series for _, y in points]
    lo, hi = min(0.0, min(values)), max(0.0, max(values))
    span = hi - lo
    if not math.isfinite(span):
        return f"<p>{html.escape(title)}：数值量级超出预览范围，请检查 CSV 与失败状态。</p>"
    if span < 1e-9:
        span, hi = 1.0, lo + 1.0
    end = max(rows[-1]["time_s"], 1e-9)
    x = lambda t: left + t / end * (width - left - right)
    y = lambda v: top + (1 - (v - lo) / span) * (height - top - bottom)
    elements = [f'<svg role="img" aria-label="{html.escape(title)}" viewBox="0 0 {width} {height}">',
                '<rect width="100%" height="100%" fill="#f8fafc"/>']
    for fraction in (0.0, 0.5, 1.0):
        value = lo + span * fraction
        elements.append(f'<line x1="{left}" x2="{width-right}" y1="{y(value):.2f}" y2="{y(value):.2f}" stroke="#dce4ed"/>')
        elements.append(f'<text x="{left-7}" y="{y(value)+4:.2f}" text-anchor="end">{value:.3g}</text>')
        t = end * fraction
        elements.append(f'<text x="{x(t):.2f}" y="{height-17}" text-anchor="middle">{t:.3g}</text>')
    if event_s is not None and 0 <= event_s <= end:
        elements.append(f'<line x1="{x(event_s):.2f}" x2="{x(event_s):.2f}" y1="{top}" y2="{height-bottom}" stroke="#b45309" stroke-dasharray="5 4"/>')
    for points, color, label in series:
        coordinates = " ".join(f"{x(t):.2f},{y(value):.2f}" for t, value in points)
        elements.append(f'<polyline fill="none" stroke="{color}" stroke-width="1.5" points="{coordinates}"><title>{html.escape(label)}</title></polyline>')
    elements.append(f'<text x="8" y="15">{html.escape(unit)}</text><text x="{width-20}" y="{height-4}" text-anchor="end">时间 / s</text></svg>')
    legend = " · ".join(f'<span style="color:{color}">{html.escape(label)}</span>' for _, color, label in series)
    return f'<h3>{html.escape(title)}</h3>{"".join(elements)}<p class="note">{legend} · 棕色虚线：评价事件锚点。完整数据见 CSV。</p>'


def charts(rows: list[dict], event_s: float) -> str:
    return (plot(rows, [("reference_rad_s", "#64748b", "参考"), ("true_output_rad_s", "#2563eb", "真实状态")],
                 "rad/s", "参考与真实输出", event_s=event_s)
            + plot(rows, [("true_output_rad_s", "#2563eb", "真实状态"), ("measurement_rad_s", "#d97706", "控制器可见测量")],
                   "rad/s", "测量与反馈", event_s=event_s)
            + plot(rows, [("command_V", "#94a3b8", "请求输入"), ("applied_V", "#0f766e", "实际输入")],
                   "V", "控制动作（仅实际发出的动作）", actions_only=True, event_s=event_s))
