"""Build a real, post-level search corpus from the resumable Whoa checkpoint."""
import datetime,gzip,hashlib,html,json,os,pathlib,shutil,sqlite3
from urllib.parse import urlsplit
from whoa_parser import extract_thread,THREAD
ROOT=pathlib.Path(__file__).resolve().parent
DB=pathlib.Path(os.environ.get('WHOA_DB','whoa.db'))
OUT=pathlib.Path(os.environ.get('WHOA_SITE','dist'))
if not DB.exists():raise SystemExit('Crawl database missing: refusing to manufacture an empty archive')
c=sqlite3.connect(f'file:{DB.resolve()}?mode=ro',uri=True);c.row_factory=sqlite3.Row
rows=c.execute('select * from raw_pages').fetchall()
rows.sort(key=lambda r:(urlsplit(r['url']).path.rsplit('/',2)[-2],int(THREAD.fullmatch(urlsplit(r['url']).path)[4]) if THREAD.fullmatch(urlsplit(r['url']).path) else 0))
posts={};indexed_pages=[];parse_failures=[]
for row in rows:
    if not THREAD.fullmatch(urlsplit(row['url']).path):continue
    data=extract_thread(gzip.decompress(row['html_gz']).decode('utf-8'),row['url'])
    if not data or not data['posts'] or not data['title']:
        parse_failures.append(row['url']);continue
    indexed_pages.append({'url':row['url'],'fetched':row['fetched'],'source_sha256':data['source_sha256'],'posts_on_page':len(data['posts'])})
    for post in data['posts']:
        post['fetched']=row['fetched']
        posts.setdefault(post['id'],post)
if OUT.resolve()==ROOT.resolve():raise SystemExit('Output must be a generated subdirectory')
OUT.mkdir(parents=True,exist_ok=True)
for name in ['thread','post','pagefind']:
    shutil.rmtree(OUT/name,ignore_errors=True)
(OUT/'index.json').unlink(missing_ok=True)
for asset in (ROOT/'web').iterdir():
    if asset.is_file():shutil.copy2(asset,OUT/asset.name)
e=lambda value:html.escape(str(value),quote=True)
for p in posts.values():
    slug=hashlib.sha256(p['id'].encode()).hexdigest()[:24]
    path=OUT/'post'/slug/'index.html';path.parent.mkdir(parents=True,exist_ok=True)
    meta=''.join(f'<meta data-pagefind-meta="{key}[content]" content="{e(value)}">' for key,value in {'title':p['title'],'original_url':p['url'],'category':p['category'],'author':p['author'] or 'Okänd skribent','date':p['date'] or ''}.items())
    filters=''.join(f'<meta data-pagefind-filter="{key}[content]" content="{e(value)}">' for key,value in {'category':p['category'],'author':p['author'],'year':p['year']}.items() if value is not None)
    page=f'<!doctype html><html lang="sv"><head><meta charset="utf-8"><title>{e(p["title"])}</title>{meta}{filters}</head><body><article data-pagefind-body><h1 data-pagefind-weight="0.2">{e(p["title"])}</h1><div>{e(p["body"])}</div></article><a href="{e(p["url"])}">Original på Whoa.nu</a></body></html>'
    path.write_text(page,encoding='utf-8')
count=lambda table:c.execute('select count(*) from '+table).fetchone()[0]
coverage={'indexed_pages':len(indexed_pages),'indexed_posts':len(posts),'indexed_threads':len({p['thread_id'] for p in posts.values()}),
 'visited_urls':count('visited'),'queued_urls':count('pending'),'failed_urls':count('failures'),'parse_failures':len(parse_failures),
 'missing_author':sum(p['author'] is None for p in posts.values()),'missing_year':sum(p['year'] is None for p in posts.values()),
 'forum_total_known':False,'percent_complete':None,'verified_complete':False}
status=dict(c.execute('select key,value from crawl_status'))
stats={'schema_version':2,'source':'https://github.com/Jtensetti/whoa','source_commit':os.getenv('GITHUB_SHA','local-rebuild'),
 'run_url':f'https://github.com/Jtensetti/whoa/actions/runs/{os.environ["GITHUB_RUN_ID"]}' if 'GITHUB_RUN_ID' in os.environ else None,
 'refreshed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'collected_until':max((p['fetched'] for p in posts.values()),default=None),
 'coverage':coverage,'crawl_status':status,'parse_failures':parse_failures}
(OUT/'stats.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'provenance.json').write_text(json.dumps(indexed_pages,ensure_ascii=False,indent=2),encoding='utf-8')
with gzip.open(OUT/'posts.jsonl.gz','wt',encoding='utf-8') as f:
    for p in posts.values():f.write(json.dumps(p,ensure_ascii=False)+'\n')
print(json.dumps(coverage,ensure_ascii=False))
