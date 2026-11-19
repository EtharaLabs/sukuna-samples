import json,glob,sys,os
D='/logs/agent/sessions/projects/-workspace/62bdf77f-470e-4273-a1ec-45fcbe90e362/tool-results/'
recs={}
for f in sorted(glob.glob(D+'*.txt'), key=os.path.getmtime):
    try: d=json.load(open(f))
    except Exception: continue
    o=d.get('output')
    if not isinstance(o,dict): continue
    rs=o.get('results') or ([o] if 'id' in o else [])
    for r in rs:
        if isinstance(r,dict) and 'id' in r: recs[r['id']]=r
json.dump(recs,open('/workspace/work/recs.json','w'))
from collections import Counter
print(len(recs), Counter(r.get('parent_id') for r in recs.values()))
