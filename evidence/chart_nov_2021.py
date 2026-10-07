import json, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from datetime import date, timedelta
S=[("08MH001","Chilliwack R. at Vedder Crossing","#2a78d6","o"),
   ("08MH103","Chilliwack R. above Slesse Ck (upstream)","#eb6834","s"),
   ("08MH029","Sumas R. near Huntingdon","#1baf7a","^"),
   ("08MH155","Nicomekl R. at 203 St, Langley","#eda100","D")]
summ=json.load(open("summary.json"))
days=[date(2021,11,8)+timedelta(i) for i in range(15)]
fig,ax=plt.subplots(figsize=(10,5.6),dpi=150)
fig.patch.set_facecolor("#fcfcfb"); ax.set_facecolor("#fcfcfb")
rows=[]
for s,n,c,m in S:
    dm={r["DATE"]:r["DISCHARGE"] for r in json.load(open(f"{s}.json"))["dm"]}
    q2=summ[s]["q2"]
    y=[(dm.get(d.isoformat())/q2) if dm.get(d.isoformat()) is not None else float("nan") for d in days]
    ax.plot(days,y,color=c,lw=2,marker=m,ms=6,markeredgecolor="#fcfcfb",markeredgewidth=1.5,label=n,zorder=3)
    i=max(range(len(y)),key=lambda k:-1 if y[k]!=y[k] else y[k])
    ax.annotate(f"{y[i]:.1f}×",(days[i],y[i]),xytext=((8,-4) if s=="08MH029" else (-34,-3)),textcoords="offset points",fontsize=9,color="#333")
    rows.append((s,n,q2,max(v for v in y if v==v),days[i]))
ax.axhline(1,color="#8a8a85",lw=1,ls=(0,(4,3)),zorder=1)
ax.text(days[0],1.04,"typical yearly peak (median annual max daily flow)",fontsize=8.5,color="#5f5e5a")
ax.annotate("Sumas gauge:\nno data Nov 16–17",(date(2021,11,16),2.0),fontsize=8.5,color="#5f5e5a")
ax.set_ylabel("Daily mean flow ÷ station's typical yearly peak",fontsize=9.5,color="#333")
ax.set_title("November 2021: Fraser Valley gauges went past their typical yearly peak in a day",loc="left",fontsize=11.5,color="#111")
for sp in ["top","right"]: ax.spines[sp].set_visible(False)
for sp in ["left","bottom"]: ax.spines[sp].set_color("#c9c8c2")
ax.grid(axis="y",color="#e6e5df",lw=0.8); ax.tick_params(colors="#5f5e5a",labelsize=8.5)
ax.set_xticks(days[::2]); ax.set_xticklabels([d.strftime("%b %d") for d in days[::2]])
ax.set_ylim(0,3.1)
ax.legend(frameon=False,fontsize=8.5,loc="upper right")
fig.text(0.01,0.01,"Source: ECCC Water Survey of Canada, historical daily discharge (OGL-Canada). Contains data from Environment and Climate Change Canada.",fontsize=7.5,color="#7a7a75")
fig.tight_layout(rect=(0,0.03,1,1))
fig.savefig("nov-2021-fraser-valley.png",facecolor=fig.get_facecolor())
for r in rows: print(r)
