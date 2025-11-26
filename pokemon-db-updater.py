import os
import requests
from datetime import datetime
from supabase import create_client, Client
from typing import Dict, List, Optional
import time

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
TCGDEX_BASE_URL = "https://api.tcgdex.net/v2/en"

# Initialize Supabase client (will be set later after validation)
supabase: Client = None


def fetch_all_sets() -> List[Dict]:
    """Fetch all Pokemon card sets from TCGdex API."""
    print("Fetching all sets...")
    response = requests.get(f"{TCGDEX_BASE_URL}/sets")
    response.raise_for_status()
    return response.json()


def fetch_set_details(set_id: str) -> Dict:
    """Fetch detailed information for a specific set."""
    print(f"Fetching set details for: {set_id}")
    response = requests.get(f"{TCGDEX_BASE_URL}/sets/{set_id}")
    response.raise_for_status()
    return response.json()


def fetch_cards_in_set(set_id: str) -> List[Dict]:
    """Fetch all cards in a specific set."""
    print(f"Fetching cards for set: {set_id}")
    response = requests.get(f"{TCGDEX_BASE_URL}/sets/{set_id}")
    response.raise_for_status()
    set_data = response.json()
    return set_data.get('cards', [])


def fetch_card_details(card_id: str) -> Dict:
    """Fetch detailed information for a specific card."""
    response = requests.get(f"{TCGDEX_BASE_URL}/cards/{card_id}")
    response.raise_for_status()
    return response.json()


def transform_set_data(set_data: Dict) -> Dict:
    """Transform TCGdex set data to match Supabase schema."""
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
        'updated_at': datetime.now().isoformat()
    }


def transform_card_data(card_data: Dict) -> Dict:
    """Transform TCGdex card data to match Supabase schema."""
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


def upsert_set(set_data: Dict) -> bool:
    """Insert or update a set in Supabase."""
    try:
        transformed_data = transform_set_data(set_data)
        supabase.table('pokemon_sets').upsert(transformed_data).execute()
        print(f"✓ Upserted set: {transformed_data['name']}")
        return True
    except Exception as e:
        print(f"✗ Error upserting set {set_data.get('id')}: {e}")
        return False


def upsert_card(card_data: Dict) -> bool:
    """Insert or update a card in Supabase."""
    try:
        transformed_data = transform_card_data(card_data)
        supabase.table('cards').upsert(transformed_data).execute()
        print(f"✓ Upserted card: {transformed_data['name']} ({transformed_data['id']})")
        return True
    except Exception as e:
        print(f"✗ Error upserting card {card_data.get('id')}: {e}")
        return False


def upsert_prices(card_id: str, pricing_data: Dict) -> int:
    """Insert or update card prices in Supabase."""
    if not pricing_data:
        return 0
    
    try:
        price_records = transform_price_data(card_id, pricing_data)
        
        if not price_records:
            return 0
        
        # Upsert all price records
        supabase.table('card_prices').upsert(price_records).execute()
        print(f"  ✓ Upserted {len(price_records)} price records for card {card_id}")
        return len(price_records)
    except Exception as e:
        print(f"  ✗ Error upserting prices for card {card_id}: {e}")
        return 0


def seed_all_data(limit_sets: Optional[int] = None):
    """
    Main function to seed all data from TCGdex to Supabase.
    
    Args:
        limit_sets: Optional limit on number of sets to process (for testing)
    """
    print("="*60)
    print("Starting TCGdex to Supabase seeding process")
    print("="*60)
    
    # Fetch all sets
    sets = fetch_all_sets()
    print(f"\nFound {len(sets)} sets")

    # Filter out Pokémon TCG Pocket sets (by name or id)
    def is_pocket_set(set_summary):
        name = (set_summary.get('name') or '').lower()
        set_id = (set_summary.get('id') or '').lower()
        # Exclude if 'pocket' in name or id
        return 'pocket' in name or 'pocket' in set_id

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
        print(f"\n[{i}/{len(sets)}] Processing set: {set_id}")

        try:
            # Fetch detailed set information
            set_details = fetch_set_details(set_id)
            # Check fetched set name/serie for 'pocket'
            name = (set_details.get('name') or '').lower()
            serie = set_details.get('serie')
            if isinstance(serie, dict):
                serie_name = (serie.get('name') or '').lower()
            else:
                serie_name = (serie or '').lower()
            if 'pocket' in name or 'pocket' in serie_name:
                print(f"Skipping set '{set_id}' (Pocket set detected by name or serie)")
                continue

            # Upsert set
            if upsert_set(set_details):
                sets_success += 1

            # Fetch and process all cards in the set
            cards = set_details.get('cards', [])
            print(f"Found {len(cards)} cards in set {set_id}")

            for j, card_summary in enumerate(cards, 1):
                card_id = card_summary.get('id')

                try:
                    # Fetch detailed card information
                    card_details = fetch_card_details(card_id)

                    # Upsert card
                    if upsert_card(card_details):
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
    print("Seeding Summary")
    print("="*60)
    print(f"Sets processed: {sets_success}/{len(sets)}")
    print(f"Cards succeeded: {cards_success}")
    print(f"Cards failed: {cards_failed}")
    print(f"Price records created: {prices_success}")
    print("="*60)


def seed_single_set(set_id: str):
    """Seed a single set and its cards (useful for testing)."""
    # Skip if set_id or set name contains 'pocket'
    if 'pocket' in (set_id or '').lower():
        print(f"Skipping set '{set_id}' (Pocket set detected)")
        return

    print(f"Seeding single set: {set_id}")

    try:
        # Fetch and upsert set
        set_details = fetch_set_details(set_id)
        # Also skip if set name or serie contains 'pocket'
        name = (set_details.get('name') or '').lower()
        serie = set_details.get('serie')
        if isinstance(serie, dict):
            serie_name = (serie.get('name') or '').lower()
        else:
            serie_name = (serie or '').lower()
        if 'pocket' in name or 'pocket' in serie_name:
            print(f"Skipping set '{set_id}' (Pocket set detected by name or serie)")
            return
        upsert_set(set_details)

        # Fetch and upsert cards
        cards = set_details.get('cards', [])
        print(f"Found {len(cards)} cards")

        for card_summary in cards:
            card_id = card_summary.get('id')
            card_details = fetch_card_details(card_id)
            upsert_card(card_details)

            # Upsert pricing data if available
            if 'pricing' in card_details:
                upsert_prices(card_id, card_details['pricing'])

            time.sleep(0.3)

        print(f"✓ Successfully seeded set {set_id}")

    except Exception as e:
        print(f"✗ Error seeding set {set_id}: {e}")


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
    
    # Example usage:
    # 1. Seed all data (this will take a while!)
    seed_all_data()
    
    # 2. Or seed a limited number of sets for testing
    # seed_all_data(limit_sets=2)
    
    # 3. Or seed a single set
    # seed_single_set("base1")