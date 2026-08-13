# Pokemon Card & Pokedex Updater

This workspace contains tools to fetch Pokémon card data and Pokémon species data, transform them, and upsert into Supabase and/or Neon Postgres tables. Supports both international and Japanese card data.

## Scripts

- **`pokemon-db-updater.py`**: Card updater — fetches sets and cards from TCGdex and jpn-cards APIs and upserts to Supabase, Neon, or both.
- **`pokedex-updater.py`**: Pokedex updater — fetches Pokémon from PokeAPI, matches cards from both APIs, and upserts Pokémon to Supabase.


---

## Card Updater (`pokemon-db-updater.py`)

### Purpose
Download set and card data from multiple sources and upsert into database tables (`pokemon_sets`, `cards`, `card_prices`). The card updater supports Supabase, Neon, or both.

### Data Sources
- **International cards**: TCGdex API (`https://api.tcgdex.net/v2/en`)
- **Japanese cards**: jpn-cards API (`https://www.jpn-cards.com/v2`) with TCGdex fallback

### Environment Variables
Required (use `.env` file with python-dotenv):
- `SUPABASE_URL` — your Supabase project URL
- `SUPABASE_KEY` — your Supabase anon/service key
- `DATABASE_URL` — your first Neon Postgres connection string, required for Neon uploads
- `DATABASE_URL_2` — optional second Neon Postgres connection string
- `DATABASE_URLS` — optional list of Neon connection strings separated by newlines, commas, or semicolons

### Dependencies
```bash
pip install -r requirements.txt
```

### Usage

**Seed all international cards:**
```bash
python pokemon-db-updater.py --db-target neon
```

**Seed Japanese cards:**
```bash
python pokemon-db-updater.py --db-target neon --version japan
```

**Seed both versions:**
```bash
python pokemon-db-updater.py --db-target neon --version both
```

**Upload to both Supabase and Neon:**
```bash
python pokemon-db-updater.py --db-target both --version both
```

**Seed a single set (testing):**
```bash
python pokemon-db-updater.py --set base1
python pokemon-db-updater.py --set sv1 --version japan
```

**Limit number of sets:**
```bash
python pokemon-db-updater.py --limit 5 --version both
```

### Features
- Automatic Pokémon TCG Pocket set filtering
- Dual API support for Japanese cards (jpn-cards primary, TCGdex fallback)
- Smart image URL handling (WebP for international, fallback to pokemontcg.io)
- Rate limiting and error handling
- Progress tracking and detailed logging

---

## Pokedex Updater (`pokedex-updater.py`)

### Purpose
Pull Pokémon data from PokeAPI and link them to card entries in the `cards` table. Results are grouped by normalized base Pokémon name (consolidating variants) and upserted into a `pokedex` table.

### Data Sources
- **Pokémon data**: PokeAPI (`https://pokeapi.co/api/v2`)
- **Card matching**: TCGdex API + jpn-cards API

### Environment Variables
Required (or use `.env`):
- `SUPABASE_URL` — Supabase URL
- `SUPABASE_KEY` — Supabase key

### Dependencies
```bash
pip install requests supabase python-dotenv
```

### Usage
```bash
python pokedex-updater.py
```

### Features
- Normalizes Pokémon names to group variants (e.g., "Hisuian Zorua" → "Zorua")
- Fetches cards from both international (TCGdex) and Japanese (jpn-cards) sources
- Batched upserts (50 records at a time)
- Combines card IDs from all sources for comprehensive card linking

---

## Database Schema Requirements

### `pokemon_sets` table
- `id` (text, primary key)
- `name` (text)
- `series` (text)
- `total` (integer)
- `release_date` (text/date)
- `images` (jsonb)
- `legalities` (jsonb)
- `version` (text) — "international" or "japan"
- `updated_at` (timestamp)

### `cards` table
- `id` (text, primary key)
- `name` (text)
- `supertype` (text)
- `subtypes` (jsonb/array)
- `hp` (text)
- `types` (jsonb/array)
- `rarity` (text)
- `set_id` (text)
- `set_name` (text)
- `number` (text)
- `artist` (text)
- `image_small_url` (text)
- `image_large_url` (text)
- `version` (text) — "international" or "japan"
- Plus additional fields for legalities, regulation marks, etc.

### `card_prices` table
- `card_id` (text, foreign key)
- `market_source` (text) — "cardmarket" or "tcgplayer"
- `condition` (text)
- `currency` (text)
- `low`, `mid`, `high`, `average`, `market`, `trend` (numeric)
- `price_type` (text) — "normal", "holo", "reverse", etc.
- `last_updated` (timestamp)

### `pokedex` table
- `id` (integer, primary key)
- `name` (text)
- `types` (jsonb/array)
- `abilities` (jsonb/array)
- `sprite_url` (text)
- `card_ids` (jsonb/array) — contains both international and Japanese card IDs

---

## Notes

- Pokémon TCG Pocket sets are automatically filtered out
- Japanese card data prioritizes jpn-cards API with TCGdex as fallback
- Rate limiting is built in (0.5-1 second delays between requests)
- Image URLs use WebP format for better performance where available
- All timestamps use ISO 8601 format
- Upsert operations prevent duplicates using primary keys

## Neon Setup

1. Open your Neon project dashboard.
2. Click **Connect**, choose your branch, role, and database, then copy the connection string.
3. Add it to `.env`:
   ```bash
   DATABASE_URL="postgresql://USER:PASSWORD@HOST/dbname?sslmode=require&channel_binding=require"
   DATABASE_URL_2="postgresql://USER:PASSWORD@SECOND_HOST/dbname?sslmode=require&channel_binding=require"
   ```
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Create the tables by opening `schema/neon_cards.sql`, pasting it into Neon's SQL Editor, and running it.
6. Test with one small set:
   ```bash
   python pokemon-db-updater.py --db-target neon --set base1
   ```

For more copies, either continue with `DATABASE_URL_3`, `DATABASE_URL_4`, and so on, or use one `DATABASE_URLS` value with each connection string separated by a newline, comma, or semicolon. The updater sends the exact same rows to every Neon URL it finds.

Neon is plain Postgres, so there is no Supabase-style RLS to configure for this script. Keep Neon connection strings server-side only; do not expose them in frontend code.

For GitHub Actions, add repository secrets named `DATABASE_URL` and `DATABASE_URL_2` or a single `DATABASE_URLS` secret. If both Supabase and Neon credentials are present, `pokemon-db-updater.py` uploads cards to Supabase and every Neon database by default.

## Contributing

Feel free to open issues or submit PRs for improvements!
