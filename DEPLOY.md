# Drift och import till ChatGPT Sites

## Flöde

1. GitHub Actions kör crawlern var fjärde timme och via **Run workflow**. Manuella och schemalagda körningar gör högst 400 anrop med minst tre sekunders mellanrum; robots.txt:s längre Crawl-delay respekteras.
2. `whoa.db.gz` i release `archive-state` är checkpoint. Den innehåller besökta adresser, kö, fel, extraherad text och komprimerad original-HTML. Avbrutna körningar bevarar kön.
3. `build_static.py` extraherar enskilda inlägg och verifierbar metadata ur den insamlade HTML-koden. Pagefind skapar ett uppdelat sökindex.
4. `publish_index.py` publicerar indexet på grenen `archive-index`. En separat commit skriver `latest.json` med den föregående datacommitens SHA. Alla läsningar av indexdelar kan därför bindas till samma oföränderliga version.
5. Artefakten **whoa-search-import** innehåller byggda Site-filer, källprov och databasen. Frontend och en faktiskt byggd indexkopia importeras till Sites. Där läses nyare `latest.json` automatiskt från samma offentliga repo. Ingen Sites-nyckel lagras i GitHub.

## Bygga lokalt från en verklig checkpoint

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
gh release download archive-state --pattern whoa.db.gz
gzip -dc whoa.db.gz > whoa.db
.venv/bin/python build_static.py
npx --yes pagefind@1.4.0 --site dist --glob 'post/**/*.html'
python -m http.server 8080 --directory dist
```

Det krävs insamlad data. Byggaren skapar inga exempeldata. `dist/stats.json` innehåller täckning och källversion. `dist/provenance.json` redovisar källadresser, hämtningstid och SHA-256 för den avkodade original-HTML som extraktionen utgår från. `dist/posts.jsonl.gz` är exporten av de sökbara inläggen.

## Sites

Projektets ID finns i `.openai/hosting.json`. Återanvänd det projektet; skapa inte en ny Site. Push av källa, sparad Sites-version och privat driftsättning görs med Sites anslutning. Frontend, stats och Pagefind-bundle måste komma från samma byggda export. Importera inga `diagnostics/`, rådatabaser eller inloggningsuppgifter till webbplatsen.

En import räcker för fortsatt datauppdatering: frontend hämtar en liten versionspekare och väljer ett nyare, kompatibelt index. Om GitHub inte svarar vid uppstart används den importerade versionen. Appen kör lokala Pagefind-moduler och hämtar bara indexdata från GitHub. Automatiska indexuppdateringar ändrar inte Site-koden eller dess delningsinställningar.

## Vad siffrorna betyder

- **Trådsidor:** hämtade sidor med identifierade originalinlägg.
- **Inlägg:** unika öppningsinlägg och svar, inklusive citerad text i meddelandekroppen.
- **Kön:** kända men ännu inte besökta adresser; den omfattar både list- och trådsidor. Den är ingen uppskattning av hela forumet.
- **Okänd återstående andel:** totalantalet offentligt tillgängliga sidor har inte inventerats. En tom kö bevisar inte fullständighet.
- **Okänd skribent:** namnet saknas eller källan visar Borttagen; inga identiteter rekonstrueras.

Fullständig täckning kräver inventering av alla kategorier och paginering, granskning av hämt- och tolkningsfel samt en dokumenterad jämförelse med originalforumet. Material som redan raderats eller inte längre är offentligt åtkomligt kan saknas permanent. Det är inte samma sak som en full historisk återställning.

## Gränser

Gratisdriften är beroende av GitHubs gällande kapacitetsgränser och tjänsternas tillgänglighet. Indexets storlek och byggtid måste följas när arkivet växer. Den här versionen har inte verifierats mot ett färdiginsamlat helt forum.
