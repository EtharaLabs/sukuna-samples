import json,sys
from datetime import datetime,timedelta,timezone
sys.path.insert(0,'/workspace/work')
from certs import CERTS,UNSIGNED
R=json.load(open('/workspace/work/roster.json')); C=json.load(open('/workspace/work/cards.json'))
def cv(i): return {c['id']:c['text'] for c in i['column_values']}
ros={}
for i in R:
  v=cv(i); v['name']=i['name']; v['item']=i['id']; ros[v['duty_ref']]=v
cards={c['properties']['DutyRef']['value']:dict({k:x['value'] for k,x in c['properties'].items()},page=c['id'],edited=c['last_edited_time']) for c in C}
