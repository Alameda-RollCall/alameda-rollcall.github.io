import json,re,os,sys,collections
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import audit as au
sv=au.sv; OUT=au.OUT
d=json.load(open(os.path.join(au.ROOT,'votes.json'))); V=d['votes']
F=collections.defaultdict(list)
inoff=lambda date:{s for s in sv.TENURE if sv.in_office(s,date)}
# C2 per-vote membership vs tenure
for v in V:
    io=inoff(v['date']); got=set(v['votes'])
    out=got-io; miss=io-got
    if out: F['C2_voter_outside_tenure'].append((v['id'],v['date'],sorted(out)))
    if miss: F['C2_member_missing'].append((v['id'],v['date'],v['title'][:50],sorted(miss),v['votes']))
# C3 result vs counts
for v in V:
    a=sum(x=='aye' for x in v['votes'].values()); n=sum(x=='no' for x in v['votes'].values())
    if v['result']=='passed' and a<=n: F['C3_passed_not_majority'].append((v['id'],v['date'],a,n,v['title'][:60]))
    if v['result']=='failed' and a>n: F['C3_failed_with_ayes_ahead'].append((v['id'],v['date'],a,n,v['title'][:60],v.get('note','')[:30]))
    if v['result']=='passed' and a<3: F['C3_passed_under3'].append((v['id'],v['date'],a,n,v['title'][:60]))
    if v['result'] not in('passed','failed'): F['C3_odd_result'].append((v['id'],v['result']))
# C4 duplicates
seen=collections.defaultdict(list)
for v in V: seen[(v['date'],v['title'])].append(v)
for k,l in seen.items():
    if len(l)>1: F['C4_same_date_title'].append((k[0],k[1][:60],[x['id'] for x in l],[x['votes']==l[0]['votes'] for x in l]))
ids=collections.Counter(v['id'] for v in V)
F['C4_dup_ids']=[k for k,c in ids.items() if c>1]
# C1 roll call per section
for m,c in au.load_docs():
    for sec in au.sections(c['plain']):
        date=sv.parse_meeting_date(sec,matter_file=c.get('file') or m.get('MatterFile',''))
        if not date or date<'2013-08-01': continue
        pr,ab=sv.parse_roll_call(sec); pr2=sv.fix_roll_call(list(pr),date)
        io=inoff(date)
        both=set(pr)&set(ab)
        if both: F['C1_present_and_absent'].append((date,m['MatterId'],sorted(both)))
        if len(pr)>=3 and (set(pr2)|set(ab))!=io: F['C1_roll_vs_tenure'].append((date,m['MatterId'],sorted(set(pr2)),sorted(ab),sorted(io)))
json.dump(F,open(os.path.join(OUT,'audit_C.json'),'w'),indent=1,default=str)
print({k:len(v) for k,v in F.items()})
