# Whoa Search

Fulltextsökning i faktiskt insamlade offentliga Whoa-inlägg, med ChatGPT Sites som sökgränssnitt. Crawlern körs i GitHub Actions. Ingen Render-instans, extern sökdatabas eller betald söktjänst används.

**Täckningen är inte fullständig eller verifierad.** Sidan visar antal indexerade trådsidor och inlägg, upptäckta adresser i kön, hämtfel och saknad metadata. Återstående andel är okänd tills forumet har inventerats.

- Sökning i hela inläggstexten och trådrubriken med Pagefind 1.4.0.
- Frassökning med citattecken, svenska tecken och valbar expansion av stavningsvarianter.
- Kategori, skribent och år filtrerar det enskilda inlägget. Borttagna konton behandlas som okänd skribent.
- Svarens original-ID och HTML-ankare bevaras. Trådstarten, som återkommer på flera sidor, dedupliceras.
- Navigation, annonser och användarsignaturer indexeras inte.
- Inga exempelposter läggs i produktionsindexet.

## Drift

Se [DEPLOY.md](DEPLOY.md). GitHub Actions sparar återupptagbar SQLite i release `archive-state`, bygger ett uppdelat fulltextindex och publicerar det på grenen `archive-index`. `latest.json` pekar på en oföränderlig dataversion. Sites har en importerad kopia och läser nyare index automatiskt från GitHub.

Sidan är oberoende av Whoa. Kontrollera originaltrådarna innan material citeras eller tolkas.
