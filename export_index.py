"""Validate the actual export and include raw samples for parser auditing."""
import gzip,hashlib,json,pathlib,sqlite3
stats=json.loads(pathlib.Path('dist/stats.json').read_text())
assert stats['schema_version']==2
c=sqlite3.connect('file:whoa.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
samples=pathlib.Path('diagnostics');samples.mkdir(exist_ok=True)
for row in c.execute('select * from raw_pages limit 10'):
    name=hashlib.sha256(row['url'].encode()).hexdigest()[:12]
    (samples/(name+'.html')).write_bytes(gzip.decompress(row['html_gz']))
    (samples/(name+'.url')).write_text(row['url'])
print('Exported real records:',stats['coverage']['indexed_posts'])
