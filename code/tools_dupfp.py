"""Content-fingerprint duplicate scan: catches papers retitled between preprint and publication."""
import csv,re,os,glob,collections,itertools,json
idx={r['key']:r for r in csv.DictReader(open('database/papers_index.csv'))}
rows=list(csv.DictReader(open('database/aimdb.csv')))
cnt=collections.Counter(r['entry_id'].rsplit('-',1)[0] for r in rows)
NUM=re.compile(r'(?<![\d.])\d{1,3}\.\d{2,4}(?![\d])')   # distinctive decimals like 7.43, 2.291
fp={}
for k in idx:
    p=f'text/{k}.txt'
    if not os.path.exists(p): continue
    t=open(p,encoding='utf-8',errors='replace').read()
    s=set(NUM.findall(t))
    if len(s)>=25: fp[k]=s          # need enough numbers for the signature to mean anything
print(f"fingerprinted {len(fp)} papers with >=25 distinctive decimals")
# invert: which papers share each rare number
inv=collections.defaultdict(set)
for k,s in fp.items():
    for n in s: inv[n].add(k)
rare={n:ks for n,ks in inv.items() if 2<=len(ks)<=6}
pair=collections.Counter()
for n,ks in rare.items():
    for a,b in itertools.combinations(sorted(ks),2): pair[(a,b)]+=1
cands=[]
for (a,b),shared in pair.items():
    if shared<15: continue
    if idx[a]['doi'].lower()==idx[b]['doi'].lower(): continue
    j=shared/len(fp[a]|fp[b])
    if j<0.10: continue
    cands.append((j,shared,a,b))
cands.sort(reverse=True)
print(f"\ncandidate pairs (>=15 shared rare decimals, Jaccard>=0.10): {len(cands)}\n")
out=[]
for j,shared,a,b in cands[:25]:
    ra,rb=idx[a],idx[b]
    print(f"  J={j:.2f} shared={shared:3d}")
    print(f"     {a:14s} [{ra['status']:16s}] rows={cnt.get(a,0)}  {ra['doi']}")
    print(f"        {ra['title'][:88]}")
    print(f"     {b:14s} [{rb['status']:16s}] rows={cnt.get(b,0)}  {rb['doi']}")
    print(f"        {rb['title'][:88]}\n")
    out.append({'a':a,'b':b,'jaccard':round(j,3),'shared':shared})
json.dump(out,open('/tmp/claude-8718/-gpfs-projects-p32664-claude/a3ee635e-4675-4541-b751-7dbc05edfde9/scratchpad/dupfp.json','w'),indent=1)
