# Whoa Archive – kostnadsfri drift

**Driftmodellen är GitHub Actions + GitHub Releases + GitHub Pages + Pagefind.**
Ingen Render-tjänst eller betald databas behövs.

## Kom igång
1. Öppna **Settings → Pages** i GitHub-repot `Jtensetti/whoa`.
2. Under **Build and deployment**, välj **GitHub Actions**.
3. Öppna **Actions → Crawl Whoa and publish free search → Run workflow**. Ett tryck räcker. Schemalagda körningar sker därefter var fjärde timme.
4. Följ loggen. Den redovisar `fetched`, `indexed`, `queued` och eventuella stopp.
5. Webbplatsen publiceras normalt på **https://jtensetti.github.io/whoa/** när GitHub Pages är aktiverat och deployment har lyckats.

## Var datan ligger
En komprimerad SQLite-databas `whoa.db.gz` sparas som asset i GitHub Release `archive-state` efter varje körning. Nästa körning laddar ner den och fortsätter. En körning gör högst 400 anrop och väntar minst tre sekunder mellan anrop. Detta är ungefär 20 minuter och begränsar belastningen på Whoa.

## Förutsättningar
- GitHub Actions och GitHub Pages måste vara aktiverade på repot.
- Whoa måste svara från GitHubs körmiljö och tillåta insamling enligt robots.txt.
- GitHub Pages har en publiceringsgräns på 1 GB. Kontrollera storleken när fler trådar har indexerats.
- Fullständig täckning är **inte verifierad** förrän samtliga forumkategorier och paginerade trådar är inventerade, kön är tom och fel har granskats.
- Inga träffar betyder inte att begreppet saknas från det ännu oindexerade materialet.
- Indexet innehåller i första versionen trådsidor med extraherad text, inte en säker uppdelning av varje enskild skribents inlägg.
- Projektet är oberoende av Whoa och visar länkar till originalkällan.

## Kostnad
GitHub Actions på publika repositories är avgiftsfritt med standardrunners. GitHub Pages är kostnadsfritt inom tjänstens gränser. Ingen server hos Render behövs. Kontrollera GitHubs aktuella kvoter och användningsvillkor innan storskalig publicering.
