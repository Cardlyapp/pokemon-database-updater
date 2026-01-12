import os
import requests
from datetime import datetime
from supabase import create_client, Client
from typing import Dict, List, Optional
import time
import argparse

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not installed. Install it with: pip install python-dotenv")
    print("Or set environment variables manually.\n")

# Configuration
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
TCGDEX_BASE_URL_EN = "https://api.tcgdex.net/v2/en"
TCGDEX_BASE_URL_JP = "https://api.tcgdex.net/v2/ja"
JPN_CARDS_BASE_URL = "https://www.jpn-cards.com/v2"

# Initialize Supabase client (will be set later after validation)
supabase: Client = None


def get_base_url(version: str, api: str = "primary") -> str:
    """Get the appropriate API base URL based on version and API preference."""
    if version == "japan":
        return JPN_CARDS_BASE_URL if api == "primary" else TCGDEX_BASE_URL_JP
    return TCGDEX_BASE_URL_EN


def fetch_all_sets_jpn_cards() -> List[Dict]:
    """Fetch all Pokemon card sets from jpn-cards API."""
    print("Fetching all Japanese sets from jpn-cards API...")
    try:
        # Correct endpoint per docs: GET /v2/set/
        response = requests.get(f"{JPN_CARDS_BASE_URL}/set/", timeout=10)
        response.raise_for_status()
        # jpn-cards returns a list of sets for this endpoint
        return response.json()
    except Exception as e:
        print(f"Failed to fetch from jpn-cards: {e}")
        return None


def fetch_set_details_jpn_cards(set_id: str) -> Dict:
    """Fetch detailed information for a specific set from jpn-cards."""
    print(f"Fetching Japanese set details from jpn-cards for: {set_id}")
    try:
        # Docs show GET /v2/set/<id> (or /set/uuid/<id>), use numeric id path
        response = requests.get(f"{JPN_CARDS_BASE_URL}/set/{set_id}", timeout=10)
        response.raise_for_status()
        # This endpoint returns a single set object (not wrapped in "data")
        return response.json()
    except Exception as e:
        print(f"Failed to fetch set from jpn-cards: {e}")
        return None


def fetch_card_details_jpn_cards(card_id: str) -> Dict:
    """Fetch detailed information for a specific card from jpn-cards."""
    print(f"Fetching Japanese card details from jpn-cards for: {card_id}")
    try:
        # Per docs: GET /v2/card/id=<id>
        response = requests.get(f"{JPN_CARDS_BASE_URL}/card/id={card_id}", timeout=10)
        response.raise_for_status()
        data = response.json()
        # The card endpoints return {"data":[ {...} ], ...}
        if isinstance(data, dict) and 'data' in data and isinstance(data['data'], list) and len(data['data']) > 0:
            return data['data'][0]
        # If the API returns a single object for some reason, return it
        if isinstance(data, dict) and 'id' in data:
            return data
        return None
    except Exception as e:
        print(f"Failed to fetch card from jpn-cards: {e}")
        return None


def fetch_all_sets(version: str = "international") -> List[Dict]:
    """Fetch all Pokemon card sets from appropriate API."""
    if version == "japan":
        # Try jpn-cards first
        sets = fetch_all_sets_jpn_cards()
        if sets is not None:
            return sets
        # Fallback to TCGdex
        print("Falling back to TCGdex for Japanese sets...")

    base_url = get_base_url(version, "fallback")
    print(f"Fetching all {version} sets from TCGdex...")
    response = requests.get(f"{base_url}/sets")
    response.raise_for_status()
    return response.json()


def fetch_set_details(set_id: str, version: str = "international") -> Dict:
    """Fetch detailed information for a specific set."""
    if version == "japan":
        # Try jpn-cards first
        set_details = fetch_set_details_jpn_cards(set_id)
        if set_details is not None:
            return set_details
        # Fallback to TCGdex
        print(f"Falling back to TCGdex for set: {set_id}")

    base_url = get_base_url(version, "fallback")
    print(f"Fetching {version} set details from TCGdex for: {set_id}")
    response = requests.get(f"{base_url}/sets/{set_id}")
    response.raise_for_status()
    return response.json()


def fetch_cards_in_set(set_id: str, version: str = "international") -> List[Dict]:
    """Fetch all cards in a specific set."""
    if version == "japan":
        try:
            response = requests.get(f"{JPN_CARDS_BASE_URL}/card/set_id={set_id}", timeout=10)
            response.raise_for_status()
            data = response.json()
            # jpn-cards returns {"data":[...], ...}
            if isinstance(data, dict) and 'data' in data and isinstance(data['data'], list):
                return data['data']
            return []
        except Exception as e:
            print(f"Falling back to TCGdex for cards in set {set_id}: {e}")


    base_url = get_base_url(version, "fallback")
    print(f"Fetching {version} cards for set from TCGdex: {set_id}")
    response = requests.get(f"{base_url}/sets/{set_id}")
    response.raise_for_status()
    set_data = response.json()
    return set_data.get('cards', [])


def fetch_card_details(card_id: str, version: str = "international") -> Dict:
    """Fetch detailed information for a specific card."""
    if version == "japan":
        # Try jpn-cards first
        card_details = fetch_card_details_jpn_cards(card_id)
        if card_details is not None:
            return card_details
        # Fallback to TCGdex
        print(f"Falling back to TCGdex for card: {card_id}")

    base_url = get_base_url(version, "fallback")
    response = requests.get(f"{base_url}/cards/{card_id}")
    response.raise_for_status()
    return response.json()


def transform_set_data_jpn_cards(set_data: Dict) -> Dict:
    """Transform jpn-cards set data to match Supabase schema."""
    # jpn-cards set object fields (examples in docs): id, name, image_url, language, year, date, card_count, printed_count, set_code, uuid
    return {
        'id': set_data.get('id'),
        'name': set_data.get('name'),
        'series': None,  # jpn-cards does not always have a "series" field mapped the same way; keep None or map if you prefer
        'total': set_data.get('card_count') or set_data.get('card_count', None),
        'release_date': set_data.get('date') or set_data.get('year'),
        'images': {
            'logo': set_data.get('image_url'),
            'symbol': None
        },
        'legalities': None,
        'version': 'japan',
        'updated_at': datetime.now().isoformat()
    }


def transform_card_data_jpn_cards(card_data: Dict) -> Dict:
    """Transform jpn-cards card data to match Supabase schema."""
    # jpn-cards card objects usually include keys like:
    # id, setData (dict), name, types, hp, evolvesFrom, effect (array), attacks (array), rules, weaknesses, supertype, subtypes, rarity, cardLegalities, artist, imageUrl, cardUrl, sequenceNumber, printedNumber, uuid
    set_info = card_data.get('setData', {}) if isinstance(card_data.get('setData', {}), dict) else {}

    # Image fields: jpn-cards uses `imageUrl` for the card image in examples
    image_small_url = card_data.get('imageUrl') or card_data.get('image_url')
    # jpn-cards doesn't always provide a hires variant; reuse imageUrl if missing
    image_large_url = image_small_url

    # Card legalities in jpn-cards examples are in `cardLegalities`
    card_legal = card_data.get('cardLegalities') or {}

    return {
        'id': card_data.get('id'),
        'name': card_data.get('name'),
        'supertype': card_data.get('supertype'),
        'subtypes': card_data.get('subtypes'),
        'hp': str(card_data.get('hp')) if card_data.get('hp') else None,
        'types': card_data.get('types'),
        'rarity': card_data.get('rarity'),
        'set_id': set_info.get('id') if isinstance(set_info, dict) else None,
        'set_name': set_info.get('name') if isinstance(set_info, dict) else None,
        'set_series': None,
        'set_symbol_url': set_info.get('image_url') if isinstance(set_info, dict) else None,
        'set_logo_url': set_info.get('image_url') if isinstance(set_info, dict) else None,
        'number': card_data.get('printedNumber') or card_data.get('sequenceNumber') or card_data.get('printedNumber'),
        'artist': card_data.get('artist'),
        'image_small_url': image_small_url,
        'image_large_url': image_large_url,
        'legality_standard': card_legal.get('Standard') if isinstance(card_legal, dict) else None,
        'legality_expanded': card_legal.get('Expanded') if isinstance(card_legal, dict) else None,
        'legality_unlimited': card_legal.get('Unlimited') if isinstance(card_legal, dict) else None,
        'regulation_mark': None,
        'stage': None,
        'suffix': None,
        'description': None,
        'tcgplayer_url': card_data.get('cardUrl'),
        'variants': None,
        'version': 'japan',
        'updated_at': datetime.now().isoformat()
    }


def transform_set_data(set_data: Dict, version: str = "international", source: str = "tcgdex") -> Dict:
    """Transform set data to match Supabase schema."""
    # Use jpn-cards transformer if data is from jpn-cards
    if source == "jpn-cards":
        return transform_set_data_jpn_cards(set_data)

    # Helper to ensure set images are returned as a dict with .png extensions
    def _ensure_png_url_local(url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        # preserve query string
        if '?' in url:
            base, query = url.split('?', 1)
            query = '?' + query
        else:
            base, query = url, ''
        last_segment = base.rstrip('/').split('/')[-1]
        if '.' in last_segment:
            return base + query
        return base + '.png' + query

    return {
        'id': set_data.get('id'),
        'name': set_data.get('name'),
        'series': set_data.get('serie', {}).get('name') if isinstance(set_data.get('serie'), dict) else set_data.get('serie'),
        'total': set_data.get('cardCount', {}).get('total') if isinstance(set_data.get('cardCount'), dict) else set_data.get('total'),
        'release_date': set_data.get('releaseDate'),
        'images': {
            'logo': _ensure_png_url_local(set_data.get('logo')) if set_data.get('logo') else None,
            'symbol': _ensure_png_url_local(set_data.get('symbol')) if set_data.get('symbol') else None
        },
        'legalities': set_data.get('legal'),
        'version': version,
        'updated_at': datetime.now().isoformat()
    }


def transform_card_data(card_data: Dict, version: str = "international", source: str = "tcgdex") -> Dict:
    """Transform card data to match Supabase schema."""
    # Use jpn-cards transformer if data is from jpn-cards
    if source == "jpn-cards":
        return transform_card_data_jpn_cards(card_data)

    set_info = card_data.get('set', {})
    legalities = card_data.get('legal', {})

    # Extract TCGPlayer URL if available
    tcgplayer_url = None
    if 'tcgplayer' in card_data:
        tcgplayer_url = card_data['tcgplayer'].get('url')

    # Construct proper image URLs
    # TCGdex returns base URLs without extensions
    # Format: {base_url}/{quality}.{extension}
    base_image_url = card_data.get('image')
    image_small_url = None
    image_large_url = None

    if base_image_url:
        # Small image: low quality, webp format (245x337)
        image_small_url = f"{base_image_url}/low.webp"
        # Large image: high quality, webp format (600x825)
        image_large_url = f"{base_image_url}/high.webp"
    else:
        # Fallback to images.pokemontcg.io when TCGdex image is missing.
        # Use set id and card number if available to construct URLs.
        set_id_val = set_info.get('id') if isinstance(set_info, dict) else None
        card_num = card_data.get('localId') or card_data.get('number') or None
        if not card_num:
            # try extracting trailing part of card id like 'base1-1'
            cid = card_data.get('id')
            if isinstance(cid, str) and '-' in cid:
                card_num = cid.split('-')[-1]
        if set_id_val and card_num:
            image_small_url = f"https://images.pokemontcg.io/{set_id_val}/{card_num}.png"
            image_large_url = f"https://images.pokemontcg.io/{set_id_val}/{card_num}_hires.png"

    # Helper used to ensure set image urls include .png if missing
    def _ensure_png_for_set(val: Optional[str]) -> Optional[str]:
        if not val:
            return None
        if '?' in val:
            base, query = val.split('?', 1)
            query = '?' + query
        else:
            base, query = val, ''
        last = base.rstrip('/').split('/')[-1]
        if '.' in last:
            return base + query
        return base + '.png' + query

    return {
        'id': card_data.get('id'),
        'name': card_data.get('name'),
        'supertype': card_data.get('category'),
        'subtypes': card_data.get('dexId'),  # Note: TCGdex structure may differ
        'hp': str(card_data.get('hp')) if card_data.get('hp') else None,
        'types': card_data.get('types'),
        'rarity': card_data.get('rarity'),
        'set_id': set_info.get('id') if isinstance(set_info, dict) else None,
        'set_name': set_info.get('name') if isinstance(set_info, dict) else None,
        'set_series': set_info.get('serie') if isinstance(set_info, dict) else None,
        'set_symbol_url': _ensure_png_for_set(set_info.get('symbol')) if isinstance(set_info, dict) else None,
        'set_logo_url': _ensure_png_for_set(set_info.get('logo')) if isinstance(set_info, dict) else None,
        'number': card_data.get('localId'),
        'artist': card_data.get('illustrator'),
        'image_small_url': image_small_url,
        'image_large_url': image_large_url,
        'legality_standard': legalities.get('standard') if isinstance(legalities, dict) else None,
        'legality_expanded': legalities.get('expanded') if isinstance(legalities, dict) else None,
        'legality_unlimited': legalities.get('unlimited') if isinstance(legalities, dict) else None,
        'regulation_mark': card_data.get('regulationMark'),
        'stage': card_data.get('stage'),
        'suffix': card_data.get('suffix'),
        'description': card_data.get('effect') or card_data.get('description'),
        'tcgplayer_url': tcgplayer_url,
        'variants': card_data.get('variants'),
        'version': version,
        'updated_at': datetime.now().isoformat()
    }


def transform_price_data(card_id: str, pricing_data: Dict) -> List[Dict]:
    """Transform TCGdex pricing data to match Supabase schema."""
    price_records = []

    # Process Cardmarket pricing
    if 'cardmarket' in pricing_data:
        cm = pricing_data['cardmarket']
        updated = cm.get('updated')

        # Regular/average prices
        price_records.append({
            'card_id': card_id,
            'market_source': 'cardmarket',
            'condition': 'average',
            'currency': cm.get('unit', 'EUR'),
            'low': cm.get('low'),
            'average': cm.get('avg'),
            'trend': str(cm.get('trend')),
            'price_type': 'normal',
            'last_updated': updated,
            'updated_at': datetime.now().isoformat()
        })

        # Holo prices
        if 'avg-holo' in cm or 'low-holo' in cm:
            price_records.append({
                'card_id': card_id,
                'market_source': 'cardmarket',
                'condition': 'average',
                'currency': cm.get('unit', 'EUR'),
                'low': cm.get('low-holo'),
                'average': cm.get('avg-holo'),
                'trend': str(cm.get('trend-holo')),
                'price_type': 'holo',
                'last_updated': updated,
                'updated_at': datetime.now().isoformat()
            })

    # Process TCGPlayer pricing
    if 'tcgplayer' in pricing_data:
        tcp = pricing_data['tcgplayer']
        updated = tcp.get('updated')
        unit = tcp.get('unit', 'USD')

        # Normal prices
        if 'normal' in tcp:
            normal = tcp['normal']
            price_records.append({
                'card_id': card_id,
                'market_source': 'tcgplayer',
                'condition': 'normal',
                'currency': unit,
                'low': normal.get('lowPrice'),
                'mid': normal.get('midPrice'),
                'high': normal.get('highPrice'),
                'market': normal.get('marketPrice'),
                'price_type': 'normal',
                'last_updated': updated,
                'updated_at': datetime.now().isoformat()
            })

        # Reverse holo prices
        if 'reverse' in tcp:
            reverse = tcp['reverse']
            price_records.append({
                'card_id': card_id,
                'market_source': 'tcgplayer',
                'condition': 'normal',
                'currency': unit,
                'low': reverse.get('lowPrice'),
                'mid': reverse.get('midPrice'),
                'high': reverse.get('highPrice'),
                'market': reverse.get('marketPrice'),
                'price_type': 'reverse',
                'last_updated': updated,
                'updated_at': datetime.now().isoformat()
            })

        # Holofoil prices
        if 'holofoil' in tcp:
            holo = tcp['holofoil']
            price_records.append({
                'card_id': card_id,
                'market_source': 'tcgplayer',
                'condition': 'normal',
                'currency': unit,
                'low': holo.get('lowPrice'),
                'mid': holo.get('midPrice'),
                'high': holo.get('highPrice'),
                'market': holo.get('marketPrice'),
                'price_type': 'holofoil',
                'last_updated': updated,
                'updated_at': datetime.now().isoformat()
            })

        # 1st Edition prices
        if '1stEdition' in tcp:
            first_ed = tcp['1stEdition']
            price_records.append({
                'card_id': card_id,
                'market_source': 'tcgplayer',
                'condition': 'normal',
                'currency': unit,
                'low': first_ed.get('lowPrice'),
                'mid': first_ed.get('midPrice'),
                'high': first_ed.get('highPrice'),
                'market': first_ed.get('marketPrice'),
                'price_type': '1stEdition',
                'last_updated': updated,
                'updated_at': datetime.now().isoformat()
            })

    return price_records


def detect_data_source(data: Dict) -> str:
    """Detect whether data came from jpn-cards or tcgdex based on structure."""
    # jpn-cards responses commonly include 'setData' (for cards) or 'imageUrl'/'cardUrl' keys.
    if isinstance(data, dict) and ('setData' in data or 'imageUrl' in data or 'cardUrl' in data):
        return "jpn-cards"
    # jpn-cards sets endpoint returns a list of set objects (with 'card_count' etc.)
    if isinstance(data, dict) and ('card_count' in data or 'set_code' in data):
        return "jpn-cards"
    return "tcgdex"


def upsert_set(set_data: Dict, version: str = "international") -> bool:
    """Insert or update a set in Supabase."""
    try:
        source = detect_data_source(set_data)
        transformed_data = transform_set_data(set_data, version, source)
        supabase.table('pokemon_sets').upsert(transformed_data).execute()
        print(f"✓ Upserted {version} set: {transformed_data['name']} (source: {source})")
        return True
    except Exception as e:
        print(f"✗ Error upserting {version} set {set_data.get('id')}: {e}")
        return False


def upsert_card(card_data: Dict, version: str = "international") -> bool:
    """Insert or update a card in Supabase."""
    try:
        source = detect_data_source(card_data)
        transformed_data = transform_card_data(card_data, version, source)
        supabase.table('cards').upsert(transformed_data).execute()
        print(f"✓ Upserted {version} card: {transformed_data['name']} ({transformed_data['id']}) (source: {source})")
        return True
    except Exception as e:
        print(f"✗ Error upserting {version} card {card_data.get('id')}: {e}")
        return False


def upsert_prices(card_id: str, pricing_data: Dict) -> int:
    """Insert or update card prices in Supabase."""
    if not pricing_data:
        return 0

    try:
        price_records = transform_price_data(card_id, pricing_data)

        if not price_records:
            return 0
        # Delete existing price records for this card to avoid duplicates
        # This replaces old pricing rows with the newly-fetched ones.
        try:
            supabase.table('card_prices').delete().eq('card_id', card_id).execute()
        except Exception:
            # If delete fails, continue to attempt insert and let the outer try/except
            pass

        # Insert new price records
        supabase.table('card_prices').insert(price_records).execute()
        print(f"  ✓ Inserted {len(price_records)} price records for card {card_id}")
        return len(price_records)
    except Exception as e:
        print(f"  ✗ Error upserting prices for card {card_id}: {e}")
        return 0


def seed_all_data(limit_sets: Optional[int] = None, version: str = "international"):
    """
    Main function to seed all data from APIs to Supabase.
    For Japanese cards, tries jpn-cards API first, then falls back to TCGdex.
    
    Args:
        limit_sets: Optional limit on number of sets to process (for testing)
        version: "international" or "japan"
    """
    print("="*60)
    print(f"Starting seeding process ({version})")
    if version == "japan":
        print("Primary API: jpn-cards.com (fallback: TCGdex)")
    else:
        print("API: TCGdex")
    print("="*60)
    
    # Fetch all sets
    sets = fetch_all_sets(version)
    print(f"\nFound {len(sets)} {version} sets")

    # Filter out Pokémon TCG Pocket sets (by name or id)
    def is_pocket_set(set_summary):
        set_id = str(set_summary.get('id') or '').lower()
        set_name = str(set_summary.get('name') or '').lower()

        return (
            "pocket" in set_id
            or "pocket" in set_name
            or "ポケモンカードゲームスカーレット&バイオレット" in set_name
            or "ポケモンカードゲーム" in set_name
        )



    sets = [s for s in sets if not is_pocket_set(s)]
    print(f"After filtering, {len(sets)} sets remain (Pocket sets excluded)")

    if limit_sets:
        sets = sets[:limit_sets]
        print(f"Limiting to {limit_sets} sets for testing")

    sets_success = 0
    cards_success = 0
    cards_failed = 0
    prices_success = 0

    # Process each set
    for i, set_summary in enumerate(sets, 1):
        set_id = set_summary.get('id')
        print(f"\n[{i}/{len(sets)}] Processing {version} set: {set_id}")

        try:
            # Fetch detailed set information
            set_details = fetch_set_details(set_id, version)
            if set_details is None:
                print(f"✗ Could not fetch set details for {set_id}")
                continue
                
            # Check fetched set name/serie for 'pocket'
            name = (set_details.get('name') or '').lower()
            serie = set_details.get('serie') or set_details.get('series')
            if isinstance(serie, dict):
                serie_name = (serie.get('name') or '').lower()
            else:
                serie_name = (serie or '').lower()
            if 'pocket' in name or 'pocket' in serie_name:
                print(f"Skipping set '{set_id}' (Pocket set detected by name or serie)")
                continue

            # Upsert set
            if upsert_set(set_details, version):
                sets_success += 1

            # Fetch and process all cards in the set
            if version == "japan":
                cards = fetch_cards_in_set(set_id, version)
            else:
                cards = set_details.get('cards', [])

            print(f"Found {len(cards)} cards in set {set_id}")

            for j, card_summary in enumerate(cards, 1):
                card_id = card_summary.get('id')

                try:
                    # Fetch detailed card information
                    card_details = fetch_card_details(card_id, version)
                    if card_details is None:
                        print(f"✗ Could not fetch card details for {card_id}")
                        cards_failed += 1
                        continue

                    # Upsert card
                    if upsert_card(card_details, version):
                        cards_success += 1

                        # Upsert pricing data if available
                        if 'pricing' in card_details:
                            price_count = upsert_prices(card_id, card_details['pricing'])
                            prices_success += price_count
                    else:
                        cards_failed += 1

                    # Rate limiting - be respectful to the API
                    if j % 10 == 0:
                        print(f"  Progress: {j}/{len(cards)} cards processed")
                        time.sleep(0.5)

                except Exception as e:
                    print(f"✗ Error processing card {card_id}: {e}")
                    cards_failed += 1
                    continue

            # Pause between sets
            time.sleep(1)

        except Exception as e:
            print(f"✗ Error processing set {set_id}: {e}")
            continue

    # Print summary
    print("\n" + "="*60)
    print(f"Seeding Summary ({version})")
    print("="*60)
    print(f"Sets processed: {sets_success}/{len(sets)}")
    print(f"Cards succeeded: {cards_success}")
    print(f"Cards failed: {cards_failed}")
    print(f"Price records created: {prices_success}")
    print("="*60)


def seed_single_set(set_id: str, version: str = "international"):
    """Seed a single set and its cards (useful for testing)."""
    # Skip if set_id or set name contains 'pocket'
    if 'pocket' in (set_id or '').lower():
        print(f"Skipping set '{set_id}' (Pocket set detected)")
        return

    print(f"Seeding single {version} set: {set_id}")
    if version == "japan":
        print("Trying jpn-cards API first, will fallback to TCGdex if needed")

    try:
        # Fetch and upsert set
        set_details = fetch_set_details(set_id, version)
        if set_details is None:
            print(f"✗ Could not fetch set details for {set_id}")
            return
            
        # Also skip if set name or serie contains 'pocket'
        name = (set_details.get('name') or '').lower()
        serie = set_details.get('serie') or set_details.get('series')
        if isinstance(serie, dict):
            serie_name = (serie.get('name') or '').lower()
        else:
            serie_name = (serie or '').lower()
        if 'pocket' in name or 'pocket' in serie_name:
            print(f"Skipping set '{set_id}' (Pocket set detected by name or serie)")
            return
        upsert_set(set_details, version)

        # Fetch and upsert cards
        cards = set_details.get('cards', [])
        print(f"Found {len(cards)} cards")

        for card_summary in cards:
            card_id = card_summary.get('id')
            card_details = fetch_card_details(card_id, version)
            if card_details is None:
                print(f"✗ Could not fetch card details for {card_id}")
                continue
            upsert_card(card_details, version)

            # Upsert pricing data if available
            if 'pricing' in card_details:
                upsert_prices(card_id, card_details['pricing'])

            time.sleep(0.3)

        print(f"✓ Successfully seeded {version} set {set_id}")

    except Exception as e:
        print(f"✗ Error seeding {version} set {set_id}: {e}")


def seed_both_versions(limit_sets: Optional[int] = None):
    """Seed both international and Japanese versions."""
    print("\n" + "="*60)
    print("SEEDING BOTH INTERNATIONAL AND JAPANESE VERSIONS")
    print("="*60 + "\n")
    
    # Seed international first
    seed_all_data(limit_sets=limit_sets, version="international")
    
    print("\n" + "="*60)
    print("Pausing before Japanese seeding...")
    print("="*60)
    time.sleep(2)
    
    # Then seed Japanese
    seed_all_data(limit_sets=limit_sets, version="japan")
    
    print("\n" + "="*60)
    print("COMPLETED BOTH VERSIONS")
    print("="*60)

def update_card_prices(card_id: str, version: str = "international", show_prices: bool = False) -> int:
    """Fetch and update prices for a single card."""
    try:
        card_details = fetch_card_details(card_id, version)
        if not card_details:
            return 0

        pricing = card_details.get("pricing")
        if not pricing:
            return 0

        if show_prices:
            print(f"\n📊 Pricing data for {card_id}:")
            print(pricing)

        return upsert_prices(card_id, pricing)

    except Exception as e:
        print(f"✗ Failed to update prices for {card_id}: {e}")
        return 0

def seed_prices_only(version: str = "international", show_prices: bool = False):
    """Update prices for all cards already in the database."""
    print("=" * 60)
    print(f"Updating prices only ({version})")
    print("=" * 60)

    cards = supabase.table("cards").select("id").eq("version", version).execute().data

    print(f"Found {len(cards)} cards to update prices for")

    total_prices = 0

    for i, card in enumerate(cards, 1):
        card_id = card["id"]
        print(f"[{i}/{len(cards)}] Updating prices for {card_id}")

        count = update_card_prices(card_id, version, show_prices)
        total_prices += count

        if i % 10 == 0:
            time.sleep(0.5)

    print("\n✓ Price update complete")
    print(f"Total price records inserted: {total_prices}")



if __name__ == "__main__":
    # Check for environment variables
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("=" * 60)
        print("ERROR: Missing Supabase credentials")
        print("=" * 60)
        print("\nYou need to set the following environment variables:\n")
        print("Option 1 - Using a .env file (recommended):")
        print("  1. Create a file named '.env' in the same directory as this script")
        print("  2. Add these lines to the file:")
        print("     SUPABASE_URL=your-project-url")
        print("     SUPABASE_KEY=your-anon-key")
        print("  3. Install python-dotenv: pip install python-dotenv")
        print("  4. Add this at the top of the script:")
        print("     from dotenv import load_dotenv")
        print("     load_dotenv()")
        print("\nOption 2 - Set environment variables in terminal:")
        print("  Windows PowerShell:")
        print("    $env:SUPABASE_URL='your-project-url'")
        print("    $env:SUPABASE_KEY='your-anon-key'")
        print("\n  Windows CMD:")
        print("    set SUPABASE_URL=your-project-url")
        print("    set SUPABASE_KEY=your-anon-key")
        print("\n  Linux/Mac:")
        print("    export SUPABASE_URL='your-project-url'")
        print("    export SUPABASE_KEY='your-anon-key'")
        print("\nOption 3 - Hardcode in script (not recommended for production):")
        print("  Replace lines 7-8 with:")
        print("    SUPABASE_URL = 'your-project-url'")
        print("    SUPABASE_KEY = 'your-anon-key'")
        print("=" * 60)
        exit(1)
    
    # Initialize Supabase client
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✓ Successfully connected to Supabase\n")

    parser = argparse.ArgumentParser(description="Pokemon DB updater (sets, cards, prices)")
    parser.add_argument("--set", "-s", dest="set_id", help="Seed a single set by id (test mode)")
    parser.add_argument("--limit", "-l", dest="limit", type=int, help="Limit number of sets to process")
    parser.add_argument("--version", "-v", dest="version", choices=["international", "japan", "both"], 
                        default="international", help="Which version to seed (default: international)")
    parser.add_argument(
    "--prices-only",
    action="store_true",
    help="Update prices only (no sets or cards)"
    )

    parser.add_argument(
        "--show-prices",
        action="store_true",
        help="Print pricing data when fetched"
    )

    args = parser.parse_args()

    if args.prices_only:
        if args.version == "both":
            seed_prices_only("international", show_prices=args.show_prices)
            time.sleep(2)
            seed_prices_only("japan", show_prices=args.show_prices)
        else:
            seed_prices_only(args.version, show_prices=args.show_prices)

    elif args.set_id:
        seed_single_set(args.set_id, version=args.version if args.version != "both" else "international")

    elif args.version == "both":
        seed_both_versions(limit_sets=args.limit)

    else:
        seed_all_data(limit_sets=args.limit, version=args.version)
