"""Extract only visible Whoa post bodies and adjacent, observed metadata."""
import hashlib,re
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
THREAD=re.compile(r'^/forum/([^/?#]+)/([^/?#]+)/(\d+)/(\d+)\.aspx$',re.I)

def extract_thread(document,url):
    match=THREAD.fullmatch(urlsplit(url).path)
    if not match:return None
    soup=BeautifulSoup(document,'html.parser')
    heading=soup.find('h1')
    title=heading.get_text(' ',strip=True) if heading else ''
    category_path=f'/forum/{match[1]}/{match[2]}.aspx'
    breadcrumb=soup.find('a',href=category_path)
    category=breadcrumb.get_text(' ',strip=True) if breadcrumb else f'{match[1]} / {match[2]}'
    posts=[]
    for ordinal,message in enumerate(soup.select('.forumMessage')):
        row=message.find_parent('tr')
        if row is None:continue
        nick=row.select_one('#forummsg_nick a')
        name=nick.get_text(' ',strip=True) if nick else ''
        name=re.sub(r'\s+[PF]\d{1,3}$','',name).strip()
        author=None if not name or name.casefold()=='borttagen' else name
        date_node=row.select_one('.calendar')
        date_match=re.search(r'\b(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\b',date_node.get_text(' ',strip=True)) if date_node else None
        date=' '.join(date_match.groups()) if date_match else None
        # Hidden message IDs distinguish replies. The opening post repeats on paginated pages.
        id_node=row.find('input',id=re.compile(r'_messageId_\d+$'))
        native_id=id_node.get('value') if id_node else None
        post_id=f'{match[3]}:message:{native_id}' if native_id else (f'{match[3]}:topic' if ordinal==0 else f'{match[3]}:page:{match[4]}:position:{ordinal}')
        td=message.find_parent('td');anchor=td.get('id') if td else None
        for el in message.select('script,style,noscript,iframe,span[id$="_lblSubject"]'):el.decompose()
        for br in message.find_all('br'):br.replace_with('\n')
        body=message.get_text(' ',strip=False)
        body='\n'.join(re.sub(r'[^\S\n]+',' ',line).strip() for line in body.splitlines())
        body=re.sub(r'\n{3,}','\n\n',body).strip()
        if not body:continue
        posts.append({'id':post_id,'thread_id':match[3],'url':url+('#'+anchor if anchor else ''),'page_url':url,
          'title':title,'category':category,'body':body,'author':author,'date':date,'year':int(date[:4]) if date else None})
    return {'url':url,'title':title,'category':category,'posts':posts,'source_sha256':hashlib.sha256(document.encode()).hexdigest()}
