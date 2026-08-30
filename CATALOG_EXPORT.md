# GitHub card catalog export

`github_catalog_updater.py` fetches card, set, and price data directly from
TCGdex and jpn-cards. It does not read Supabase or Neon. The published catalog
is the source of truth used by the database updater.

The scheduled workflow checks the latest release of
`tcgdex/cards-database` against `manifest.json`'s `tcgdexRelease` value. Sets
and cards are rebuilt and uploaded to the databases only when that release tag
changes. On every other scheduled run, the workflow refreshes `prices.json`
from the existing card catalog and updates only the database price rows.

The scheduled workflow publishes these files to `Cardlyapp/cards-database`:

```text
manifest.json
data/sets.json
data/cards.json
data/prices.json
data-asia/sets.json
data-asia/cards.json
data-asia/prices.json
```

After publishing, the workflow waits for that exact manifest version to appear
on GitHub Pages and verifies every file against its SHA-256 hash. New TCGdex
releases bulk-load sets, cards, and prices into Supabase and all configured Neon
databases. Routine runs bulk-load only prices, in batches of 100 rows.

## Repository setup

1. Initialize `Cardlyapp/cards-database` with a default branch.
2. Keep that repository public so the mobile app can download files without a
   secret bundled into the app.
3. In that repository's **Settings → Pages**, publish from the default branch's
   repository root.
4. Create a fine-grained personal access token with **Contents: Read and write**
   access to only `Cardlyapp/cards-database`.
5. Add it to the `pokemon-database-updater` repository as an Actions secret named
   `CARDS_DATABASE_TOKEN`.

The workflow runs at 00:00 and 12:00 UTC and can also be run manually. If the
GitHub release check fails, sets and cards remain untouched while the price
refresh still runs. A failed or incomplete source fetch exits before the
workflow commits, so the last complete catalog remains published. Set the repository variable
`CARD_CATALOG_URL` only if the Pages base URL is not
`https://cardlyapp.github.io/cards-database`.

## Local smoke test

Run a one-set export without publishing it:

```bash
python github_catalog_updater.py --output ./catalog-smoke-test --region international --limit-sets 1 --request-delay 0
```

Never point a limited test at a checked-out production catalog repository.

Refresh only prices in an existing complete catalog:

```bash
python github_catalog_updater.py --output ./cards-database --prices-only
```

Upload only those catalog prices without writing set or card rows:

```bash
python pokemon-db-updater.py --catalog ./cards-database --prices-only --db-target both --version both
```
