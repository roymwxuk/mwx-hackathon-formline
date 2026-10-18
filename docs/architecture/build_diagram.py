"""Draw docs/architecture/architecture.svg (1920x1080, the viewer's dark palette).

Run: python3 docs/architecture/build_diagram.py
PNG for the video and pitch: open the SVG in a browser at 1920x1080 and screenshot it, e.g.
  chrome --headless=new --window-size=1920,1080 --screenshot=architecture.png architecture.svg
"""
from pathlib import Path
from html import escape
W,H=1920,1080
BG='#0d1117'; PANEL='#161b22'; BORDER='#30363d'; TEXT='#e6edf3'; MUTED='#8b949e'
GOLD='#f2a93b'; GREEN='#3fb27f'; PURPLE='#a78bfa'; BLUE='#4aa3ff'
out=[]
def rect(x,y,w,h,stroke=BORDER,fill=PANEL,r=12,dash=None,sw=1.5):
    d=f' stroke-dasharray="{dash}"' if dash else ''
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')
def text(x,y,s,size=16,color=TEXT,weight=400,anchor='start',mono=False):
    fam='ui-monospace, SFMono-Regular, Menlo, Consolas, monospace' if mono else 'Inter, Segoe UI, Helvetica Neue, Arial, sans-serif'
    out.append(f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}" xml:space="preserve">{escape(s)}</text>')
def lines(x,y,items,size=15,gap=22,color=TEXT):
    for i,s in enumerate(items):
        if isinstance(s,tuple): s,c=s
        else: c=color
        text(x,y+i*gap,s,size,c)
def arrow(pts,color=MUTED,dash=None,sw=2,marker='arr'):
    d=f' stroke-dasharray="{dash}"' if dash else ''
    p=' '.join(f'{a},{b}' for a,b in pts)
    out.append(f'<polyline points="{p}" fill="none" stroke="{color}" stroke-width="{sw}"{d} marker-end="url(#{marker}-{color[1:]})"/>')
def chip(x,y,label,color):
    w=len(label)*7.6+20
    rect(x,y,w,24,stroke=color,fill=BG,r=12,sw=1.2); text(x+w/2,y+17,label,12.5,color,600,'middle')
    return w
def box(x,y,w,h,title,color,items,tag=None,size=15):
    rect(x,y,w,h,stroke=color)
    out.append(f'<rect x="{x}" y="{y}" width="6" height="{h}" rx="3" fill="{color}"/>')
    text(x+20,y+30,title,18,TEXT,700)
    if tag: chip(x+w-len(tag)*7.6-34,y+12,tag,color)
    lines(x+20,y+58,items,size)

# title
text(40,58,'Formline: architecture',34,TEXT,800)
text(430,58,'a synthetic match feed becomes explainable, personalized overlays, live',20,MUTED)

# Azure environment
rect(30,92,1480,776,stroke=BLUE,fill='none',r=18,dash='8 6',sw=1.8)
text(54,122,'Azure Container Apps environment',18,BLUE,700)
text(366,122,'· Japan East · consumption plan · min 0 replicas (scale to zero)',16,MUTED)

# backend app
rect(54,140,1086,712,stroke=BORDER,fill='#10151c',r=14)
text(76,172,'formline-api',20,TEXT,700); text(212,172,'Python · FastAPI · Microsoft Agent Framework · 0.5 vCPU',15,MUTED)

box(76,192,330,262,'a · Ingest',GREEN,[
 'Synthetic match feed (seeded)',
 'Chaos injector: duplicates, late,',
 '  out-of-order and corrected events',
 'Append-only event log',
 '  idempotent on event_id',
 '  reorder window + idle timeout',
 'Synthetic tracking, 10 Hz:',
 '  22 players + ball, from events',
 ('Pass, shot, tackle, VAR... events',MUTED),
])
box(426,192,340,262,'b · Interpret',GREEN,[
 'Shot features: speed, xG,',
 '  placement, pressure',
 "Personal baseline per player",
 '  like-for-like: zone, body part,',
 '  pressure, wider buckets if thin',
 'Empirical Bayes shrinkage',
 'Incremental; rebuilt from the log',
],tag='no LLM')
box(786,192,334,262,'c · Insight detectors',GREEN,[
 "Shot vs the shooter's own norm",
 '  speed, placement, finish quality',
 'Salience score per insight',
 'Lineage: source_event_ids',
 'Corrections (VAR overturn):',
 '  roll back the baseline,',
 '  re-issue the insight',
],tag='no LLM')
arrow([(406,323),(422,323)],GREEN); arrow([(766,323),(782,323)],GREEN)

# agent workflow
rect(76,476,814,358,stroke=PURPLE,fill=PANEL,r=12)
out.append(f'<rect x="76" y="476" width="6" height="358" rx="3" fill="{PURPLE}"/>')
text(96,506,'c · Explain: multi-agent workflow',18,TEXT,700)
text(96,530,'Microsoft Agent Framework WorkflowBuilder · shared state · explicit handoffs',14.5,MUTED)
arrow([(953,454),(953,468),(483,468),(483,476)],GREEN)  # insights -> workflow (enter top)
def node(x,y,w,h,title,sub,color):
    rect(x,y,w,h,stroke=color,fill=BG,r=10)
    text(x+w/2,y+24,title,15.5,TEXT,700,'middle')
    if sub: text(x+w/2,y+44,sub,12.5,MUTED,400,'middle')
node(96,600,150,64,'Insight Selector','rules + LLM pick',PURPLE)
for i,(l,m) in enumerate([('EN','casual'),('EN','analyst'),('JA','casual'),('JA','analyst')]):
    yc=582+i*50
    node(282,yc-20,172,40,f'Narrator {l} · {m}',None,PURPLE)
    arrow([(246,632),(276,yc)],PURPLE,sw=1.6)
    arrow([(454,yc),(484,632)],PURPLE,sw=1.6)
node(490,600,176,64,'Verifier','numbers · names · wording',GREEN)
node(706,600,168,64,'Overlay Composer','template catalog',GREEN)
node(490,730,176,56,'Template fallback','after 3 failures',GREEN)
arrow([(666,632),(700,632)],GREEN); text(683,624,'ok',12.5,GREEN,600,'middle')
arrow([(578,600),(578,548),(368,548),(368,556)],GOLD,dash='5 4'); text(586,578,'retry with feedback',12.5,GOLD,600)
arrow([(578,664),(578,724)],GOLD,dash='5 4'); text(586,700,'give up',12.5,GOLD,600)
arrow([(666,758),(790,758),(790,670)],GREEN)
lines(690,774,[('Bad JSON, timeouts → retry',MUTED),('A card is never blocked,',MUTED),('and never wrong',MUTED)],13.5,19)

# render
box(910,476,210,186,'d · Render',GREEN,[
 'Overlay contract (JSON)',
 '  source_event_ids',
 'SSE stream, resumable',
 '  + tracking frames 4/s',
 '  + Analyst comments',
],size=14)
arrow([(874,632),(904,632)],GREEN)

# Match Analyst (phase 1 comments, phase 2 follow-up questions)
box(910,676,210,158,'Match Analyst',PURPLE,[
 'Comments after shots,',
 '  corners, cards, VAR',
 'Suggester: 2 of 4 questions',
 'Researcher: tools, chains',
 '/ask · own verifier',
],size=13)
arrow([(1015,676),(1015,668)],PURPLE)

# web app
rect(1160,140,330,712,stroke=BORDER,fill='#10151c',r=14)
text(1180,172,'formline-web',20,TEXT,700); text(1318,172,'Next.js · 0.25 vCPU',15,MUTED)
box(1180,192,290,642,'e · Personalize',GOLD,[
 '2D pitch: 22 tracked players',
 '  and the ball',
 'Timed overlay cards',
 '',
 ('Viewer settings',MUTED),
 'Language: EN / JA',
 'Casual / Analyst (density)',
 'Favorite clubs, players',
 '  → card priority',
 'Player focus strip',
 '  vs his own baseline',
 '"My metric" filter',
 '',
 ('Views',MUTED),
 'Live viewer',
 'Two viewers side by side',
 '',
 'Speed · slow-mo · jump to moment',
 'GOAL! · set-piece labels',
 'VAR correction banner',
 '',
 ('Match analyst panel',MUTED),
 'Comments + follow-up chips',
 '  → POST /ask, verified answer',
],size=15)
arrow([(1120,600),(1174,600)],GOLD,sw=2.5); text(1147,590,'SSE',12.5,GOLD,700,'middle')
arrow([(1174,780),(1126,780)],GOLD,sw=2); text(1150,770,'/ask',12.5,GOLD,700,'middle')

# viewers
rect(1540,92,350,360,stroke=GOLD,fill=PANEL,r=14)
text(1560,124,'Viewers (browser)',18,TEXT,700)
text(1560,148,'same moment, different insights',14.5,MUTED)
for i,(t,a,b) in enumerate([('Viewer A','日本語 · casual','favorite player'),('Viewer B','English · analyst','my metric: shot speed')]):
    y=168+i*136
    rect(1560,y,310,118,stroke=BORDER,fill=BG,r=10)
    text(1578,y+30,t,16,GOLD,700); text(1578,y+58,a,15,TEXT); text(1578,y+84,b,15,TEXT)
    text(1578,y+106,'fewer, simpler cards' if i==0 else 'every insight, full numbers',13,MUTED)
arrow([(1490,300),(1534,300)],GOLD,sw=2.5)

# Log Analytics
box(1540,474,350,130,'Log Analytics',BLUE,[
 'Container logs',
 'Console output of both apps',
])
arrow([(1490,540),(1534,540)],BLUE,dash='5 4')

# Legend
rect(1540,626,350,226,stroke=BORDER,fill=PANEL,r=14)
text(1560,658,'Legend',18,TEXT,700)
for i,(c,l) in enumerate([(GREEN,'Deterministic (no LLM)'),(PURPLE,'LLM agent (Foundry model)'),(GOLD,'Viewer, personalization'),(BLUE,'Azure service')]):
    y=690+i*36
    out.append(f'<rect x="1560" y="{y-14}" width="18" height="18" rx="4" fill="{c}"/>'); text(1590,y,l,15)
out.append(f'<line x1="1560" y1="830" x2="1590" y2="830" stroke="{GOLD}" stroke-width="2" stroke-dasharray="5 4"/>'); text(1600,835,'Recovery path',15)

# Foundry (bottom)
rect(76,900,560,150,stroke=BLUE,fill=PANEL,r=14)
out.append(f'<rect x="76" y="900" width="6" height="150" rx="3" fill="{BLUE}"/>')
text(96,932,'Microsoft Foundry',20,TEXT,700); chip(470,914,'gpt-4.1-mini',BLUE)
lines(96,962,['Project with a Global Standard deployment',
 'Entra ID managed identity, role "Foundry User": no keys',
 ('Response cache · call budget · demo text precomputed',MUTED)],15,24)
arrow([(171,664),(171,894)],BLUE,dash='5 4')
arrow([(368,752),(368,894)],BLUE,dash='5 4')
arrow([(940,834),(940,884),(600,884),(600,894)],BLUE,dash='5 4')
text(380,889,'model calls (managed identity)',13,BLUE,600)

# CI/CD (bottom)
rect(670,900,830,150,stroke=BORDER,fill=PANEL,r=14)
text(690,932,'Delivery',20,TEXT,700)
for i,(t,s) in enumerate([('GitHub Actions','lint · typecheck · tests'),('GHCR','amd64 images, tagged by SHA'),('deploy.sh','az containerapp update')]):
    x=690+i*270
    rect(x,950,240,80,stroke=BORDER,fill=BG,r=10)
    text(x+120,982,t,16,TEXT,700,'middle'); text(x+120,1008,s,13.5,MUTED,400,'middle')
    if i<2: arrow([(x+240,990),(x+264,990)],MUTED)
arrow([(1080,950),(1080,872)],BLUE,dash='5 4'); text(1090,890,'pull image',13,BLUE,600)

# Budget
rect(1540,900,350,150,stroke=BORDER,fill=PANEL,r=14)
text(1560,932,'Cost controls',20,TEXT,700)
lines(1560,962,['Scale to zero; ingress off when idle','Budget ¥3,000/month, alerts 50/100%',('~¥70–90 in model tokens so far (est.)',MUTED)],15,24)

colors={MUTED,GREEN,PURPLE,GOLD,BLUE}
markers=''.join(f'<marker id="arr-{c[1:]}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>' for c in colors)
svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="Formline architecture"><title>Formline architecture</title><defs>{markers}</defs><rect width="{W}" height="{H}" fill="{BG}"/>'+'\n'.join(out)+'</svg>\n'
(Path(__file__).parent / 'architecture.svg').write_text(svg)
