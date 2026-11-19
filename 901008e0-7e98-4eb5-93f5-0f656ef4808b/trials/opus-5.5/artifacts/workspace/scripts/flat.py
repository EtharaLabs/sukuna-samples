import json,sys
d=json.load(open(sys.argv[1]))
o=d['output']
print('#count',len(o['results']),'has_more',o.get('has_more'),'next',o.get('next_cursor'), file=sys.stderr)
for r in o['results']:
    p={k:v['value'] for k,v in r['properties'].items()}
    p['_id']=r['id']; p['_edited']=r.get('last_edited_time')
    print(json.dumps(p))
