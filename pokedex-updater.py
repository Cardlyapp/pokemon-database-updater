import os
import re
import requests
from supabase import create_client, Client
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# ---------------- CONFIG ----------------
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
POKEAPI_BASE = "https://pokeapi.co/api/v2/pokemon"
TCGDEX_BASE = "https://api.tcgdex.net/v2/en"
JPNCARDS_BASE = "https://www.jpn-cards.com/v2"
BATCH_SIZE = 50
MAX_WORKERS = 30  # Concurrent requests
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
    name = re.sub(r"^(hisuian|paldean|galarian|alolan|mega|gigantamax)\s+", "", name)
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
    """Fetch all cards for a given Pokémon from TCGdex API."""
    try:
        search_name = pokemon_name.lower().replace(" ", "-")
        url = f"{TCGDEX_BASE}/cards?name={search_name}"
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        cards = res.json()
        
        if not cards:
            return []
        
        card_ids = [card.get("id") for card in cards if card.get("id")]
        return card_ids
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return []
        return []
    except Exception:
        return []

def fetch_cards_from_jpncards(pokemon_name):
    """Fetch all Japanese cards for a given Pokémon from jpn-cards API v2."""
    try:
        url = f"{JPNCARDS_BASE}/card/name={pokemon_name.lower()}"
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        cards = data.get("data", [])
        
        if not cards:
            return []
        
        card_ids = [card.get("uuid") for card in cards if card.get("uuid")]
        return card_ids
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return []
        return []
    except Exception:
        return []

# ---------------- PROCESS POKEMON ----------------
def process_pokemon(p):
    """Process a single Pokémon and fetch all related data."""
    try:
        detail = fetch_pokemon_detail(p["url"])
        base_name = normalize_pokemon_name(detail["name"])
        
        # Fetch cards from both APIs concurrently
        with ThreadPoolExecutor(max_workers=2) as executor:
            tcgdex_future = executor.submit(fetch_cards_from_tcgdex, base_name)
            jpn_future = executor.submit(fetch_cards_from_jpncards, base_name)
            
            tcgdex_cards = tcgdex_future.result()
            jpn_cards = jpn_future.result()
        
        all_card_ids = tcgdex_cards + jpn_cards
        
        return {
            "base_name": base_name,
            "detail": detail,
            "card_ids": all_card_ids,
            "success": True
        }
    except Exception as e:
        return {
            "base_name": p.get("name", "Unknown"),
            "error": str(e),
            "success": False
        }

# ---------------- UPSERT INTO SUPABASE ----------------
def upsert_pokemon_batch(batch):
    try:
        supabase.table("pokedex").upsert(batch).execute()
    except Exception as e:
        print(f"\n❌ Error during batch upsert: {e}")

# ---------------- MAIN ----------------
def main():
    pokemon_list = fetch_all_pokemon()
    grouped_pokemon = {}

    print(f"\n🔄 Processing {len(pokemon_list)} Pokémon...")
    
    # Process all Pokémon concurrently with progress bar
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_pokemon, p): p for p in pokemon_list}
        
        with tqdm(total=len(pokemon_list), desc="Processing Pokémon", unit="pokemon") as pbar:
            for future in as_completed(futures):
                result = future.result()
                
                if result["success"]:
                    base_name = result["base_name"]
                    detail = result["detail"]
                    card_ids = result["card_ids"]
                    
                    if base_name not in grouped_pokemon:
                        grouped_pokemon[base_name] = {
                            "id": detail["id"],
                            "name": base_name,
                            "types": detail["types"],
                            "abilities": detail["abilities"],
                            "sprite_url": detail["sprite_url"],
                            "card_ids": set(card_ids),
                        }
                    else:
                        grouped_pokemon[base_name]["card_ids"].update(card_ids)
                else:
                    tqdm.write(f"❌ Error on {result['base_name']}: {result.get('error', 'Unknown')}")
                
                pbar.update(1)

    # Prepare and upsert batches
    print(f"\n📤 Uploading {len(grouped_pokemon)} Pokémon to Supabase...")
    buffer = []
    
    with tqdm(total=len(grouped_pokemon), desc="Uploading batches", unit="pokemon") as pbar:
        for name, data in grouped_pokemon.items():
            data["card_ids"] = list(data["card_ids"])
            buffer.append(data)

            if len(buffer) >= BATCH_SIZE:
                upsert_pokemon_batch(buffer)
                pbar.update(len(buffer))
                buffer.clear()

        if buffer:
            upsert_pokemon_batch(buffer)
            pbar.update(len(buffer))

    print(f"\n🎉 Successfully imported {len(grouped_pokemon)} base Pokémon!")

if __name__ == "__main__":
    main()