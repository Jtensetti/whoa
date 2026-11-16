# Render deployment

This repository defines one Python web service with a persistent 1 GB Render disk.
It will **incur recurring paid charges** on Starter, including persistent storage.
Check current pricing before applying the Blueprint.

## Provisioning
1. Confirm Render workspace `Whoa Archive`.
2. Open https://dashboard.render.com/blueprint/new?repo=https://github.com/Jtensetti/whoa
3. Select `Whoa Archive`, review recurring costs, then Apply.
4. Verify /api/stats and monitor `indexed_pages`, `queued_urls`, `last_error`.
5. A robots.txt or network failure stops a batch without discarding the pending queue.

## Notes
- No claims of completeness until every public category page and thread page is discovered and the queue reaches zero with no unexplained failures.
- At least 3 seconds between requests, one process. Larger archives require more than 1 GB; disk size can be increased later.
- SQLite FTS5 indexes **forum thread pages** and includes text (subject to DOM parsing quality), not yet distinct individual author posts.
- The site returns short excerpts and links to the original, not a republished copy.
- Robots rules are checked before each crawl batch. If Whoa cannot be reached or robots.txt cannot be read, crawling pauses.
- Database lives on mounted disk; do not run multiple workers and do not use ephemeral free storage.
- Do not disable or bypass access restrictions or circumvent robots.txt.
