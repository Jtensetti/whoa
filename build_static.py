"""Build a static, searchable Whoa archive from the crawler's SQLite data."""
import json, os, sqlite3, html, hashlib, pathlib, re

DB=os.environ.get("WHOA_DB","whoa.db")
OUT=pathlib.Path(os.environ.get("WHOА_SITE","site"))
OUT.mkdir(parents=True,exist_ok=True)

STYLE="""body{background:#121319;color:#f0eee9;font:16px system-ui,Arial;margin:0}
main{max-width:850px;margin:7vh auto;padding:24px}
h1{letter-spacing:-2px;font-size:clamp(38px,7vw,66px);margin:0}
em{color:#eab557;font-style:normal}
p,.meta{color:#aab0ba;line-height:1.5}
a{color:#eab557;text-decoration:none}a:hover{text-decoration:underline}
article{border-top:1px solid #393c45;padding:20px 0;white-space:pre-wrap;line-height:1.6}
label{display:block;margin:24px 0 10px}
input{font-size:18px;border-radius:8px;padding:13px;background:#262833;border:1px solid #51535f;color:white;width:100%;box-sizing:border-box}
small{color:#aab0ba} .pagefind-ui{--pagefind-ui-primary:#eab557;--pagefind-ui-text:#f4f1eb;--pagefind-ui-background:#20222a;--pagefind-ui-border:#484b55;--pagefind-ui-tag:#30323b}
"""

def write(path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(body,encoding="utf-8")

def shell(title, body, extra=""):
    return ('<!doctype html><html lang="sv"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>'+html.escape(title)+'</title>'
            '<style>'+STYLE+'</style>'+extra+'<main>'+body+'</main></html>')

if os.path.exists(DB):
    connection=sqlite3.connect(DB)
    rows=connection.execute("select url,title,category,body,fetched from pages order by url").fetchall()
    fetched=connection.execute("select count(*) from visited").fetchone()[0]
    pending=connection.execute("select count(*) from pending").fetchone()[0]
    failed=connection.execute("select count(*) from failures").fetchone()[0]
    connection.close()
else:
    rows=[]; fetched=pending=failed=0

for url,title,category,body,date in rows:
    slug=hashlib.sha256(url.encode()).hexdigest()[:20]
    dest=OUT/"thread"/slug/"index.html"
    safe_title=html.escape(title)
    # Search is generated from the extracted forum text, but the source URL
    # is always available and no content is asserted to be complete.
    page=('<div class="meta">'+html.escape(category)+'</div>'
          '<h1>'+safe_title+'</h1>'
          '<p><a href="'+html.escape(url,quote=True)+'" rel="noopener noreferrer">Läs originaltråden på Whoa.nu ↗</a></p>'
          '<article data-pagefind-body><h2>'+safe_title+'</h2>'
          +html.escape(body)+'</article>'
          '<p><a href="../../">Tillbaka till sökningen</a></p>')
    write(dest,shell(title,page,
        '<meta data-pagefind-meta="title[content]" content="'+html.escape(title,quote=True)+'">'))

intro=('<div class="meta">ETT OBEROENDE FORSKNINGSINDEX</div>'
       '<h1>whoa<em>.</em>search</h1>'
       '<p>Fulltextsökning i de forumsidor som har samlats in från Whoa.nu. '
       'Projektet har ingen koppling till Whoa. Träffarna kan vara ofullständiga.</p>'
       '<p class="meta"><strong>'+format(len(rows),",").replace(","," ")+'</strong> indexerade trådsidor · '
       +str(fetched)+' besökta adresser · '+str(pending)+' kvar i kön · '+str(failed)+' fel</p>'
       '<div id="search"></div>'
       '<p class="meta">Sök gärna efter våldsironi, vålds-ironi, D6AA eller MBMA. '
       'Inga träffar betyder inte att ordet saknas på originalforumet.</p>')
js=('<link href="./pagefind/pagefind-ui.css" rel="stylesheet">'
    '<script src="./pagefind/pagefind-ui.js"></script>'
    '<script>window.addEventListener("DOMContentLoaded",()=>{'
    'if(window.PagefindUI)new PagefindUI({element:"#search",showSubResults:true,'
    'showImages:false,translations:{placeholder:"Sök i Whoas forum..."}});'
    'else document.querySelector("#search").textContent="Sökindexet har ännu inte byggts.";'
    '});</script>')
write(OUT/"index.html",shell("Whoa Search",intro,js))
write(OUT/"stats.json",json.dumps({"indexed_pages":len(rows),"visited":fetched,"pending":pending,"failures":failed},ensure_ascii=False))
print(f"Generated {len(rows)} thread pages in {OUT}")
