import json,sys,os
# usage: ingest.py name file
name,f=sys.argv[1],sys.argv[2]
d=json.load(open(f))['output']
store=f'/workspace/work/{name}.jsonl'
ids=set()
if os.path.exists(store):
    ids={json.loads(l)['id'] for l in open(store)}
n=0
with open(store,'a') as o:
    for r in d.get('results',[]):
        if r['id'] in ids: continue
        p={k:(v['value'] if isinstance(v,dict) and 'value' in v else v) for k,v in r.get('properties',{}).items()}
        o.write(json.dumps({'id':r['id'],'title':r.get('title'),'archived':r.get('archived'),'last_edited':r.get('last_edited_time'),'p':p})+'\n'); n+=1
print('added',n,'has_more',d.get('has_more'),'next',d.get('next_cursor'),'total',len(ids)+n)
