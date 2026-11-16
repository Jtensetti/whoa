const $ = s => document.querySelector(s);
const fmt = n => Number(n || 0).toLocaleString('sv-SE');
const form = $('#search-form'), query = $('#query'), results = $('#results');
const selects = {category:$('#category'), author:$('#author'), year:$('#year')};
const state = {stats:null, engine:null, list:[], page:0, ticket:0, source:'inläst kopia'};
const RAW='https://raw.githubusercontent.com/Jtensetti/whoa/';
const SIZE=20;
function text(id,value){$(id).textContent=value}
function element(tag,cls,value){const e=document.createElement(tag);if(cls)e.className=cls;if(value!==undefined)e.textContent=value;return e}
function originalURL(value){try{const u=new URL(value);return u.protocol==='https:' && ['www.whoa.nu','whoa.nu'].includes(u.hostname) && /^\/forum\//.test(u.pathname) ? u.href : null}catch{return null}}
export function parseQuery(input){
  const quotes=(input.match(/"/g)||[]).length;if(quotes%2)throw Error('Avsluta frasen med ett citattecken.');
  const phrases=[];const loose=input.replace(/"([^"]+)"/g,(_,p)=>{phrases.push(p.trim());return ' '}).trim().replace(/\s+/g,' ');
  return {phrases,loose};
}
export function spellingQueries(loose,enabled=true){
  const out=[loose]; if(!enabled || !loose)return out;
  out.push(loose.normalize('NFD').replace(/[\u0300-\u036f]/g,''));
  const compact=loose.normalize('NFD').replace(/[\u0300-\u036f\s\-‐‑–]/g,'').toLowerCase();
  if(compact==='valdsironi')out.push('våldsironi','"vålds ironi"','vålds-ironi','valdsironi');
  if(/[-‐‑]/.test(loose))out.push(loose.replace(/[-‐‑]/g,''),loose.replace(/[-‐‑]/g,' '));
  return [...new Set(out)];
}
async function fetchJSON(url,ms=6000){const r=await fetch(url,{signal:AbortSignal.timeout(ms),cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);return r.json()}
function empty(title,body){results.replaceChildren();const box=element('div','empty');box.append(element('div','stamp','Whoa Search / arkivet'),element('h2','',title),element('p','',body));results.append(box)}
function updateStats(){
  const c=state.stats.coverage;
  text('#indexed',fmt(c.indexed_pages));text('#posts',fmt(c.indexed_posts));text('#visited',fmt(c.visited_urls));text('#queued',fmt(c.queued_urls));text('#failed',fmt(c.failed_urls));
  text('#remaining','okänd');text('#coverage-line',`${fmt(c.indexed_pages)} trådsidor · täckning ej verifierad`);
  const date=new Date(state.stats.refreshed_at);text('#updated',Number.isNaN(+date)?'Okänt uppdateringsdatum':date.toLocaleString('sv-SE',{dateStyle:'short',timeStyle:'short'}));
  text('#data-source',state.source);
  text('#metadata-note',`${fmt(c.missing_author)} inlägg saknar skribentuppgift. ${fmt(c.missing_year)} saknar år. Filter utesluter inlägg som saknar den valda uppgiften.`);
  text('#inventory-note',c.discovered_categories?`${fmt(c.discovered_categories)} kategorier upptäckta. ${fmt(c.crawled_listing_pages)} av ${fmt(c.known_listing_pages)} kända listsidor har hämtats. Trådarnas totala sidantal är fortfarande okänt.`:'Inventering av kategorier och listsidor pågår.');
  const err=state.stats.crawl_status?.last_error;
  $('#crawl-warning').hidden=!err;if(err)text('#crawl-warning','Senaste insamlingen avbröts: '+err+'. Redan indexerat material går fortfarande att söka.');
}
function fillFilter(key,values){
  const select=selects[key];const first=select.options[0];select.replaceChildren(first);
  const entries=Object.entries(values||{}).sort(([a],[b])=>key==='year'?Number(b)-Number(a):a.localeCompare(b,'sv'));
  for(const [value,count] of entries){const opt=element('option','',`${value} (${fmt(count)})`);opt.value=value;select.append(opt)}
  select.disabled=!entries.length;
}
function safeExcerpt(html){
  const doc=new DOMParser().parseFromString(html||'','text/html');const fragment=document.createDocumentFragment();
  const walk=(node,parent)=>{if(node.nodeType===Node.TEXT_NODE){parent.append(document.createTextNode(node.textContent));return}if(node.nodeType!==Node.ELEMENT_NODE)return;if(node.tagName==='MARK'){const m=document.createElement('mark');parent.append(m);for(const c of node.childNodes)walk(c,m)}else for(const c of node.childNodes)walk(c,parent)};
  for(const n of doc.body.childNodes)walk(n,fragment);return fragment;
}
async function renderPage(ticket){
  const slice=state.list.slice(state.page*SIZE,(state.page+1)*SIZE);
  const data=await Promise.all(slice.map(r=>r.data()));if(ticket!==state.ticket)return;
  results.replaceChildren();
  for(const d of data){
    const url=originalURL(d.meta.original_url);if(!url)continue;
    const article=element('article','result');const a=element('a','result-title',d.meta.title||'Tråd utan rubrik');a.href=url;a.target='_blank';a.rel='noopener noreferrer';
    const meta=element('div','result-meta',[d.meta.category,d.meta.author||'Skribent saknas',d.meta.date||'Datum saknas'].join(' · '));
    const p=element('p','excerpt');p.append(safeExcerpt(d.excerpt));
    const link=element('a','source','Läs inlägget i originaltråden ↗');link.href=url;link.target='_blank';link.rel='noopener noreferrer';
    article.append(a,meta,p,link);results.append(article);
  }
  $('#pagination').hidden=state.list.length<=SIZE;
  $('#prev').disabled=state.page===0;$('#next').disabled=(state.page+1)*SIZE>=state.list.length;
  text('#page-number',`Sida ${state.page+1} av ${Math.ceil(state.list.length/SIZE)}`);
}
async function search(){
  const ticket=++state.ticket;state.page=0;$('#pagination').hidden=true;
  const term=query.value.trim();text('#term-label',term||'alla inlägg');
  if(!state.engine)return;
  const params=new URLSearchParams();if(term)params.set('q',term);for(const [key,e]of Object.entries(selects))if(e.value)params.set(key,e.value);if(!$('#variants').checked)params.set('variants','0');
  history.replaceState(null,'',location.pathname+(params.size?'?'+params:''));
  text('#result-count','Söker …');results.setAttribute('aria-busy','true');$('#search-submit').disabled=true;
  try{
    const parsed=parseQuery(term), filters=Object.fromEntries(Object.entries(selects).filter(([,e])=>e.value).map(([k,e])=>[k,e.value]));
    const spelling=spellingQueries(parsed.loose,$('#variants').checked);
    let list=[];
    if(parsed.loose || !parsed.phrases.length){
      const searches=await Promise.all(spelling.map(q=>state.engine.search(q||null,{filters})));
      const seen=new Set();for(const found of searches)for(const r of found.results)if(!seen.has(r.id)){seen.add(r.id);list.push(r)}
    }
    for(let i=0;i<parsed.phrases.length;i++){
      const exact=(await state.engine.search('"'+parsed.phrases[i]+'"',{filters})).results;
      if(i===0&&!parsed.loose)list=exact;else{const ids=new Set(exact.map(r=>r.id));list=list.filter(r=>ids.has(r.id))}
    }
    if(ticket!==state.ticket)return;state.list=list;
    text('#result-count',`${fmt(list.length)} ${list.length===1?'träff':'träffar'} i indexerade inlägg`);
    text('#search-note',$('#variants').checked&&!parsed.phrases.length?'Varianter: med/utan diakritik och bindestreck. Våldsironi matchar även vålds-ironi och valdsironi.':parsed.phrases.length?'Fraser matchas i angiven ordning. Svenska tecken stöds.':'Stavningsvarianter är avstängda.');
    if(!list.length){empty('Inga träffar i den här delen av arkivet.','Prova en annan stavning eller ta bort ett filter. Forumet är inte färdigindexerat, så inga träffar betyder inte att uttrycket saknas på Whoa.');return}
    await renderPage(ticket);
  }catch(err){if(ticket===state.ticket){text('#result-count','Sökningen kunde inte slutföras');empty('Sökningen stannade.',err.message+' Ladda om sidan om indexet nyligen har uppdaterats.');}}
  finally{if(ticket===state.ticket){$('#search-submit').disabled=false;results.setAttribute('aria-busy','false');}}
}
async function init(){
  const params=new URLSearchParams(location.search);query.value=params.get('q')??'våldsironi';$('#variants').checked=params.get('variants')!=='0';
  try{
    const local=await fetchJSON('./stats.json');state.stats=local;
    let basePath=new URL('./pagefind/',location.href).href;
    try{
      const latest=await fetchJSON(RAW+'archive-index/latest.json',4500);
      if(latest.schema_version===2 && latest.pagefind_version==='1.4.0' && /^[a-f0-9]{40}$/.test(latest.data_commit) && Date.parse(latest.refreshed_at)>Date.parse(local.refreshed_at)){
        const candidate=RAW+latest.data_commit+'/pagefind/';
        const entry=await fetchJSON(candidate+'pagefind-entry.json',4500);
        if(entry.version==='1.4.0'){state.stats=latest;basePath=candidate;state.source='senaste index från GitHub Actions';}
      }
    }catch{/* An imported, verified snapshot remains usable offline from GitHub. */}
    updateStats();
    if(!state.stats.coverage.indexed_posts){empty('Det finns ännu inga indexerade inlägg.','Insamlingen behöver slutföra en körning innan sökträffar kan visas.');text('#result-count','0 indexerade inlägg');return}
    state.engine=await import('./pagefind/pagefind.js');await state.engine.options({basePath,excerptLength:48,excerptEllipsis:'…'});await state.engine.init();
    const available=await state.engine.filters();for(const key of Object.keys(selects)){fillFilter(key,available[key]);if(params.has(key)&&Object.hasOwn(available[key]||{},params.get(key)))selects[key].value=params.get(key)}
    await search();
  }catch(err){text('#result-count','Indexet kunde inte läsas');empty('Arkivet kunde inte laddas.',err.message+' Prova att ladda om sidan.');}
}
form.addEventListener('submit',e=>{e.preventDefault();search()});Object.values(selects).forEach(e=>e.addEventListener('change',search));$('#variants').addEventListener('change',search);
$('.reset-filters').addEventListener('click',()=>{Object.values(selects).forEach(e=>e.value='');search()});
for(const a of document.querySelectorAll('.variant'))a.addEventListener('click',e=>{e.preventDefault();query.value=a.dataset.q;search()});
$('#prev').addEventListener('click',()=>{if(state.page>0){state.page--;renderPage(state.ticket)}});$('#next').addEventListener('click',()=>{if((state.page+1)*SIZE<state.list.length){state.page++;renderPage(state.ticket)}});
$('#copy-search').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(location.href);text('#copy-search','Länk kopierad');setTimeout(()=>text('#copy-search','Kopiera söklänk ↗'),2200)}catch{text('#copy-search','Kopiera länken i adressfältet')}});
init();
