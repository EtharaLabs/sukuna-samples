import json,sys
from datetime import datetime,timedelta,timezone,date
recs=json.load(open('/workspace/work/recs.json'))
OV=json.load(open('/workspace/work/overrides.json'))  # per shift ref overrides
INSCOPE=[json.loads(l)['p']['Staff number'] for l in open('/workspace/work/nurses.jsonl') if json.loads(l)['p']['Unit']=='Acute Medicine' and json.loads(l)['p']['Site']=='MGH']
def T(s): return datetime.strptime(s,'%Y-%m-%dT%H:%MZ').replace(tzinfo=timezone.utc)
DST_END=T('2026-10-25T01:00Z'); REV7=T('2026-10-14T23:00Z')
def local(t): return t+timedelta(hours=1) if t<DST_END else t
def rev(t): return 'Rev 7' if t>=REV7 else 'Rev 6'
TABLE={6:[(360,809,[780,750,720,690,660]),(810,839,[765,735,705,675,645]),(840,1049,[720,690,660,630,600]),(300,359,[720,690,660,630,600])],
       7:[(360,809,[780,750,720,690,660]),(810,839,[765,735,705,675,645]),(840,1049,[720,690,660,630,600]),(300,359,[690,660,630,600,570])]}
NIGHT=[660,630,600,570,540]
def maxshift(r,lt,n):
    m=lt.hour*60+lt.minute
    col=0 if n<=2 else min(n,6)-2
    for lo,hi,row in TABLE[r]:
        if lo<=m<=hi: return row[col],(lo,hi)
    return NIGHT[col],(1050,299)
ALLOW={6:120,7:90}
PERIOD=(date(2026,10,1),date(2026,10,28))
def mins(a,b): return int((b-a).total_seconds()//60)
out=[]; detail=[]
for sn in INSCOPE:
    duties=[]
    for r in recs.values():
        if not r['id'].startswith('act-'): continue
        p={k:v['value'] for k,v in r['properties'].items()}
        if p['Staff number']!=sn: continue
        ref=p['Shift ref']; o=OV.get(ref,{})
        typ=o.get('Type',p['Type'])
        if p['Type']=='Ward shift':
            st=T(o.get('Start',p['Start (UTC)'])); en=T(o.get('End',p['Clock-out last assignment (UTC)']))
            n=o.get('Assignments',p['Ward assignments'])
            duties.append(dict(ref=ref,kind='shift',start=st,end=en,n=n,ext_auth=o.get('ext_signed',False),ev=o.get('ev',[]),transfer=o.get('transfer',False)))
        else:
            st=T(p['Start (UTC)']); en=T(o.get('End',p['End (UTC)']))
            duties.append(dict(ref=ref,kind='site' if typ=='On-site on-call' else 'home',start=st,end=en,ev=o.get('ev',[])))
    duties.sort(key=lambda d:d['start'])
    prev_end=None; prev_len=None; prev_ext=0
    for d in duties:
        if d['kind']=='shift':
            L=mins(d['start'],d['end']); R=7 if d['start']>=REV7 else 6
            lt=local(d['start']); n=d['n']+(1 if R==7 and d.get('transfer') else 0)
            mx,band=maxshift(R,lt,n)
            inper=PERIOD[0]<=lt.date()<=PERIOD[1]
            ext=0
            if L>mx:
                if d['ext_auth']:
                    lim=mx+ALLOW[R]; ext=min(L-mx,ALLOW[R])
                    if L>lim and inper: out.append(dict(sn=sn,ref=d['ref'],lt='EXTENSION',ed=f'Rev {R}',limit=lim,actual=L,excess=L-lim,ev=d['ev'],band=band,n=n))
                elif inper: out.append(dict(sn=sn,ref=d['ref'],lt='SHIFT',ed=f'Rev {R}',limit=mx,actual=L,excess=L-mx,ev=d['ev'],band=band,n=n))
            # rest
            if prev_end is not None and inper:
                rest=mins(prev_end,d['start']); need=max(prev_len,660)+(prev_ext if R==7 else 0)
                if rest<need: out.append(dict(sn=sn,ref=d['ref'],lt='REST',ed=f'Rev {R}',limit=need,actual=rest,excess=need-rest,ev=sorted(set(d['ev']+prev_ev)),prevref=prev_ref,prevend=str(prev_end)))
            detail.append((sn,d['ref'],lt.strftime('%m-%d %H:%M'),L,n,mx,d['ext_auth'],R))
            prev_end=d['end']+timedelta(minutes=30); prev_len=L+30; prev_ext=ext; prev_ref=d['ref']; prev_ev=d['ev']
        elif d['kind']=='site':
            prev_end=d['end']; prev_len=mins(d['start'],d['end']); prev_ext=0; prev_ref=d['ref']; prev_ev=d['ev']
    # rolling
    day={}; dev={}
    for d in duties:
        L=mins(d['start'],d['end'])
        w={'shift':L+30,'site':L,'home':L/4}[d['kind']]
        k=local(d['start']).date(); day[k]=day.get(k,0)+w; dev.setdefault(k,[]).extend(d['ev'])
    for W,lim,lt in [(7,3600,'HOURS_7D'),(14,6600,'HOURS_14D'),(28,11400,'HOURS_28D')]:
        x=PERIOD[0]
        while x<=PERIOD[1]:
            tot=sum(v for k,v in day.items() if x-timedelta(days=W-1)<=k<=x)
            if tot>lim:
                out.append(dict(sn=sn,ref=x.isoformat(),lt=lt,ed=rev(datetime(x.year,x.month,x.day,12,tzinfo=timezone.utc)),limit=lim,actual=tot,excess=tot-lim,ev=sorted({e for k,v in dev.items() if x-timedelta(days=W-1)<=k<=x for e in v}))); break
            x+=timedelta(days=1)
json.dump(out,open('/workspace/work/findings.json','w'),default=str,indent=0)
for f in out: print(f)
print(len(out), sum(f['excess'] for f in out))
