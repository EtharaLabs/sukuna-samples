import json
from datetime import datetime,timedelta
INS=set('45175 44049 32894 47639 35947 36330 49130 37712 39638 32200 48146 49580 36107 31279 45269 37488 32319 49946 43699 38571 45677 40672 31527 31564 44873 43840 49301 45172'.split())
P=lambda x,k:x['properties'].get(k,{}).get('value')
def T(s): return datetime.strptime(s,'%Y-%m-%dT%H:%MZ') if s else None
A=[x for x in json.load(open('/workspace/work/actuals_search.json')) if P(x,'Staff number') in INS]
RO={(P(x,'Duty ref'),P(x,'Staff number')):x for x in json.load(open('/workspace/work/roster_rows.json'))}
TL=json.load(open('/workspace/work/tl.json'))
