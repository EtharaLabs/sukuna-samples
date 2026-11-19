import json,re
recs=json.load(open('/workspace/work/recs.json'))
pages=[]
for fn in ['ts_batch1.txt','ts_batch2.txt','ts_batch3.txt']:
    cur=None
    for l in open('/workspace/work/'+fn):
        l=l.strip()
        if l.startswith('FILE'): cur={'file':l.split()[1],'rows':[],'notes':[]}; pages.append(cur)
        elif l.startswith('ROW'):
            c=[x.strip() for x in l[4:].split('|')]; cur['rows'].append(c)
        elif l.startswith('NOTE'): cur['notes'].append(l)
acts=[ {k:v['value'] for k,v in r['properties'].items()} for r in recs.values() if r['id'].startswith('act-') and r['properties']['Type']['value']=='Ward shift']
for pg in pages:
    b,d,n=pg['file'][:-4].split('_')
    sites={x for r in pg['rows'] for x in (r[2],r[3]) if x in('MGH','WGH')}
    first=pg['rows'][0][4]; last=pg['rows'][-1][5].split('->')[-1]
    cands=[a for a in acts if a['Timesheet book']==b and (a['Start (UTC)'][:10]==d or a['Clock-out last assignment (UTC)'][:10]==d)]
    m=[a for a in cands if a['Start (UTC)'][11:16]<=first and a['Start (UTC)'][:10]<=d]
    best=None
    for a in cands:
        bays=a['Assignments'].split()
        ov=len(set(bays)&{r[1] for r in pg['rows']})
        if ov: best=(ov,a)
    tag='MATCH' if best else '-----'
    s=f"{pg['file']} sites={sites} {first}-{last} n={len(pg['rows'])} notes={len(pg['notes'])}"
    if best:
        a=best[1]; s+=f" || {a['Shift ref']} {a['Staff number']} {a['Start (UTC)']} {a['Clock-out last assignment (UTC)']} n={a['Ward assignments']} [{a['Assignments']}] ov={best[0]}"
        diff = a['Clock-out last assignment (UTC)'][11:16]!=last or a['Ward assignments']!=len(pg['rows'])
        s+= '  DIFF' if diff else ''
    print(tag,s)
