import re,glob,json
out={}
for f in glob.glob('/workspace/data/techlog/*.txt'):
    t=open(f).read()
    m=re.search(r'Page (TL-\d+)\s+Aircraft (\S+)\s+Date (\S+)',t)
    secs=[]
    for l in t.splitlines():
        p=[x.strip() for x in l.split('|')]
        if len(p)==7 and p[0].isdigit(): secs.append(p)
    out[m.group(1)]=dict(ac=m.group(2),date=m.group(3),secs=secs,file=f.split('/')[-1])
json.dump(out,open('tl.json','w'))
print(len(out))
