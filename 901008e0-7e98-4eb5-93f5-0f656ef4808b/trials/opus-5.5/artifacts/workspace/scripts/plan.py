import json,collections
imp={l.split()[0] for l in open('imp.txt')}
P=list(map(json.loads,open('pallets.jsonl')))
onsite={'chiller','dispatch bay','Ridgeway cold store'}
hold=[];rec=collections.defaultdict(list);other=[]
batches=sorted(b for b in imp if b.startswith('FB-'))
for p in P:
    bs=[b.strip() for b in p['Batch'].split(',')]
    ib=[b for b in bs if b in imp]
    if not ib: continue
    if p['Location'] in onsite: hold.append((p['Pallet'],p['_id'],ib,p['Location']))
    elif p['Location'] in ('shipped','In transit'): rec[p['Customer']].append((p['Pallet'],p['_id'],ib,p['Location']))
    else: other.append(p)
print('batches',len(batches),', '.join(sorted(batches,key=lambda b:int(b[3:]))))
print('hold',len(hold)); print('recall',sum(len(v) for v in rec.values()))
for c,v in rec.items(): print(c,len(v),v)
print('other',other)
json.dump({'hold':hold,'rec':rec,'batches':batches},open('plan.json','w'))
