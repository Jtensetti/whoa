import os,re,time,sqlite3,threading,logging,datetime,gzip,json,hashlib
from urllib.parse import urljoin,urlsplit,parse_qs,urlunsplit
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup
from whoa_parser import extract_thread
from fastapi import FastAPI,Query
from fastapi.responses import HTMLResponse

ROOT="https://www.whoa.nu"
ROOT_PATH="/community/Forums.aspx"
DB=os.getenv("WHOA_DB","whoa.db")
CONTACT=os.getenv("CONTACT_URL","https://github.com/Jtensetti/whoa")
DELAY=max(2.0,float(os.getenv("CRAWL_DELAY","3")))
BATCH=int(os.getenv("CRAWL_BATCH","1000000"))
SECONDS=int(os.getenv("CRAWL_SECONDS","2700"))
UA="WhoaArchiveResearch/1.0 (+%s)"%CONTACT
LOG=logging.getLogger("whoa")
logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
THREAD=re.compile(r"^/forum/[^/?#]+/[^/?#]+/[0-9]+/[0-9]+\.aspx$",re.I)
CATEGORY=re.compile(r"^/forum/[^/?#]+/[^/?#]+(?:/[0-9]+)?\.aspx$",re.I)
SPECIAL=re.compile(r"^/forum/(?:popular|latest|active)\.aspx$",re.I)
app=FastAPI(title="Whoa Archive")
state={"running":False,"last_error":None,"robots":None,"last_run":None}

def db():
    os.makedirs(os.path.dirname(os.path.abspath(DB)),exist_ok=True)
    c=sqlite3.connect(DB,timeout=30,check_same_thread=False)
    c.execute("pragma journal_mode=WAL")
    c.execute("pragma busy_timeout=30000")
    c.executescript("""
    CREATE TABLE IF NOT EXISTS pages(
      url TEXT PRIMARY KEY,title TEXT NOT NULL,category TEXT NOT NULL DEFAULT '',
      body TEXT NOT NULL, fetched TEXT NOT NULL);
    CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(title,body,category,
      content='pages',content_rowid='rowid',tokenize='unicode61 remove_diacritics 2');
    CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
      INSERT INTO pages_fts(rowid,title,body,category) VALUES(new.rowid,new.title,new.body,new.category);
    END;
    CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
      INSERT INTO pages_fts(pages_fts,rowid,title,body,category)
      VALUES('delete',old.rowid,old.title,old.body,old.category);
    END;
    CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
      INSERT INTO pages_fts(pages_fts,rowid,title,body,category)
      VALUES('delete',old.rowid,old.title,old.body,old.category);
      INSERT INTO pages_fts(rowid,title,body,category) VALUES(new.rowid,new.title,new.body,new.category);
    END;
    CREATE TABLE IF NOT EXISTS visited(url TEXT PRIMARY KEY,code INTEGER,checked TEXT);
    CREATE TABLE IF NOT EXISTS pending(url TEXT PRIMARY KEY,priority INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS failures(url TEXT PRIMARY KEY,reason TEXT,attempts INTEGER DEFAULT 1);
    """)
    c.execute("CREATE TABLE IF NOT EXISTS raw_pages(url TEXT PRIMARY KEY, html_gz BLOB, fetched TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS crawl_status(key TEXT PRIMARY KEY,value TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS category_inventory(url TEXT PRIMARY KEY,listing_pages INTEGER NOT NULL DEFAULT 0,checked_at TEXT)")
    c.execute("CREATE INDEX IF NOT EXISTS pending_priority ON pending(priority)")
    c.commit()
    return c

def canonical(href,base):
    u=urlsplit(urljoin(base,href))
    if u.scheme not in ("https","http") or u.hostname not in ("whoa.nu","www.whoa.nu"):
        return None
    path=u.path
    if path.lower()==ROOT_PATH.lower():
        return ROOT+ROOT_PATH
    if not (THREAD.fullmatch(path) or CATEGORY.fullmatch(path) or SPECIAL.fullmatch(path)):
        return None
    params=parse_qs(u.query)
    page=(params.get("page") or params.get("Page") or [None])[0]
    if page and page.isdigit() and 1<int(page)<100000:
        return ROOT+path+"?page="+str(int(page))
    return ROOT+path

def parse_page(html,url):
    soup=BeautifulSoup(html,"html.parser")
    h=soup.find("h1")
    title=h.get_text(" ",strip=True) if h else (soup.title.get_text(" ",strip=True) if soup.title else url)
    category=urlsplit(url).path.split("/")[2:4]
    category=" / ".join(category)
    main=None
    for selector in ("#content","#main",".forum-thread","main","[role=main]"):
        node=soup.select_one(selector)
        if node and len(node.get_text(" ",strip=True))>120:main=node;break
    if main is None:main=soup.body or soup
    # Parse the original document's links BEFORE modifying its DOM.
    links=[canonical(a.get("href",""),url) for a in soup.select("a[href]")]
    for item in main.select("script,style,nav,header,footer,noscript,svg,iframe,.sidebar,.menu,.navigation,.breadcrumb,.pagination"):
        item.decompose()
    body=re.sub(r"\n{3,}","\n\n",main.get_text("\n",strip=True))
    if THREAD.fullmatch(urlsplit(url).path):
        parsed=extract_thread(html,url)
        title=parsed['title'];category=parsed['category']
        body='\n\n'.join(p['body'] for p in parsed['posts'])
    return title,category,body,{v for v in links if v}

def enqueue(c,url):
    if c.execute("select 1 from visited where url=?",(url,)).fetchone():return
    u=urlsplit(url)
    priority=100 if u.path==ROOT_PATH else (20 if THREAD.fullmatch(u.path) else (30 if CATEGORY.fullmatch(u.path) and not u.query else 10))
    c.execute("insert or ignore into pending(url,priority) values (?,?)",(url,priority))

def inventory_links(c,url,links,stamp):
    """Expand only pagination bounded by page links actually observed in the source."""
    current=urlsplit(url)
    same_pages=[1]
    for link in links:
        part=urlsplit(link)
        if CATEGORY.fullmatch(part.path) and not part.query:
            c.execute("insert or ignore into category_inventory(url) values (?)",(ROOT+part.path,))
        if part.path==current.path and CATEGORY.fullmatch(current.path):
            value=parse_qs(part.query).get('page',['1'])[0]
            if value.isdigit():same_pages.append(int(value))
    if CATEGORY.fullmatch(current.path):
        last=max(same_pages)
        base=ROOT+current.path
        c.execute("insert into category_inventory values (?,?,?) on conflict(url) do update set listing_pages=max(listing_pages,excluded.listing_pages),checked_at=excluded.checked_at",(base,last,stamp))
        # Page-major insertion visits every category before moving deeper into its history.
        for page in range(2,last+1):links.add(base+'?page='+str(page))
    if THREAD.fullmatch(current.path):
        stem=current.path.rsplit('/',1)[0]
        last=max([int(current.path.rsplit('/',1)[1].split('.')[0])]+[int(urlsplit(link).path.rsplit('/',1)[1].split('.')[0]) for link in links if THREAD.fullmatch(urlsplit(link).path) and urlsplit(link).path.rsplit('/',1)[0]==stem])
        for page in range(1,last+1):links.add(ROOT+stem+'/'+str(page)+'.aspx')
    for link in sorted(links):enqueue(c,link)

def prepare_frontier(c):
    enqueue(c,ROOT+ROOT_PATH)
    version=c.execute("select value from crawl_status where key='frontier_schema'").fetchone()
    if not version or version[0]!='2':
        # Upgrade the existing checkpoint without re-fetching already collected pages.
        old=list(c.execute('select url,html_gz,fetched from raw_pages'))
        for url,raw,stamp in old:
            soup=BeautifulSoup(gzip.decompress(raw),'html.parser')
            links={canonical(a['href'],url) for a in soup.select('a[href]')};links.discard(None)
            inventory_links(c,url,links,stamp)
        pending=[r[0] for r in c.execute('select url from pending')]
        c.execute('delete from pending')
        # Interleave list pages across all categories; threads retain discovery order.
        pending.sort(key=lambda url:(0,int(parse_qs(urlsplit(url).query).get('page',['1'])[0]),url) if CATEGORY.fullmatch(urlsplit(url).path) else (1,0,''))
        for url in pending:enqueue(c,url)
        c.execute("insert or replace into crawl_status values ('frontier_schema','2')")
    c.commit()

def can_crawl(session):
    response=session.get(ROOT+"/robots.txt",timeout=20)
    if response.status_code not in (200,404):
        raise RuntimeError("robots.txt HTTP %s; crawl blocked"%response.status_code)
    parser=RobotFileParser()
    parser.parse(response.text.splitlines() if response.status_code==200 else [])
    if not parser.can_fetch(UA,ROOT+ROOT_PATH):
        raise RuntimeError("robots.txt disallows forum index")
    return parser

def crawl_batch():
    c=db()
    s=requests.Session()
    s.headers.update({"User-Agent":UA,"Accept-Language":"sv,en;q=0.7"})
    try:
        robots=can_crawl(s)
        state["robots"]="allowed"
        delay=max(DELAY,robots.crawl_delay(UA) or robots.crawl_delay("*") or 0)
        c.execute("insert or replace into crawl_status values ('last_error','')")
        prepare_frontier(c)
        started=time.monotonic()
        for i in range(BATCH):
            if time.monotonic()-started>=SECONDS:break
            # Alternate listing discovery with full-text collection, without topic priorities.
            row=c.execute("select url from pending where priority>=30 order by priority desc,rowid limit 1").fetchone()
            if not row:
                preferred=10 if i%2==0 else 20
                row=c.execute("select url from pending where priority=? order by rowid limit 1",(preferred,)).fetchone()
            if not row:row=c.execute("select url from pending order by rowid limit 1").fetchone()
            if not row:break
            url=row[0]
            if not robots.can_fetch(UA,url):
                c.execute("delete from pending where url=?",(url,))
                c.execute("insert or replace into failures(url,reason,attempts) values (?,'robots.txt blocked',1)",(url,))
                c.commit()
                continue
            try:
                r=s.get(url,timeout=30)
            except requests.RequestException as exc:
                raise RuntimeError("network issue at %s: %s"%(url,exc))
            if r.status_code in (429,500,502,503,504):
                raise RuntimeError("temporary upstream HTTP %s; preserving queue"%r.status_code)
            stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
            if r.status_code==200 and "html" in r.headers.get("content-type","").lower():
                r.encoding=r.apparent_encoding if not r.encoding or r.encoding.lower()=="iso-8859-1" else r.encoding
                c.execute("insert or replace into raw_pages values (?,?,?)",(url,gzip.compress(r.text.encode("utf-8")),stamp))
                title,category,body,links=parse_page(r.text,url)
                if THREAD.fullmatch(urlsplit(url).path) and len(body)>20:
                    c.execute("""insert into pages(url,title,category,body,fetched) values (?,?,?,?,?)
                    on conflict(url) do update set title=excluded.title,category=excluded.category,
                    body=excluded.body,fetched=excluded.fetched""",(url,title,category,body,stamp))
                elif THREAD.fullmatch(urlsplit(url).path):
                    c.execute("insert or replace into failures values (?, 'No extractable forum posts', 1)",(url,))
                inventory_links(c,url,links,stamp)
            elif r.status_code!=200:
                c.execute("insert or replace into failures(url,reason,attempts) values (?,?,1)",(url,"HTTP %s"%r.status_code))
            c.execute("insert or replace into visited values (?,?,?)",(url,r.status_code,stamp))
            c.execute("delete from pending where url=?",(url,))
            c.commit()
            if i%25==0:LOG.info("fetched=%s indexed=%s queued=%s",i,*c.execute("select count(*) from pages").fetchone(),*c.execute("select count(*) from pending").fetchone())
            time.sleep(delay)
    except Exception as exc:
        c.execute("insert or replace into crawl_status values ('last_error',?)",(str(exc),))
        c.commit()
        raise
    finally:
        c.execute("insert or replace into crawl_status values ('last_run',?)",(datetime.datetime.now(datetime.timezone.utc).isoformat(),))
        c.commit()
        c.close()

def worker():
    while True:
        state["running"]=True
        try:
            crawl_batch()
            state["last_error"]=None
        except Exception as exc:
            state["last_error"]=str(exc)
            state["robots"]="error" if "robots" in str(exc).lower() else state["robots"]
            LOG.exception("Crawl paused: %s",exc)
        finally:
            state["last_run"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
            state["running"]=False
        time.sleep(3600 if state["last_error"] else 30)

@app.on_event("startup")
def start():
    with db():pass
    if os.getenv("CRAWL_ENABLED","1")=="1":
        threading.Thread(target=worker,daemon=True).start()

@app.get("/api/stats")
def stats():
    with db() as c:
        return {"indexed_pages":c.execute("select count(*) from pages").fetchone()[0],
          "fetched_urls":c.execute("select count(*) from visited").fetchone()[0],
          "queued_urls":c.execute("select count(*) from pending").fetchone()[0],
          "errors":c.execute("select count(*) from failures").fetchone()[0],
          **state}

@app.get("/api/search")
def search(q:str=Query(min_length=1,max_length=200),page:int=Query(default=1,ge=1,le=500)):
    tokens=re.findall(r"[^\s\"*^()]+",q)
    if not tokens:return {"total":0,"results":[]}
    match=" AND ".join('"' + t.replace('"','') + '"' for t in tokens[:12])
    with db() as c:
        c.row_factory=sqlite3.Row
        total=c.execute("select count(*) from pages_fts where pages_fts match ?",(match,)).fetchone()[0]
        rows=c.execute("""select p.url,p.title,p.category,
          snippet(pages_fts,1,'[',']',' … ',30) as excerpt
          from pages_fts join pages p on p.rowid=pages_fts.rowid
          where pages_fts match ? order by bm25(pages_fts,6,1,2)
          limit 20 offset ?""",(match,(page-1)*20)).fetchall()
        return {"total":total,"page":page,"results":[dict(r) for r in rows]}

HTML='''<!doctype html><html lang="sv"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Whoa Archive</title><style>body{font-family:system-ui;background:#111218;color:#f0f0ed;margin:0}main{max-width:860px;margin:7vh auto;padding:24px}h1{font-size:clamp(44px,8vw,75px);letter-spacing:-4px;margin:0}.gold{color:#e4ad4a}p{color:#a9abb4}form{display:flex;gap:9px;margin:32px 0}input{background:#22242c;border:1px solid #474958;border-radius:9px;padding:15px;color:white;flex:1;min-width:0;font-size:16px}button{background:#e4ad4a;border:0;border-radius:9px;padding:15px 22px;font-weight:700;cursor:pointer}article{border-bottom:1px solid #333640;padding:19px 0}a{color:#e6bf7d;text-decoration:none;font-size:19px;font-weight:600}.meta{color:#9ca0af;font-size:12px}.error{color:#ffb4a2}#results p{white-space:pre-line;line-height:1.5;overflow-wrap:anywhere}footer{font-size:12px;color:#888b96;padding:30px 0}</style><main><small class="gold">SVENSK HIPHOP · DIGITALT ARKIV</small><h1>whoa<span class="gold">.</span>search</h1><p>En oberoende fulltextsökning i de forumsidor som faktiskt har indexerats. Allt leder tillbaka till originalet.</p><form id="f"><input id="q" autofocus placeholder="Sök våldsironi, D6AA, ordbajs..." value="våldsironi"><button>Sök</button></form><div id="status" class="meta">Hämtar status...</div><div id="results"></div><footer>Fristående forskningsindex · inte anslutet till Whoa · Indexet kan vara ofullständigt. Inga träffar betyder inte att uttrycket saknas i forumet.</footer></main><script>const f=document.querySelector("#f"),q=document.querySelector("#q"),s=document.querySelector("#status"),out=document.querySelector("#results");function E(t,x){let e=document.createElement(t);if(x)e.textContent=x;return e}async function search(){let term=q.value.trim();if(!term)return;out.replaceChildren();s.textContent="Söker...";try{let [r,st]=await Promise.all([fetch("/api/search?q="+encodeURIComponent(term)),fetch("/api/stats")]);if(!r.ok)throw Error("Sökfel");let d=await r.json(),t=await st.json();s.textContent=d.total+" träffar · "+t.indexed_pages+" indexerade sidor · "+t.queued_urls+" väntar på insamling"+(t.last_error?" · Crawler pausad":"");for(let h of d.results){let a=E("article"),l=E("a",h.title);l.href=h.url;l.target="_blank";l.rel="noopener";a.append(l,E("div",h.category),E("p",h.excerpt));out.append(a)}}catch(e){s.textContent=e.message}}f.onsubmit=e=>{e.preventDefault();search()};search();</script>'''
@app.get("/",response_class=HTMLResponse)
def home():return HTML
