import os
import re
import requests
from supabase import create_client, Client
from dotenv import load_dotenv
from time import sleep

# ---------------- CONFIG ----------------
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
POKEAPI_BASE = "https://pokeapi.co/api/v2/pokemon"
TCGDEX_BASE = "https://api.tcgdex.net/v2/en"
JPNCARDS_BASE = "https://www.jpn-cards.com/v2"
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

    # remove known prefixes like "hisuian", "paldean", "galarian", "alolan", etc.
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

# ---------------- TCGDEX API ----------------
def fetch_cards_from_tcgdex(pokemon_name):
    """
    Fetch all cards for a given Pokémon from TCGdex API.
    Returns a list of card IDs.
    """
    try:
        # TCGdex uses lowercase names with hyphens
        search_name = pokemon_name.lower().replace(" ", "-")
        url = f"{TCGDEX_BASE}/cards?name={search_name}"
        
        print(f"  Searching TCGdex for: {pokemon_name}")
        res = requests.get(url)
        res.raise_for_status()
        cards = res.json()
        
        if not cards:
            print(f"  ⚠️ No cards found for {pokemon_name}")
            return []
        
        # Extract card IDs - TCGdex returns cards with an 'id' field
        card_ids = [card.get("id") for card in cards if card.get("id")]
        print(f"  ✅ Found {len(card_ids)} TCGdex cards for {pokemon_name}")
        
        # Be nice to the API
        sleep(0.1)
        
        return card_ids
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f"  ⚠️ No cards found for {pokemon_name} (404)")
            return []
        print(f"  ❌ HTTP error fetching cards for {pokemon_name}: {e}")
        return []
    except Exception as e:
        print(f"  ❌ Error fetching cards for {pokemon_name}: {e}")
        return []

def fetch_cards_from_jpncards(pokemon_name):
    """
    Fetch all Japanese cards for a given Pokémon from jpn-cards API v2.
    Returns a list of card UUIDs.
    """
    try:
        # jpn-cards API v2 endpoint - note it's /card/ not /cards/
        url = f"{JPNCARDS_BASE}/card/name={pokemon_name.lower()}"
        
        print(f"  Searching jpn-cards for: {pokemon_name}")
        res = requests.get(url)
        res.raise_for_status()
        data = res.json()
        
        # jpn-cards v2 returns {"data": [...], "count": N, "totalCount": N}
        cards = data.get("data", [])
        
        if not cards:
            print(f"  ⚠️ No Japanese cards found for {pokemon_name}")
            return []
        
        # Extract UUIDs from the response
        card_ids = [card.get("uuid") for card in cards if card.get("uuid")]
        print(f"  ✅ Found {len(card_ids)} Japanese cards for {pokemon_name}")
        
        # Be nice to the API
        sleep(0.1)
        
        return card_ids
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f"  ⚠️ No Japanese cards found for {pokemon_name} (404)")
            return []
        print(f"  ❌ HTTP error fetching Japanese cards for {pokemon_name}: {e}")
        return []
    except Exception as e:
        print(f"  ❌ Error fetching Japanese cards for {pokemon_name}: {e}")
        return []

# ---------------- UPSERT INTO SUPABASE ----------------
def upsert_pokemon_batch(batch):
    try:
        supabase.table("pokedex").upsert(batch).execute()
        print(f"✅ Upserted {len(batch)} Pokémon")
    except Exception as e:
        print(f"❌ Error during batch upsert: {e}")

# ---------------- MAIN ----------------
def main():
    pokemon_list = fetch_all_pokemon()

    # We'll collect data grouped by normalized Pokémon name
    grouped_pokemon = {}

    for p in pokemon_list:
        try:
            detail = fetch_pokemon_detail(p["url"])
            base_name = normalize_pokemon_name(detail["name"])
            
            # Fetch cards from both TCGdex and jpn-cards APIs
            tcgdex_cards = fetch_cards_from_tcgdex(base_name)
            jpn_cards = fetch_cards_from_jpncards(base_name)
            
            # Combine all card IDs
            all_card_ids = tcgdex_cards + jpn_cards
            
            if base_name not in grouped_pokemon:
                grouped_pokemon[base_name] = {
                    "id": detail["id"],  # first seen ID
                    "name": base_name,
                    "types": detail["types"],
                    "abilities": detail["abilities"],
                    "sprite_url": detail["sprite_url"],
                    "card_ids": set(all_card_ids),
                }
            else:
                # Merge cards from variants
                grouped_pokemon[base_name]["card_ids"].update(all_card_ids)

            total_cards = len(tcgdex_cards) + len(jpn_cards)
            print(f"Processed {detail['name']} → {base_name} ({total_cards} total cards: {len(tcgdex_cards)} EN + {len(jpn_cards)} JP)")


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