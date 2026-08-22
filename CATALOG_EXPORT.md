# GitHub card catalog export

`github_catalog_updater.py` fetches card and set data directly from TCGdex and
jpn-cards. It does not read Supabase or Neon, and it does not export prices.

The scheduled workflow publishes these files to `Cardlyapp/cards-database`:

```text
manifest.json
data/sets.json
data/cards.json
data-asia/sets.json
data-asia/cards.json
```

## Repository setup

1. Initialize `Cardlyapp/cards-database` with a default branch.
2. Keep that repository public so the mobile app can download files without a
   secret bundled into the app.
3. Create a fine-grained personal access token with **Contents: Read and write**
   access to only `Cardlyapp/cards-database`.
4. Add it to the `pokemon-database-updater` repository as an Actions secret named
   `CARDS_DATABASE_TOKEN`.

The workflow runs every day at 1:00 AM in `America/New_York` and can also be run
manually. A failed or incomplete source fetch exits before the workflow commits,
so the last complete catalog remains published.

## Local smoke test

Run a one-set export without publishing it:

```bash
python github_catalog_updater.py --output ./catalog-smoke-test --region international --limit-sets 1 --request-delay 0
```

Never point a limited test at a checked-out production catalog repository.
