"""Original SVG GUI proposal inspired by referenced graphic design.

Uses saved v0.8 search metrics; does not modify the app or run simulations.
External artworks are not embedded. Requires the existing optional GUI dependencies.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
from xml.sax.saxutils import escape

ROOT=Path(__file__).resolve().parents[1]
BG,PANEL,EDGE,INK,MUTED="#101416","#181D20","#343D41","#EEF0E8","#AAB5B7"
YELLOW,CYAN,PURPLE="#E4F13B","#66D9DC","#AD8CF2"
W,H=1920,1200


def render(folder,output):
    summary=json.loads((folder/"summary.json").read_text(encoding="utf-8"))
    plan=json.loads((folder/"plan.json").read_text(encoding="utf-8"))
    if summary["feasible_count"]<1:raise ValueError("本视觉稿需要包含可行候选的已保存搜索")
    selected=next(c for c in summary["candidates"] if c["candidate_id"]==summary["low_error_id"])
    base=next(c for c in summary["candidates"] if c["candidate_id"]==0)
    smooth=summary["smooth_action_id"]
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
         '<title>ControlStressLab v0.9 original visual proposal</title>',
         '<desc>Design proposal, not an implemented application screenshot. Scatter points and metrics come from a saved v0.8 search. No third-party artwork is embedded.</desc>']

    def rect(x,y,w,h,fill=PANEL,stroke=None):
        svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke or "none"}"/>')
    def line(x,y,x2,y2,color=EDGE,width=1):
        svg.append(f'<path d="M{x},{y} L{x2},{y2}" stroke="{color}" stroke-width="{width}" fill="none"/>')
    def text(x,y,label,size=18,color=INK,font="Microsoft YaHei",weight=700):
        svg.append(f'<text x="{x}" y="{y+size*.92}" font-family="{font}" font-size="{size}" font-weight="{weight}" fill="{color}">{escape(str(label))}</text>')
    def poly(points,fill,stroke=None,width=1):
        svg.append('<polygon points="'+' '.join(f'{x:.3f},{y:.3f}' for x,y in points)+f'" fill="{fill}" stroke="{stroke or "none"}" stroke-width="{width}"/>')
    def circle(x,y,r,fill,stroke=None,width=1):
        svg.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke or "none"}" stroke-width="{width}"/>')
    def cut(x,y,w,h,fill,stroke=None,c=9):
        poly([(x,y),(x+w-c,y),(x+w,y+c),(x+w,y+h),(x+c,y+h),(x,y+h-c)],fill,stroke)
    def star(x,y,color):
        points=[]
        for i in range(10):
            a=-math.pi/2+i*math.pi/5;r=8 if i%2==0 else 3.5
            points.append((x+r*math.cos(a),y+r*math.sin(a)))
        poly(points,color)
    def button(x,y,w,label,primary=False):
        cut(x,y,w,46,YELLOW if primary else "#222A2D",None if primary else EDGE)
        text(x+17,y+12,label,17,BG if primary else INK)
    def meta(x,y,title,value,width=250):
        text(x,y,title,14,MUTED);text(x,y+30,value,19);line(x,y+63,x+width,y+63)

    rect(0,0,W,H,BG)
    rect(0,0,262,H,"#0C1012")
    line(262,0,262,H)
    # An original small lattice mark, separate from any game logo.
    for row,col in ((0,0),(0,1),(1,1),(1,2),(2,0),(2,2)):
        x,y=30+col*13,29+row*13
        poly([(x,y),(x+10,y),(x,y+10)],YELLOW if (row+col)%2 else INK)
    text(89,27,"CS / LAB",25,font="Bahnschrift")
    text(29,98,"CONTROL",31,font="Bahnschrift")
    text(29,136,"STRESS LAB.",31,font="Bahnschrift")
    text(30,186,"控制器压力测试工作台",15,MUTED)
    rect(30,224,40,3,YELLOW);line(80,225,230,225)
    text(30,253,"实验档案",18)
    text(30,284,"EXPERIMENT ARCHIVE",11,MUTED,font="Bahnschrift")
    cut(20,321,222,103,"#242B2C",EDGE)
    rect(20,321,5,103,YELLOW)
    text(37,338,"01",28,YELLOW,font="Bahnschrift")
    text(83,340,"一阶惯性",19)
    text(37,383,"抗饱和 PID · 已保存搜索",14,MUTED)
    cut(20,440,222,87,"#151B1D",EDGE)
    text(37,455,"02",25,MUTED,font="Bahnschrift")
    text(83,457,"二阶振荡",18)
    text(37,492,"双自由度 PID · 实验档案",13,MUTED)
    button(20,551,222,"＋ 新建实验")
    button(20,607,104,"导入")
    button(136,607,106,"打开")
    meta(30,725,"当前对象","一阶惯性",202)
    meta(30,815,"记录范围",f"{len(plan['candidates'])} 候选 / {len(plan['search'])} 条件",202)
    text(30,1028,"FINITE CONDITIONS",12,MUTED,font="Bahnschrift")
    text(30,1055,"有限工况 · 合成模型",15)
    text(30,1125,"v0.9 / VISUAL PROPOSAL",12,YELLOW,font="Bahnschrift")

    # Top navigation uses a compact rail and a clipped active underline.
    for i,label in enumerate(("实验对比","预算整定","历史实验","参数扫描","实验对照")):
        x=298+i*149
        text(x,35,label,19,YELLOW if i==1 else MUTED)
        if i==1:rect(x,77,100,4,YELLOW)
    text(1398,35,"视觉提案 / 真实 v0.8 数据",15,MUTED)
    line(292,83,1890,83)
    text(299,104,"WORKSPACE / 02",14,YELLOW,font="Bahnschrift")
    text(296,133,"约束多目标整定",43)
    text(300,195,"CONSTRAINED TUNING",19,MUTED,font="Bahnschrift")
    text(985,146,"从性能取舍，到可复查的参数选择。",18,MUTED)
    text(1642,107,"03",89,"#354045",font="Bahnschrift")
    text(1787,169,"/ 04",25,MUTED,font="Bahnschrift")
    # Keep ornament outside plot and form reading regions.
    for row in range(4):
        for col in range(11):
            circle(1430+col*10,120+row*10,1.1,"#303A3D")
    steps=[("01","设置要求","完成"),("02","搜索候选","完成"),("03","选择与冻结","当前"),("04","验证与报告","待开始")]
    for i,(num,title,state) in enumerate(steps):
        x=298+i*399
        rect(x,246,386,55,"#252D2E" if i==2 else "#191F22",EDGE)
        if i==2:rect(x,246,4,55,YELLOW)
        text(x+16,259,num,21,YELLOW if i==2 else MUTED,font="Bahnschrift")
        text(x+63,261,title,18)
        text(x+286,265,state,13,YELLOW if i==2 else MUTED)

    # Actual scatter data, with only the frontier and baseline annotated.
    px,py,pw,ph=298,322,1194,608
    rect(px,py,pw,ph,PANEL,EDGE)
    rect(px,py,5,56,CYAN)
    text(px+22,py+18,"候选取舍",25)
    text(px+188,py+26,f"{len(plan['candidates'])} 个候选 · {len(plan['search'])} 组声明条件",14,MUTED)
    text(px+855,py+25,"搜索已完成 / 要求已检查",14,CYAN)
    for i,label in enumerate(("候选取舍","响应对照","实际输入","要求明细")):
        x=px+22+i*138
        text(x,py+76,label,16,INK if i==0 else MUTED)
        if i==0:rect(x,py+105,92,3,CYAN)
    text(px+768,py+77,"★ 非支配候选   ◇ 基线   ● 其他候选",13,MUTED)
    left,top,plotw,ploth=390,477,1040,333
    feasible=[c for c in summary["candidates"] if c["feasible"]]
    xmin,xmax=0.05,.30;ymin,ymax=0.,7.
    # Expand automatically for another valid saved dataset.
    xmin=min(xmin,min(c["J1"] for c in feasible)*.9);xmax=max(xmax,max(c["J1"] for c in feasible)*1.05)
    ymax=max(ymax,max(c["J2"] for c in feasible)*1.03)
    raw_step=ymax/8;power=10**math.floor(math.log10(raw_step))
    step=next(m*power for m in (1,2,5,10) if m*power>=raw_step)
    ymax=math.ceil(ymax/step)*step
    def position(c):return left+(c["J1"]-xmin)/(xmax-xmin)*plotw,top+ploth-(c["J2"]-ymin)/(ymax-ymin)*ploth
    for i in range(6):
        x=left+i*plotw/5
        line(x,top,x,top+ploth,"#2B3539")
        text(x-17,top+ploth+15,f"{xmin+i*(xmax-xmin)/5:.2f}",13,MUTED,font="Consolas")
    for i in range(round(ymax/step)+1):
        y=top+ploth-i*step*ploth/ymax
        line(left,y,left+plotw,y,"#2B3539")
        text(left-30,y-7,f"{i*step:g}",13,MUTED,font="Consolas")
    line(left,top,left,top+ploth,"#68777C")
    line(left,top+ploth,left+plotw,top+ploth,"#68777C")
    text(left-49,top-34,"动作目标 J2 / (1/s)",14,MUTED)
    text(left+plotw-237,top+ploth+48,"误差目标 J1 / 归一化 RMSE",14,MUTED)
    front=set(summary["frontier_ids"])
    for c in feasible:
        x,y=position(c)
        if c["candidate_id"]==0:
            poly([(x,y-6),(x+6,y),(x,y+6),(x-6,y)],PANEL,"#D3DAD6",2)
            text(x+10,y-18,"基线 0",13,MUTED)
        elif c["candidate_id"] in front:
            color=PURPLE if c["candidate_id"]==smooth else CYAN
            star(x,y,color)
            if c["candidate_id"]!=selected["candidate_id"]:text(x+9,y-18,str(c["candidate_id"]),13,color,font="Consolas")
        else:circle(x,y,4.5,"#7C898E")
    sx,sy=position(selected)
    circle(sx,sy,15,"none",YELLOW,2)
    line(sx+15,sy-10,sx+55,sy-42,YELLOW)
    cut(sx+55,sy-76,157,55,"#263235",EDGE)
    text(sx+67,sy-66,"当前查看",12,MUTED)
    text(sx+67,sy-46,f"候选 {selected['candidate_id']:02}",19,YELLOW)
    text(px+23,py+564,"点击候选查看参数与轨迹；悬停读取完整数值。",14,MUTED)

    # Right-side context: inspection and frozen choice are separate states.
    rx=1512;rw=378
    rect(rx,322,rw,608,PANEL,EDGE)
    cut(rx+18,340,rw-36,104,INK)
    text(rx+36,353,"当前查看 / INSPECTING",12,BG,font="Bahnschrift")
    text(rx+34,373,f"{selected['candidate_id']:02}",57,BG,font="Bahnschrift")
    text(rx+157,376,"搜索要求",14,"#46514C")
    text(rx+157,404,"满足",24,BG)
    text(rx+22,467,"控制器参数",18)
    text(rx+245,471,"PID_aw",14,MUTED,font="Consolas")
    for i,(key,label) in enumerate((("kp","比例 kp"),("ki","积分 ki"),("kd","微分 kd"))):
        y=509+i*45
        text(rx+22,y,label,15,MUTED)
        text(rx+203,y-3,f"{selected['parameters'][key]:.6g}",21,font="Consolas")
    line(rx+22,654,rx+rw-22,654)
    text(rx+22,676,"误差目标 J1",14,MUTED)
    text(rx+22,704,f"{selected['J1']:.5g}",31,font="Consolas")
    echange=(selected["J1"]-base["J1"])/base["J1"]*100
    text(rx+210,715,f"较基线 {echange:+.1f}%",13,CYAN)
    text(rx+22,765,"动作目标 J2",14,MUTED)
    text(rx+22,792,f"{selected['J2']:.5g}",31,font="Consolas")
    vchange=(selected["J2"]-base["J2"])/base["J2"]*100
    text(rx+210,805,f"较基线 {vchange:+.1f}%",13,YELLOW)
    line(rx+22,855,rx+rw-22,855)
    text(rx+22,875,"主选状态：尚未冻结",16,YELLOW)
    text(rx+22,905,"更低误差伴随更多控制动作。",13,MUTED)

    rect(298,950,1194,142,PANEL,EDGE)
    text(320,969,"要求与测试计划",20)
    text(1304,975,"展开编辑  ＋",14,MUTED)
    limits=plan['config']['thresholds']
    shown=[('误差上限','未启用' if limits['error_max'] is None else f"{limits['error_max']:g}"),
           ('饱和比例上限','未启用' if limits['saturation_max'] is None else f"{100*limits['saturation_max']:g}%"),
           ('动作变化率上限','未启用' if limits['variation_max'] is None else f"{limits['variation_max']:g} /s")]
    for i,(label,value) in enumerate(shown):
        x=320+i*389
        text(x,1018,label,14,MUTED)
        text(x+203,1016,value,19)
        if i<2:line(x+361,1012,x+361,1060)
    text(320,1065,"对象、采样和要求均来自已保存的搜索协议。",12,MUTED)
    text(rx+3,954,f"主选候选 {selected['candidate_id']:02}  /  比较候选 {smooth:02}",15)
    cut(rx,989,rw,62,YELLOW)
    text(rx+23,1006,"冻结所选方案",23,BG)
    text(rx+rw-54,1003,"→",27,BG)
    text(rx+4,1070,"冻结后，才可运行新工况验证。",14,MUTED)

    line(298,1120,1890,1120)
    rect(298,1139,8,8,YELLOW)
    text(321,1135,"视觉提案 · 尚未接入主程序",15)
    text(776,1137,"真实数据来自 v0.8 已保存搜索；有限工况不构成鲁棒稳定性证明。",13,MUTED)
    # Sparse technical corner marks are original vector geometry.
    for x,y in ((289,313),(1899,313),(289,1101),(1899,1101)):
        line(x-4,y,x+4,y,"#647276");line(x,y-4,x,y+4,"#647276")
    svg.append('</svg>')
    output.parent.mkdir(parents=True,exist_ok=True)
    svg_path=output.parent/(output.name+'.svg')
    png_path=output.parent/(output.name+'.png')
    json_path=output.parent/(output.name+'.json')
    svg_path.write_text('\n'.join(svg),encoding='utf-8')
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFontDatabase,QImage,QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    for name in ('msyhbd.ttc','consola.ttf','bahnschrift.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
    renderer=QSvgRenderer(str(svg_path))
    if not renderer.isValid():raise ValueError('SVG rendering failed')
    image=QImage(W*2,H*2,QImage.Format.Format_ARGB32);image.fill(Qt.GlobalColor.transparent)
    painter=QPainter(image);renderer.render(painter);painter.end()
    if not image.scaled(W,H,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation).save(str(png_path)):raise OSError('PNG save failed')
    metadata=dict(status='visual_proposal_not_implemented',source_summary_sha256=hashlib.sha256((folder/'summary.json').read_bytes()).hexdigest(),
                  source_folder=str(folder),selected_candidate=selected['candidate_id'],comparison_candidate=smooth,
                  displayed_metrics=dict(J1=selected['J1'],J2=selected['J2'],baseline_J1=base['J1'],baseline_J2=base['J2']),
                  external_artworks_embedded=False,reference='https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2024/0926')
    json_path.write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Rendered original v0.9 visual proposal with saved v0.8 data.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--search',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'docs/design/v0.9-arknights-workbench')
    args=parser.parse_args()
    source=args.search
    if source is None:source=Path(json.loads((ROOT/'outputs/v08-verification.json').read_text(encoding='utf-8'))['folders']['first_search'])
    render(source,args.output)
