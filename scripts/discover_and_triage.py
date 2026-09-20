import json,re,html,urllib.request,concurrent.futures
SL="""
gitlab hashicorp docker circleci jfrog harness codefresh
sourcegraph replit vercel netlify render railwayapp flyio
linear height shortcut productboard aha
gong outreach salesloft apollo-io clari
drift intercom zendesk freshworks helpscout front
loom descript riverside veed opus-clip
calendly savvycal doodle clockwise reclaim
rippling deel remote oysterhr velocityglobal papayaglobal
justworks trinet insperity paychex
lattice culture-amp cultureamp 15five leapsome
greenhouse-software smartrecruiters jobvite icims
checkr sterling goodhire truework argyle
alloy persona socure-inc middesk
unit01 unit synctera treasuryprime column
marqeta lithic-inc highnote galileo
finix payrix rainforestpay
carta pulley ledgy angelist
mercury-technologies brex-inc
betterment wealthsimple m1finance titan
nerdwallet creditkarma lendingtree
earnin brigit moneylion selfinc
tally qapital digit
policygenius ethos ladder bestow haven-life
sidecarhealth curative honestmedical
ro hims thirtymadison cerebral
spring-health lyrahealth headspace calm ginger
maven progyny carrotfertility kindbody
wheel sesame plushcare mdlive amwell
capsule alto nowrx truepill
tia parsleyhealth oneMedical forwardhealth
zus particlehealth healthverity datavant
komodohealth trillianthealth clarifyhealth
cedar waystar availity zelis
olive notable qventus laudio
hingehealth limeadeinc virginpulse
sharecare healthjoy rightway
bright-health friday-health
clearcover branchinsurance metromile
jerry insurify thezebra
goosehead brightway
divvyhomes landis home-partners
roofstock mynd doorstead
avantstay sonder placemakr
hopper going scottscheapflights
tripactions navan-inc
freshbooks waveapps zoho
pilotcom bench botkeeper
puzzlefinancial rippling-inc
ramp-financial airbase-inc
brexhq mesh-payments
teampay center-app
navan-travel
figment alchemy quicknode infura
fireblocks anchorage bitgo
gemini kraken bitstamp
circle paxos
chainalysis trmlabs elliptic
opensea magiceden
"""
SL=sorted(set(s for s in SL.split() if s))
KW=re.compile(r'\b(customer (support|service|experience|success)|technical support|support (specialist|associate|agent|representative|analyst|engineer)|help ?desk|service desk|it support|desktop support|recruiting coordinator|talent coordinator|recruiting associate|people operations|hr (coordinator|assistant|associate|generalist)|onboarding (coordinator|specialist|associate)|administrative (assistant|coordinator|associate)|executive assistant|office (coordinator|manager|administrator|assistant)|data entry|operations (associate|specialist|coordinator|analyst|assistant)|business operations|program coordinator|project coordinator|scheduling coordinator|scheduler|dispatcher|associate analyst|junior|entry.level|soc analyst|security analyst|information security analyst|it (technician|analyst|associate|specialist)|billing (specialist|coordinator|analyst)|accounts (payable|receivable)|order (management|operations)|claims (processor|specialist)|receptionist|front desk)\b',re.I)
BAD=re.compile(r'\b(senior|sr\.?|staff|principal|lead\b|manager|director|head of|\bvp\b|vice president|architect|intern\b)\b',re.I)
LOCAL=['los angeles','el segundo','torrance','hawthorne','gardena','carson','long beach','inglewood','compton','culver city','redondo','manhattan beach','lawndale','santa monica','downey','cerritos','vernon','commerce']
FOR=['canada','india','united kingdom',' uk','ireland','germany','netherlands','singapore','australia','emea','apac','philippines','mexico','brazil','poland','spain','france','japan','china','colombia','argentina','portugal','croatia','estonia','malaysia','thailand','vietnam','romania','israel','korea','taiwan','hungary','czech','sweden','denmark','norway','italy','belgium','switzerland','austria','greece','turkey','nigeria','kenya','south africa','new zealand','costa rica','chile','peru','serbia','bulgaria','lithuania','ukraine','dublin','london','berlin','paris','amsterdam','toronto','vancouver','sydney','tokyo','manila','bogota','armenia','egypt','uae','dubai','bengaluru','hyderabad','pune','krakow','warsaw','lisbon','madrid','barcelona','zurich','munich','stockholm','oslo','helsinki','tel aviv','seoul','shanghai','beijing','hong kong','kuala','jakarta','cairo','lagos','nairobi','melbourne','auckland','montreal','ottawa','calgary','waterloo']
def okl(lo):
    lo=(lo or '').lower()
    if any(f in lo for f in FOR): return None
    if 'remote' in lo or lo.strip() in ('united states','usa','us','u.s.','anywhere','remote - us','united states of america'): return 'remote'
    if any(c in lo for c in LOCAL): return 'local'
    return None
def fetch(u):
    r=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
    return json.load(urllib.request.urlopen(r,timeout=15))
def g(s):
    o=[]
    try:
        for j in fetch(f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs").get('jobs',[]):
            t=j['title']; lc=(j.get('location') or {}).get('name','')
            if not KW.search(t) or BAD.search(t): continue
            w=okl(lc)
            if w: o.append(('greenhouse',s,str(j['id']),t,lc,w,j['absolute_url']))
    except Exception: pass
    return o
def l(s):
    o=[]
    try:
        for j in fetch(f"https://api.lever.co/v0/postings/{s}?mode=json"):
            t=j.get('text',''); lc=(j.get('categories') or {}).get('location','')
            if not KW.search(t) or BAD.search(t): continue
            w=okl(lc)
            if w: o.append(('lever',s,j['id'],t,lc,w,j['hostedUrl']))
    except Exception: pass
    return o
res=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=14) as ex:
    for f in (g,l):
        for r in ex.map(f,SL): res.extend(r)
json.dump(res,open('/tmp/sweep5_out.json','w'),indent=1)
print("HITS",len(res),"of",len(SL),"slugs")

# ---- stage 2: pull full JD + required questions, auto-flag knockouts
SCHED=re.compile(r'weekend|on-?call|overnight|evening|rotating (shift|schedule|basis)|24/7|24x7|after.hours|night shift|swing shift|holiday coverage|shift work|shifts',re.I)
YRS=re.compile(r'(\b[3-9]\+?\s*(?:-\s*\d+)?\s*years?|\b\d+\s*-\s*\d+\s*years?)',re.I)
RESID=re.compile(r'must (?:live|reside|be located)|residents? of|eligible to work in the following states|located in (?:one of )?the following',re.I)
BADQ=re.compile(r'essential function|non-?compete|restrictive covenant|post.employment|start date|earliest.*(?:start|available)|when (?:can|could) you start|bilingual|fluent in|sponsorship',re.I)
def txt(c):
    t=re.sub('<[^>]+>','\n',html.unescape(c or '')); t=re.sub('[ \t]+',' ',t); return re.sub('\n{2,}','\n',t)
def jd(item):
    src,s,jid,t,lc,w,url=item
    if src!='greenhouse': return None
    try:
        d=fetch(f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs/{jid}?questions=true")
    except Exception as e: return (item,'ERR',str(e)[:60],[],[])
    body=txt(d.get('content',''))
    qs=[q['label'] for q in d.get('questions',[]) if q.get('required') and q['fields'][0]['name'] not in ('first_name','last_name','email','phone','resume','cover_letter')]
    flags=[]
    for nm,p in (('SCHED',SCHED),('YRS',YRS),('RESID',RESID)):
        m=p.search(body)
        if m: flags.append(f"{nm}:{body[max(0,m.start()-90):m.start()+110]}".replace('\n',' '))
    for q in qs:
        if BADQ.search(q): flags.append(f"BADQ:{q[:110]}")
    return (item,'CLEAN' if not flags else 'FLAG',url,flags,qs)
out=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
    for r in ex.map(jd,res):
        if r: out.append(r)
json.dump([[list(a),b,c,d,e] for a,b,c,d,e in out],open('/tmp/sweep5_tri.json','w'),indent=1)
print("\n########## CLEAN ##########")
for item,st,url,flags,qs in out:
    if st=='CLEAN':
        print(f"{item[5]} | {item[1]} | {item[3][:60]} | {item[4][:34]} | {url}")
        print(f"    REQ-Q: {' || '.join(q[:70] for q in qs) or '(none)'}")
print("\n########## FLAGGED ##########")
for item,st,url,flags,qs in out:
    if st!='CLEAN':
        print(f"{item[5]} | {item[1]} | {item[3][:55]} | {item[4][:30]} | {url}")
        for f in flags: print("      -",f[:190])
