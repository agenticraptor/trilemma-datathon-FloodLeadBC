import json, urllib.request, urllib.parse, sys
B="https://api.weather.gc.ca/collections"
ST={"08MH001":"Chilliwack R. at Vedder Crossing","08MH029":"Sumas R. near Huntingdon","08MH024":"Fraser R. at Mission","08MH155":"Nicomekl R. at 203 St, Langley","08MF062":"Coquihalla R. below Needle Ck","08MH103":"Chilliwack R. above Slesse Ck","08MH056":"Slesse Ck near Vedder Crossing"}
def get(coll, params):
    out=[]; off=0
    while True:
        p=dict(params, f="json", limit=10000, offset=off)
        u=f"{B}/{coll}/items?"+urllib.parse.urlencode(p)
        d=json.load(urllib.request.urlopen(u, timeout=120))
        fs=d.get("features",[]); out+=fs
        if len(fs)<10000: return out
        off+=10000
res={}
for s,n in ST.items():
    rt=get("hydrometric-realtime",{"STATION_NUMBER":s})
    dm=get("hydrometric-daily-mean",{"STATION_NUMBER":s})
    json.dump({"rt":[f["properties"] for f in rt],"dm":[f["properties"] for f in dm]}, open(f"{s}.json","w"))
    print(s, n, "realtime rows:",len(rt),"daily rows:",len(dm), flush=True)
