"""Export actual indexed rows for ChatGPT Sites; never create example content."""
import sqlite3, json, pathlib, datetime, gzip, hashlib
c=sqlite3.connect('whoa.db');c.row_factory=sqlite3.Row
out=pathlib.Path('site');out.mkdir(exist_ok=True)
records=[dict(r) for r in c.execute('select url,title,category,body as full_text,fetched from pages order by url')]
coverage={'indexed_pages':len(records),'visited_urls':c.execute('select count(*) from visited').fetchone()[0],
 'queued_urls':c.execute('select count(*) from pending').fetchone()[0],
 'failed_urls':c.execute('select count(*) from failures').fetchone()[0],
 'forum_total_known':False,'percent_complete':None,'verified_complete':False}
status=dict(c.execute('select key,value from crawl_status'))
data={'schema_version':1,'source':'https://github.com/Jtensetti/whoa','refreshed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'coverage':coverage,'crawl_status':status,'records':records}
(out/'index.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
(out/'stats.json').write_text(json.dumps({k:v for k,v in data.items() if k!='records'},ensure_ascii=False),encoding='utf-8')
samples=pathlib.Path('diagnostics');samples.mkdir(exist_ok=True)
for row in c.execute('select * from raw_pages limit 10'):
 name=hashlib.sha256(row['url'].encode()).hexdigest()[:12]
 (samples/(name+'.html')).write_bytes(gzip.decompress(row['html_gz']))
 (samples/(name+'.url')).write_text(row['url'])
print(json.dumps(coverage))
