import json,sys
# extract tool_result texts containing a given parent db id with has_more false
log=sys.argv[1]; db=sys.argv[2]
seen=set(); out={}
for line in open(log):
    try: e=json.loads(line)
    except: continue
    m=e.get('message') or {}
    c=m.get('content')
    if not isinstance(c,list): continue
    for part in c:
        if part.get('type')!='tool_result': continue
        cont=part.get('content')
        texts=[]
        if isinstance(cont,str): texts=[cont]
        elif isinstance(cont,list): texts=[x.get('text','') for x in cont if isinstance(x,dict)]
        for t in texts:
            if '"parent_id":"%s"'%db not in t: continue
            try: d=json.loads(t)
            except: continue
            if not isinstance(d.get('output'),dict) or 'results' not in d['output']: continue
            for r in d['output']['results']:
                if r['parent_id']!=db: continue
                p={k:v['value'] for k,v in r['properties'].items()}
                p['_id']=r['id']; p['_edited']=r.get('last_edited_time')
                out[r['id']]=p

for v in out.values(): print(json.dumps(v))
