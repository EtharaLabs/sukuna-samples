import json,glob,sys
old=json.load(open('/workspace/work/recs.json'))
D='/logs/agent/sessions/projects/-workspace/c04d0ee3-1507-4573-94d0-03920898b379/tool-results/'
for f in sorted(glob.glob(D+'mcp-LightNotion-search-*')):
    if f.split('-')[-2] < sys.argv[1]: continue
    d=json.load(open(f))['output']['results']
    for r in d:
        if r.get('parent_id') in ('db-staffing-findings-oct-2026','db-actuals-corrections'): continue
        if r['id'] not in old: print('NEW',f[-15:],r['id'],json.dumps(r.get('properties'))[:400])
        elif json.dumps(old[r['id']],sort_keys=True)!=json.dumps(r,sort_keys=True):
            o={k:v['value'] for k,v in old[r['id']]['properties'].items()}; n={k:v['value'] for k,v in r['properties'].items()}
            print('CHG',r['id'],{k:(o.get(k),n.get(k)) for k in set(o)|set(n) if o.get(k)!=n.get(k)}, r.get('last_edited_time'))
    print(f[-15:],len(d))
