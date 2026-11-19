import json,sys
from load import *
from datetime import datetime,timedelta
REV14=datetime(2026,9,14,23,0)  # 00:00 local 15 Sep in UTC
CDR={r[1]:dict(id=r[0],signed=r[2]=='Yes',rep=r[3],end=r[4]) for r in json.load(open('cdr.json'))}
OVR_TL={('E9-0909-ABZ-573','45269'):'TL-28498',('E9-0923-ABZ-816','36330'):'TL-86765'}
CALLOUT={('E9-0921-ABZ-775','45677'):('VN-119',datetime(2026,9,21,7,0))}
AIRSB={('E9-0909-ABZ-812','49301'):'VN-686',('E9-0918-ABZ-164','45175'):'VN-717'}
def tab(rev,loc,sec):
    m=loc.hour*60+loc.minute
    col=min(sec,6); ci={1:0,2:0,3:1,4:2,5:3,6:4}[max(col,1)]
    rows=[((360,809),[780,750,720,690,660]),((810,839),[765,735,705,675,645]),((840,1049),[720,690,660,630,600])]
    if 300<=m<360: r=[720,690,660,630,600] if rev==13 else [690,660,630,600,570]; row='05:00 to 05:59'
    elif 360<=m<=809: r=rows[0][1]; row='06:00 to 13:29'
    elif 810<=m<=839: r=rows[1][1]; row='13:30 to 13:59'
    elif 840<=m<=1049: r=rows[2][1]; row='14:00 to 17:29'
    else: r=[660,630,600,570,540]; row='17:30 to 04:59'
    return r[ci],row,['1-2','3','4','5','6 or more'][ci]
duties={}
for x in A:
    s=P(x,'Staff number'); ref=P(x,'Duty ref'); k=(ref,s); ty=P(x,'Type')
    d=dict(ref=ref,s=s,type=ty,ev=[])
    rep=T(P(x,'Report (UTC)'))
    if ty=='Flight duty':
        ob=T(P(x,'On-blocks last sector (UTC)')); sec=P(x,'Sectors'); fl=P(x,'Flights').split()
        assert sec==len(fl),(k,sec,fl)
        route=P(RO[k],'Route'); endst=route.split('-')[-1] if route else None
        pos=0
        if k in OVR_TL:
            tl=TL[OVR_TL[k]]; sec=len(tl['secs']); last=tl['secs'][-1]
            hh,mm=map(int,last[5].split(':')); ob2=ob.replace(hour=hh,minute=mm)
            if ob2<ob-timedelta(hours=12): ob2+=timedelta(days=1)
            if ob2<rep: ob2+=timedelta(days=1)
            ob=ob2; endst=last[3]; d['ev'].append(OVR_TL[k])
        if k in CALLOUT:
            vid,t=CALLOUT[k]; rep=t; pos=1; d['ev'].append(vid)
        rev=14 if rep>=REV14 else 13
        d.update(rep=rep,ob=ob,sec=sec,pos=pos,rev=rev,end=ob+timedelta(minutes=30),endst=endst,fdp=(ob-rep).total_seconds()/60)
        c=CDR.get(ref)
        disc_flag=P(x,'Discretion used'); d['flag']=disc_flag; d['flagrpt']=P(x,'Discretion report')
        d['cdr']=c
        d['len']=d['fdp']+30; d['cum']=d['len']
    else:
        end=T(P(x,'End (UTC)'))
        if k in AIRSB: ty='Airport standby'; d['type']=ty; d['ev'].append(AIRSB[k])
        d.update(rep=rep,end=end,len=(end-rep).total_seconds()/60,rev=14 if rep>=REV14 else 13)
        d['cum']=d['len'] if ty=='Airport standby' else d['len']/4
    duties[k]=d
json.dump({f'{k[0]}|{k[1]}':{a:(str(b) if isinstance(b,datetime) else b) for a,b in v.items()} for k,v in duties.items()},open('duties.json','w'),indent=0,default=str)
