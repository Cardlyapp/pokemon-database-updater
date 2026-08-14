import os
import re
import time
import requests
from functools import lru_cache
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
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1
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
TWO_WORD_POKEMON_IDS = {
    1001, 1002, 1003, 1004, 1005,
    1009, 1020, 1021,
}
SPECIAL_POKEMON_NAMES = {
    29: "Nidoran♀",
    32: "Nidoran♂",
    474: "Porygon-Z",
    866: "Mr. Rime",
}

def normalize_pokemon_name(name: str, pokemon_id=None) -> str:
    """
    Simplify Pokémon names so variants are grouped under the main form.
    Example: 'Hisuian Zorua' -> 'Zorua'
             'Mega Charizard X' -> 'Charizard'
             'charizard-mega-x' -> 'Charizard'
             'tapu-koko-something' -> 'Tapu Koko'
             'iron-bundle-something' -> 'Iron Bundle'
    """
    if pokemon_id in SPECIAL_POKEMON_NAMES:
        return SPECIAL_POKEMON_NAMES[pokemon_id]

    name = name.lower()
    name_parts = name.split("-")
    words = name.replace("-", " ").split()
    is_multiword_name = False
    if pokemon_id in TWO_WORD_POKEMON_IDS and len(name_parts) > 1:
        name = " ".join(name_parts[:2])
        is_multiword_name = True
    elif "iron" in words and words.index("iron") + 1 < len(words):
        iron_index = words.index("iron")
        name = " ".join(words[iron_index:iron_index + 2])
        is_multiword_name = True
    elif name_parts[0] == "tapu" and len(name_parts) > 1:
        name = " ".join(name_parts[:2])
        is_multiword_name = True
    else:
        name = name_parts[0]
    name = re.sub(r"^(hisuian|paldean|galarian|alolan|mega|gigantamax)\s+", "", name)
    for pattern in VARIANT_PATTERNS:
        name = re.sub(pattern, "", name)
    name = name.strip()
    return name.title() if is_multiword_name else name.capitalize()

def fetch_json_with_retries(url, timeout=10):
    """Fetch JSON, retrying transient request and response errors."""
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as error:
            if error.response is not None and error.response.status_code == 404:
                raise
            last_error = error
        except (requests.exceptions.RequestException, ValueError) as error:
            last_error = error

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY_SECONDS * attempt)

    raise last_error

# ---------------- FETCH DATA ----------------
def fetch_all_pokemon():
    print("Fetching all Pokémon from PokeAPI...")
    all_pokemon = []
    url = f"{POKEAPI_BASE}?limit=2000"
    while url:
        data = fetch_json_with_retries(url)
        all_pokemon.extend(data["results"])
        url = data.get("next")
    print(f"✅ Found {len(all_pokemon)} Pokémon total.")
    return all_pokemon

def fetch_pokemon_detail(url):
    data = fetch_json_with_retries(url)
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
@lru_cache(maxsize=None)
def fetch_cards_from_tcgdex(pokemon_name):
    """Fetch all cards for a given Pokémon from TCGdex API."""
    try:
        search_name = pokemon_name.lower().replace(" ", "-")
        url = f"{TCGDEX_BASE}/cards?name={search_name}"
        cards = fetch_json_with_retries(url)
        
        if not cards:
            return []
        
        card_ids = [card.get("id") for card in cards if card.get("id")]
        return card_ids
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return []
        raise

@lru_cache(maxsize=None)
def fetch_cards_from_jpncards(pokemon_name):
    """Fetch all Japanese cards for a given Pokémon from jpn-cards API v2."""
    try:
        url = f"{JPNCARDS_BASE}/card/name={pokemon_name.lower()}"
        data = fetch_json_with_retries(url)
        cards = data.get("data", [])
        
        if not cards:
            return []
        
        card_ids = [card.get("uuid") for card in cards if card.get("uuid")]
        return card_ids
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return []
        raise

# ---------------- PROCESS POKEMON ----------------
def process_pokemon(p):
    """Process a Pokémon, retrying the complete detail and card-mapping flow."""
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            detail = fetch_pokemon_detail(p["url"])
            base_name = normalize_pokemon_name(detail["name"], detail["id"])

            # Fetch cards from both APIs concurrently
            with ThreadPoolExecutor(max_workers=2) as executor:
                tcgdex_future = executor.submit(fetch_cards_from_tcgdex, base_name)
                jpn_future = executor.submit(fetch_cards_from_jpncards, base_name)

                tcgdex_cards = tcgdex_future.result()
                jpn_cards = jpn_future.result()

            return {
                "base_name": base_name,
                "detail": detail,
                "card_ids": tcgdex_cards + jpn_cards,
                "success": True
            }
        except Exception as error:
            last_error = error
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS * attempt)

    return {
        "base_name": p.get("name", "Unknown"),
        "error": str(last_error),
        "success": False
    }

# ---------------- UPSERT INTO SUPABASE ----------------
def upsert_pokemon_batch(batch):
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            supabase.table("pokedex").upsert(batch).execute()
            return
        except Exception as error:
            last_error = error
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS * attempt)

    raise last_error

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
