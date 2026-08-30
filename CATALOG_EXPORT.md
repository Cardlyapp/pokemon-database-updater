# GitHub card catalog export

`github_catalog_updater.py` fetches card, set, and price data directly from
TCGdex and jpn-cards. It does not read Supabase or Neon. The published catalog
is the source of truth used by the database updater.

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
on GitHub Pages. It downloads and verifies every file against the manifest's
SHA-256 hashes, then updates Supabase and all configured Neon databases in
batches of 100 rows. This avoids fetching the APIs twice and avoids one remote
database commit per card.

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

The workflow runs at 00:00 and 12:00 UTC and can also be run manually. A failed
or incomplete source fetch exits before the workflow commits, so the last
complete catalog remains published. Set the repository variable
`CARD_CATALOG_URL` only if the Pages base URL is not
`https://cardlyapp.github.io/cards-database`.

## Local smoke test

Run a one-set export without publishing it:

```bash
python github_catalog_updater.py --output ./catalog-smoke-test --region international --limit-sets 1 --request-delay 0
```

Never point a limited test at a checked-out production catalog repository.
