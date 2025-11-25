
# Pokemon Card Updater

> This README was made by AI.

This workspace contains tools to fetch Pokémon card data and Pokémon species data, transform them, and upsert into Supabase tables.

**Scripts**

- `pokemon-db-updater.py`: Card updater — fetches sets and cards from the TCGdex API and upserts to Supabase.
- `pokedex-updater.py`: Pokedex updater — fetches Pokémon from PokeAPI, matches cards, and upserts Pokémon to Supabase.

**Card Updater (`pokemon-db-updater.py`)**

- Purpose: Download set and card data from TCGdex (`https://api.tcgdex.net/v2/en`) and upsert into Supabase tables (`pokemon_sets`, `cards`, `card_prices`).
- Environment variables required to run (or use a `.env` file with python-dotenv):
	- `SUPABASE_URL` — your Supabase project URL
	- `SUPABASE_KEY` — your Supabase anon/service key
- Dependencies: `requests`, `supabase`, `python-dotenv` (optional).

**Pokedex Updater (`pokedex-updater.py`)**

- Purpose: Pull Pokémon data from PokeAPI and link them to card entries in the `cards` table. Results are grouped by normalized base Pokémon name and upserted into a `pokedex` table.
- Environment variables (or `.env`):
	- `SUPABASE_URL_2` — Supabase URL
	- `SUPABASE_KEY_2` — Supabase key
- Dependencies: `requests`, `supabase`, `python-dotenv`, `rapidfuzz`.


