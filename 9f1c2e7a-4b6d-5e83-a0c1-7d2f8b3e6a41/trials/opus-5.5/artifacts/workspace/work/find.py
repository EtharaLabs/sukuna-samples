from audit import *
L=lambda t:t+timedelta(hours=1)
B0=datetime(2026,9,1); B1=datetime(2026,9,29)
F=[]; notes=[]
bys={}
for d in duties.values(): bys.setdefault(d['s'],[]).append(d)
for s in bys: bys[s].sort(key=lambda d:d['rep'])
for s,ds in bys.items():
    for i,d in enumerate(ds):
        if d['type']!='Flight duty': continue
        inb = B0<=L(d['rep'])<B1
        rev=d['rev']; secs=d['sec']+(d['pos'] if rev==14 else 0)
        mx,row,col=tab(rev,L(d['rep']),secs)
        fdp=d['fdp']; c=d['cdr']; ext=0
        maxext=120 if rev==13 else 90
        signed= c is not None and c['signed']
        if c and inb: notes.append((d['ref'],s,'CDR',c['id'],c['signed'],'flag',d['flag'],d['flagrpt'],'fdp',fdp,'max',mx, 'cdr times',c['rep'],c['end'],'act',d['rep'],d['ob']))
        elif d['flag']=='Yes' and inb: notes.append((d['ref'],s,'flag yes no CDR',d['flagrpt']))
        if fdp>mx:
            if signed:
                ext=min(fdp-mx,maxext)
                if fdp>mx+maxext and inb: F.append(dict(s=s,ref=d['ref'],lt='DISCRETION',rev=rev,lim=mx+maxext,act=fdp,ev=d['ev']+[c['id']],why=f'Rev{rev} App A {row} {col} sectors {mx} + 7.4.1 {maxext}'))
            else:
                ev=list(d['ev'])
                if c and not c['signed']: ev.append(c['id'])
                if inb: F.append(dict(s=s,ref=d['ref'],lt='FDP',rev=rev,lim=mx,act=fdp,ev=ev,why=f'Rev{rev} App A {row} {col} sectors'))
        d['ext']=ext; d['mx']=mx
        # rest
        prev=[p for p in ds[:i] if p['type']!='Home standby']
        if prev and inb:
            p=prev[-1]
            home = (p.get('endst','ABZ')=='ABZ') if p['type']=='Flight duty' else True
            mn=max(p['len'],720 if home else 600)
            add=0
            if rev==14 and p['type']=='Flight duty' and p.get('ext',0)>0: add=p['ext']
            mn+=add
            rest=(d['rep']-p['end']).total_seconds()/60
            if rest<mn:
                ev=list(d['ev'])+[e for e in p['ev']]
                if add and p['cdr']: ev.append(p['cdr']['id'])
                F.append(dict(s=s,ref=d['ref'],lt='REST',rev=rev,lim=mn,act=rest,ev=ev,why=f'Rev{rev} 7.5.1 prev {p["ref"]} len {p["len"]} home {home} add {add}'))
# cumulative
from collections import defaultdict
for s,ds in bys.items():
    day=defaultdict(float); evd=defaultdict(list)
    for d in ds:
        dd=L(d['rep']).date(); day[dd]+=d['cum']; evd[dd]+=d['ev']
    for n,lim,lt in ((7,3600,'DUTY_7D'),(14,6600,'DUTY_14D'),(28,11400,'DUTY_28D')):
        for k in range(28):
            end=(B0+timedelta(days=k)).date()
            days=[end-timedelta(days=j) for j in range(n)]
            tot=sum(day[x] for x in days)
            if tot>lim:
                ev=sorted(set(e for x in days for e in evd[x]))
                F.append(dict(s=s,ref=str(end),lt=lt,rev=14 if end>=datetime(2026,9,15).date() else 13,lim=lim,act=tot,ev=ev,why=f'7.6.1 {n}d'))
                break
