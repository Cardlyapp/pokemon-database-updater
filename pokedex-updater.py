import os
import re
import requests
from supabase import create_client, Client
from dotenv import load_dotenv
from rapidfuzz import process, fuzz

# ---------------- CONFIG ----------------
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL_2")
SUPABASE_KEY = os.getenv("SUPABASE_KEY_2")
POKEAPI_BASE = "https://pokeapi.co/api/v2/pokemon"
BATCH_SIZE = 50
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------- HELPERS ----------------
VARIANT_PATTERNS = [
    r"mega", r"gmax", r"gigantamax",
    r"alola", r"alolan",
    r"galar", r"galarian",
    r"hisui", r"hisuan",
    r"paldea", r"paldean",
    r"v$", r"vmax$", r"ex$", r"gx$", r"lv\.x$", r"prism$"
]

def normalize_pokemon_name(name: str) -> str:
    """
    Simplify Pokémon names so variants are grouped under the main form.
    Example: 'Hisuian Zorua' -> 'Zorua'
             'Mega Charizard X' -> 'Charizard'
    """
    name = name.lower()

    # remove known prefixes like "hisuian", "paldean", "alolan", etc.
    name = re.sub(r"^(hisuian|paldean|galarian|alolan|mega|gigantamax)\s+", "", name)

    # remove suffixes like "v", "vmax", "ex", "gx"
    for pattern in VARIANT_PATTERNS:
        name = re.sub(pattern, "", name)

    return name.strip().capitalize()

# ---------------- FETCH DATA ----------------
def fetch_all_pokemon():
    print("Fetching all Pokémon from PokeAPI...")
    all_pokemon = []
    url = f"{POKEAPI_BASE}?limit=100"
    while url:
        res = requests.get(url)
        res.raise_for_status()
        data = res.json()
        all_pokemon.extend(data["results"])
        url = data.get("next")
    print(f"✅ Found {len(all_pokemon)} Pokémon total.")
    return all_pokemon

def fetch_pokemon_detail(url):
    res = requests.get(url)
    res.raise_for_status()
    data = res.json()
    return {
        "id": data["id"],
        "name": data["name"].capitalize(),
        "height": data.get("height"),
        "weight": data.get("weight"),
        "base_experience": data.get("base_experience"),
        "types": [t["type"]["name"] for t in data["types"]],
        "abilities": [a["ability"]["name"] for a in data["abilities"]],
        "sprite_url": data["sprites"]["other"]["official-artwork"]["front_default"],
    }

# ---------------- FUZZY CARD MATCHING ----------------
def load_card_names():
    print("Loading card names from Supabase...")
    res = supabase.table("cards").select("id", "name").execute()
    if not res.data:
        return []
    print(f"✅ Loaded {len(res.data)} cards.")
    return res.data

def find_card_ids_fuzzy(pokemon_name, cards, threshold=80):
    card_names = [c["name"] for c in cards]
    matches = process.extract(pokemon_name, card_names, scorer=fuzz.token_sort_ratio, limit=15)
    return [
        cards[i]["id"]
        for (_, score, i) in matches
        if score >= threshold
    ]

# ---------------- UPSERT INTO SUPABASE ----------------
def upsert_pokemon_batch(batch):
    try:
        supabase.table("pokedex").upsert(batch).execute()
        print(f"✅ Upserted {len(batch)} Pokémon")
    except Exception as e:
        print(f"❌ Error during batch upsert: {e}")

# ---------------- MAIN ----------------
def main():
    cards = load_card_names()
    if not cards:
        print("⚠️ No cards found in database. Load your card data first.")
        return

    pokemon_list = fetch_all_pokemon()

    # We'll collect data grouped by normalized Pokémon name
    grouped_pokemon = {}

    for p in pokemon_list:
        try:
            detail = fetch_pokemon_detail(p["url"])
            base_name = normalize_pokemon_name(detail["name"])
            card_ids = find_card_ids_fuzzy(base_name, cards)
            if base_name not in grouped_pokemon:
                grouped_pokemon[base_name] = {
                    "id": detail["id"],  # first seen ID
                    "name": base_name,
                    "types": detail["types"],
                    "abilities": detail["abilities"],
                    "sprite_url": detail["sprite_url"],
                    "card_ids": set(card_ids),
                }
            else:
                # Merge cards from variants
                grouped_pokemon[base_name]["card_ids"].update(card_ids)

            print(f"Processed {detail['name']} → {base_name} ({len(card_ids)} cards)")

        except Exception as e:
            print(f"❌ Error on {p['name']}: {e}")

    # Prepare batches for upsert
    buffer = []
    for i, (name, data) in enumerate(grouped_pokemon.items(), start=1):
        data["card_ids"] = list(data["card_ids"])
        buffer.append(data)

        if len(buffer) >= BATCH_SIZE:
            upsert_pokemon_batch(buffer)
            buffer.clear()

    if buffer:
        upsert_pokemon_batch(buffer)

    print(f"🎉 Grouped {len(grouped_pokemon)} base Pokémon imported successfully!")

if __name__ == "__main__":
    main()
