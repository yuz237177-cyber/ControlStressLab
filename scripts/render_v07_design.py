"""Render the v0.7 layout proposal. Curves are illustrative, never evidence.

Requires Pillow (also available with the existing charts dependencies).
Writes only the PNG/SVG design assets; it does not run product analysis.
"""

from pathlib import Path
import math
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "design"
W, H, SCALE = 1920, 1200, 2
BG, PANEL, BOX, EDGE = "#0b0c0e", "#121315", "#1c1e22", "#2b2e34"
FG, MUTED = "#f2f3f5", "#b3bac7"
BLUE, CYAN, PURPLE, AMBER = "#2878ff", "#49cfbc", "#b49aff", "#e7bd74"
image = Image.new("RGB", (W * SCALE, H * SCALE), BG)
draw = ImageDraw.Draw(image)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
       '<title>ControlStressLab v0.7 frequency workbench — design proposal</title>',
       '<desc>Not an application screenshot. All curves are layout illustrations; no calculated metrics are shown.</desc>']
fonts = {}


def text(x, y, value, size=17, color=FG):
    if size not in fonts:
        fonts[size] = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", size * SCALE)
    draw.text((round(x * SCALE), round(y * SCALE)), value, fill=color,
              font=fonts[size], anchor="lt")
    svg.append(f'<text x="{x}" y="{y}" dominant-baseline="text-before-edge" '
               f'font-family="Microsoft YaHei, sans-serif" font-size="{size}" '
               f'font-weight="700" fill="{color}">{escape(value)}</text>')


def rect(x, y, w, h, fill=PANEL, stroke=None, r=12):
    draw.rounded_rectangle(tuple(round(v * SCALE) for v in (x, y, x + w, y + h)),
                           radius=r * SCALE, fill=fill, outline=stroke, width=SCALE)
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" '
               f'fill="{fill}" stroke="{stroke or "none"}"/>')


def line(points, color=EDGE, width=1, dashed=False):
    scaled = [(round(x * SCALE), round(y * SCALE)) for x, y in points]
    if dashed:
        # Keep dash lengths consistent across segments in the raster copy.
        travelled = 0.0
        for a, b in zip(points, points[1:]):
            length = math.dist(a, b)
            for step in range(max(1, math.ceil(length))):
                if int((travelled + step) / 7) % 2 == 0:
                    t0, t1 = step / max(length, 1), min(step + 1, length) / max(length, 1)
                    draw.line([(round((a[0] + (b[0] - a[0]) * t) * SCALE),
                                round((a[1] + (b[1] - a[1]) * t) * SCALE))
                               for t in (t0, t1)], fill=color, width=round(width * SCALE))
            travelled += length
    else:
        draw.line(scaled, fill=color, width=round(width * SCALE), joint="curve")
    svg.append('<polyline points="' + ' '.join(f'{x:.3f},{y:.3f}' for x, y in points)
               + f'" fill="none" stroke="{color}" stroke-width="{width}" '
               'stroke-linejoin="round"' + (' stroke-dasharray="7 7"' if dashed else '') + '/>')


def button(x, y, w, label, selected=False, primary=False, disabled=False, h=44):
    rect(x, y, w, h, BLUE if primary else ("#141f32" if selected else BOX),
         "#305b9e" if selected else (None if primary else EDGE), 8)
    text(x + 15, y + 12, label, 16,
         "#737b88" if disabled else (BLUE if selected else FG))


def legend(x, y, label, color, dashed=False):
    line([(x, y + 8), (x + 25, y + 8)], color, 3, dashed)
    text(x + 36, y, label, 15, MUTED)


def field(x, y, w, label, value):
    text(x, y, label, 15, MUTED)
    rect(x, y + 28, w, 42, BOX, EDGE, 7)
    text(x + 12, y + 41, value, 16)


def metric(y, title, unit, detail):
    text(1590, y, title, 18)
    text(1590, y + 37, "—", 31)
    text(1640, y + 48, unit, 15, MUTED)
    text(1590, y + 86, detail, 14, MUTED)


rect(0, 0, W, H, BG, EDGE, 12)
text(30, 26, "ControlStressLab", 25)
text(291, 31, "v0.7 · 设计方案", 17, MUTED)
text(1438, 31, "布局预览 / 非运行截图", 17, AMBER)
text(1785, 27, "─    □    ×", 22, MUTED)

# Persistent left rail.
text(28, 108, "控制实验工作台", 25)
text(29, 149, "配置与已保存实验", 15, MUTED)
button(27, 194, 224, "+  新建实验配置")
button(27, 249, 106, "导入")
button(143, 249, 108, "打开结果")
text(29, 330, "当前分析来源", 16, MUTED)
rect(27, 367, 224, 101, "#111b2b", "#305b9e", 10)
rect(27, 383, 4, 65, BLUE, r=2)
text(44, 385, "一阶 · 延迟工况", 18, BLUE)
text(44, 419, "从扫描工况建立快照", 14, MUTED)
text(29, 502, "配置快照", 16)
for row, (label, value) in enumerate([
        ("对象", "一阶模型"), ("控制器", "已选 3 项"),
        ("采样周期", "0.01 s"), ("测量延迟", "0.07 s"),
        ("分析范围", "标称 / 未饱和")]):
    yy = 548 + row * 53
    text(29, yy, label, 14, MUTED)
    text(29, yy + 23, value, 17)
line([(28, 839), (249, 839)])
text(29, 865, "来源与结果分别保存", 16)
text(29, 899, "修改草稿后须重新计算", 14, MUTED)
text(29, 925, "旧扫描数据保持原样", 14, MUTED)
button(27, 1086, 224, "查看模型与计算说明")

# Main navigation and scope banner.
rect(277, 78, 1615, 1070, PANEL)
navs = [(304, 133, "实验对比"), (448, 133, "预算整定"),
        (592, 133, "历史实验"), (736, 133, "参数扫描"),
        (880, 133, "实验对照"), (1024, 144, "频域分析")]
for x, width, label in navs:
    button(x, 96, width, label, selected=label == "频域分析")
text(1196, 110, "模型、数据与图表一起保存", 16, MUTED)
rect(300, 159, 1568, 69, "#1d1a14", "#55462c", 9)
text(319, 174, "标称线性分析 · 仅适用于未饱和分支", 17, AMBER)
text(319, 201, "设计稿：以下曲线仅作排版示意，裕度、极点与稳定性均尚未计算。", 14, MUTED)

# Large plot pane. The side panel holds context rather than duplicating charts.
rect(300, 246, 1242, 726, "#101113", EDGE)
for x, width, label in [(316, 155, "环路 Bode"), (481, 149, "闭环极点"),
                         (640, 135, "灵敏度"), (785, 175, "参考与扰动")]:
    button(x, 260, width, label, selected=label == "环路 Bode", h=42)
legend(331, 327, "PI", BLUE)
legend(471, 327, "PID_aw", CYAN)
legend(679, 327, "TwoDOF_PID · 与PID反馈环路重合", PURPLE, True)

px, pw = 395, 1095
for top, bottom, label, ticks in [
        (391, 607, "幅值 / dB", ["40", "20", "0", "−20"]),
        (660, 876, "相位 / °", ["0", "−90", "−180", "−270"])]:
    text(321, top - 22, label, 16, MUTED)
    for i, tick in enumerate(ticks):
        yy = top + i * (bottom - top) / 3
        line([(px, yy), (px + pw, yy)], EDGE)
        text(341, yy - 6, tick, 13, MUTED)
    for j in range(5):
        xx = px + j * pw / 4
        line([(xx, top), (xx, bottom)], "#22252b")
    line([(px, top), (px, bottom), (px + pw, bottom)], "#535b67", 1)

# Deliberately aesthetic, non-computed placeholders, prominently labelled.
for top, variant in [(391, "magnitude"), (660, "phase")]:
    for color, offset in [(BLUE, 0), (CYAN, 1)]:
        points = []
        for index in range(280):
            t = index / 279
            if variant == "magnitude":
                value = 25 + 38 * t + (143 if not offset else 111) / (1 + math.exp(-9 * (t - .56)))
            else:
                value = 20 + 164 * t ** 1.35 + 23 * math.sin(t * math.pi) - offset * 27 * math.sin(t * math.pi)
            points.append((px + pw * t, top + value))
        line(points, color, 3)
        if offset:
            line(points, PURPLE, 2, True)
    text(1165, top + 22, "示意曲线 · 非计算数据", 16, "#687382")
for j, label in enumerate(["0.01", "0.1", "1", "10", "100"]):
    text(px + j * pw / 4 - 15, 890, label, 14, MUTED)
text(1293, 928, "角频率 ω / rad/s", 16, MUTED)
text(331, 929, "悬停读取幅相  ·  点击交越标记查看明细", 14, MUTED)

# Metric cards: no invented results.
rect(1560, 246, 308, 726, "#151619", EDGE)
text(1590, 269, "当前控制器：PID_aw", 18)
line([(1589, 309), (1840, 309)])
text(1590, 332, "标称内部稳定性", 17)
text(1590, 370, "尚未计算", 25, MUTED)
text(1590, 411, "依据全部内部闭环极点", 14, MUTED)
line([(1589, 449), (1840, 449)])
metric(473, "相位裕度 PM", "°", "对应增益交越频率：— rad/s")
metric(606, "增益裕度 GM", "dB", "对应相位交越频率：— rad/s")
button(1588, 747, 253, "查看全部交越与数值状态", disabled=True)
line([(1589, 814), (1840, 814)])
text(1590, 837, "没有交越 ≠ 无限安全", 16, AMBER)
text(1590, 871, "未覆盖饱和与真实硬件", 14, MUTED)
text(1590, 902, "频响结论附带搜索频段", 14, MUTED)

# Compact settings below the charts.
text(316, 991, "频率范围", 16)
field(316, 1022, 188, "起始角频率 / rad/s", "0.01")
field(519, 1022, 188, "结束角频率 / rad/s", "100")
field(722, 1022, 148, "基础采样点", "1024")
line([(899, 992), (899, 1104)])
text(922, 991, "时域一致性", 16)
text(922, 1026, "独立的小信号验证案例", 15, MUTED)
button(922, 1060, 239, "核对响应与实际输入", disabled=True)
line([(1187, 992), (1187, 1104)])
text(1211, 991, "结果保存", 16)
text(1211, 1026, "原始频响 / 极点 / 图表 / 来源", 15, MUTED)
button(1211, 1060, 239, "保存完整分析", disabled=True)
button(1560, 1045, 308, "校验配置并开始分析", primary=True, h=52)

text(29, 1167, "设计阶段 · 尚未接入计算模块", 15, AMBER)
text(770, 1167, "界面沿用深色、粗体与大图区域；数值需独立参考验收。", 15, MUTED)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    image.resize((W, H), Image.Resampling.LANCZOS).save(OUT / "v0.7-frequency-workbench.png")
    (OUT / "v0.7-frequency-workbench.svg").write_text('\n'.join(svg + ['</svg>']), encoding="utf-8")
    print("Saved v0.7 design proposal PNG and SVG (illustrative only).")
