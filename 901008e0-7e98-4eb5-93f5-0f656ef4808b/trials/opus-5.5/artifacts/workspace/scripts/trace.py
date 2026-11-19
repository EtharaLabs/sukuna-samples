import json,sys,collections
runs={r['Run']:r for r in map(json.loads,open('allruns.jsonl'))}
T=list(map(json.loads,open('alltix.jsonl')))
CD=list(map(json.loads,open('allcd.jsonl')))
corr=json.load(open('corrections.json'))  # ticket -> source
seeds=json.load(open('seeds.json'))  # implicated tubs
extra=json.load(open('extra.json')) if len(sys.argv)>1 else {}
for t in T:
    if t['Ticket no'] in corr: t['Source']=corr[t['Ticket no']]
posted=[t for t in T if t['Status']=='Posted']
imp={}  # run -> reason
def add(run,why):
    if run not in imp: imp[run]=why; return True
    return False
for r,why in extra.items(): add(r,why)
byline=collections.defaultdict(list)
for r in runs.values(): byline[r['Line']].append(r)
for l in byline: byline[l].sort(key=lambda r:r['Start'])
def clean_between(line,a,b):
    for c in CD:
        if c['Line']==line and c['Result']=='Pass' and c['Swab test'] in ('Total protein','Sesame') and a['End']<c['Finished']<b['Start']:
            return c
    return None
changed=True
while changed:
    changed=False
    for t in posted:
        s=t['Source']
        if s in seeds or s in imp:
            changed|=add(t['Run'],'ticket %s from %s'%(t['Ticket no'],s))
    for l,rs in byline.items():
        for a,b in zip(rs,rs[1:]):
            if a['Run'] in imp and not clean_between(l,a,b):
                changed|=add(b['Run'],'carry-over on %s after %s'%(l,a['Run']))
for r,w in sorted(imp.items(),key=lambda x:runs[x[0]]['Start'] if x[0] in runs else ''):
    x=runs.get(r,{}); print(r,x.get('Kind'),x.get('Line'),x.get('Start'),x.get('End'),'|',w)
