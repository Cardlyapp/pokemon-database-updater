import os
import re
import requests
from supabase import create_client, Client
from dotenv import load_dotenv
from tqdm import tqdm

# ---------------- CONFIG ----------------
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PRODUCTS_URL = "https://fatalmistake02.github.io/pokemon-products/products.json"
BATCH_SIZE = 50

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------- FETCH DATA ----------------
def fetch_products():
    """Fetch the full product list from the JSON source."""
    print(f"Fetching products from {PRODUCTS_URL}...")
    try:
        res = requests.get(PRODUCTS_URL, timeout=15)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"❌ Failed to fetch data: {e}")
        return []

def transform_product(item):
    """
    Map the JSON data to the Supabase table columns.
    Converts 'product-1' -> 1 to use as the Primary Key.
    """
    # Extract only digits from the id string (e.g., "product-123" -> "123")
    raw_id = item.get("id", "0")
    numeric_id = "".join(filter(str.isdigit, raw_id))
    
    return {
        "id": int(numeric_id) if numeric_id else None, # The script now provides the ID
        "name": item.get("name"),
        "type": item.get("type"),
        "release_date": item.get("release_date"),
        "tcgplayer_id": item.get("tcgplayer_id"), 
        "description": item.get("description"),
        "image_url": item.get("image_url"),
        "packs": item.get("packs"),      
        "promos": item.get("promos"),    
    }

# ---------------- UPSERT INTO SUPABASE ----------------
def upsert_products_batch(batch):
    try:
        # We remove on_conflict="tcgplayer_id" 
        # By default, .upsert() uses the primary key ('id').
        # Since we are providing the ID, it will update if ID exists or insert if it doesn't.
        supabase.table("products").upsert(batch).execute()
    except Exception as e:
        print(f"\n❌ Error during batch upsert: {e}")

# ---------------- MAIN ----------------
def main():
    raw_products = fetch_products()
    if not raw_products:
        print("No data found. Exiting.")
        return

    print(f"✅ Found {len(raw_products)} products.")

    # Transform the data
    processed_data = [transform_product(p) for p in raw_products]

    print(f"\n📤 Uploading to Supabase...")
    buffer = []
    
    with tqdm(total=len(processed_data), desc="Uploading products", unit="product") as pbar:
        for item in processed_data:
            # Skip items that didn't have a valid numeric ID
            if item["id"] is None:
                continue
                
            buffer.append(item)

            if len(buffer) >= BATCH_SIZE:
                upsert_products_batch(buffer)
                pbar.update(len(buffer))
                buffer.clear()

        if buffer:
            upsert_products_batch(buffer)
            pbar.update(len(buffer))

    print(f"\n🎉 Successfully imported {len(processed_data)} products!")

if __name__ == "__main__":
    main()
