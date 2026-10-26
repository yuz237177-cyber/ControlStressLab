"""White-background export figures from persisted frequency data."""
import csv
import numpy as np
from matplotlib.figure import Figure
CHANNELS=("L","S","T","Y_R","Y_D")
def draw(figure,folder,records,mode,colors=None):
    figure.clear()
    if mode=="bode":
        axes=figure.subplots(2,1,sharex=True)
        for i,r in enumerate(records):
            with (folder/"frequency"/(r["controller_name"]+".csv")).open(encoding="utf-8") as f:rows=list(csv.DictReader(f))
            w=[float(v["omega_rad_s"]) for v in rows];color=colors[i%len(colors)] if colors else None
            axes[0].semilogx(w,[float(v["L_db"]) if v["L_db"] else np.nan for v in rows],label=r["controller_name"],color=color)
            axes[1].semilogx(w,[float(v["loop_phase_deg"]) if v["loop_phase_deg"] else np.nan for v in rows],color=color)
        axes[0].set_ylabel("Loop / dB");axes[0].axhline(0,color="gray",lw=.7);axes[1].set_ylabel("Phase / deg");axes[1].set_xlabel("Frequency / rad s⁻¹")
    elif mode=="poles":
        ax=figure.add_subplot();axes=[ax];t=np.linspace(0,2*np.pi,400);ax.plot(np.cos(t),np.sin(t),"--",color="gray")
        for i,r in enumerate(records):
            p=r["summary"]["internal"]["poles"];ax.scatter([z["real"] for z in p],[z["imag"] for z in p],marker="x",label=r["controller_name"],color=colors[i%len(colors)] if colors else None)
        ax.set_aspect("equal",adjustable="datalim");ax.set_xlabel("Real");ax.set_ylabel("Imaginary")
    else:
        ax=figure.add_subplot();axes=[ax];keys=("S","T") if mode=="sensitivity" else ("Y_R","Y_D")
        for i,r in enumerate(records):
            with (folder/"frequency"/(r["controller_name"]+".csv")).open(encoding="utf-8") as f:rows=list(csv.DictReader(f))
            for j,key in enumerate(keys):
                ax.semilogx([float(v["omega_rad_s"]) for v in rows],[float(v[key+"_db"]) if v[key+"_db"] else np.nan for v in rows],ls="-" if j==0 else "--",label=r["controller_name"]+" "+key,color=colors[i%len(colors)] if colors else None)
        ax.set_ylabel("Magnitude / dB");ax.set_xlabel("Frequency / rad s⁻¹")
    for ax in axes:ax.grid(alpha=.2)
    axes[0].legend(fontsize=8)
def build(folder,records):
    for mode in ("bode","poles","sensitivity","channels"):
        fig=Figure(figsize=(12,7),layout="constrained");draw(fig,folder,records,mode)
        for suffix in ("png","svg"):fig.savefig(folder/"figures"/(mode+"."+suffix),dpi=150)
