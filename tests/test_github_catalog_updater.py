import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "github_catalog_updater.py"
SPEC = importlib.util.spec_from_file_location("github_catalog_updater", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class FakeSource:
    def fetch_all_sets(self, version):
        return [{"id": "set-1", "name": "First Set"}]

    def fetch_set_details(self, set_id, version):
        return {"id": set_id, "name": "First Set", "cards": [{"id": "card-1"}]}

    def fetch_cards_in_set(self, set_id, version):
        return [{"id": "card-1"}]

    def fetch_card_details(self, card_id, version, set_id=None, local_id=None):
        return {"id": card_id, "name": "Pikachu", "pricing": {"market": 1}}

    def detect_data_source(self, row):
        return "fake"

    def transform_set_data(self, row, version, source):
        return {"id": row["id"], "name": row["name"], "version": version, "updated_at": "changes"}

    def transform_card_data(self, row, version, source):
        return {"id": row["id"], "name": row["name"], "set_id": None, "version": version, "updated_at": "changes"}

    def transform_price_data(self, card_id, pricing):
        return [{"card_id": card_id, "market_source": "fake", "price_type": "normal", "updated_at": "changes"}]


class CatalogExportTests(unittest.TestCase):
    def test_export_writes_bulk_files_and_stable_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            region = MODULE.export_region(FakeSource(), "international", root, request_delay=0)
            manifest = MODULE.publish_manifest(root, [region])

            sets = json.loads((root / "data" / "sets.json").read_text(encoding="utf-8"))
            cards = json.loads((root / "data" / "cards.json").read_text(encoding="utf-8"))
            self.assertEqual(sets[0]["card_count"], 1)
            self.assertEqual(cards[0]["set_id"], "set-1")
            self.assertNotIn("updated_at", sets[0])
            self.assertNotIn("updated_at", cards[0])
            self.assertNotIn("pricing", cards[0])
            self.assertEqual(manifest["regions"]["international"]["cardCount"], 1)
            prices = json.loads((root / "data" / "prices.json").read_text(encoding="utf-8"))
            self.assertEqual(prices[0]["card_id"], "card-1")
            self.assertNotIn("updated_at", prices[0])
            self.assertEqual(manifest["regions"]["international"]["priceCount"], 1)
            self.assertEqual(manifest["schemaVersion"], 2)

            second = MODULE.publish_manifest(root, [region])
            self.assertEqual(second["version"], manifest["version"])
            self.assertEqual(second["publishedAt"], manifest["publishedAt"])

    def test_price_only_export_preserves_cards_sets_and_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            region_dir = root / "data"
            region_dir.mkdir()
            sets = [{"id": "set-1", "name": "First Set"}]
            cards = [{"id": "card-1", "set_id": "set-1", "local_id": "1"}]
            MODULE.write_json_atomic(region_dir / "sets.json", sets)
            MODULE.write_json_atomic(region_dir / "cards.json", cards)
            MODULE.write_json_atomic(region_dir / "prices.json", [])
            initial_region = {
                "version": "international",
                "directory": "data",
                "setCount": 1,
                "cardCount": 1,
                "priceCount": 0,
                "sets": MODULE.file_metadata(root, region_dir / "sets.json"),
                "cards": MODULE.file_metadata(root, region_dir / "cards.json"),
                "prices": MODULE.file_metadata(root, region_dir / "prices.json"),
            }
            MODULE.publish_manifest(root, [initial_region], "v2.47.0")
            original_sets = (region_dir / "sets.json").read_bytes()
            original_cards = (region_dir / "cards.json").read_bytes()

            region = MODULE.export_region_prices(FakeSource(), "international", root, request_delay=0)
            manifest = MODULE.publish_manifest(root, [region])

            self.assertEqual((region_dir / "sets.json").read_bytes(), original_sets)
            self.assertEqual((region_dir / "cards.json").read_bytes(), original_cards)
            self.assertEqual(manifest["tcgdexRelease"], "v2.47.0")
            self.assertEqual(manifest["regions"]["international"]["priceCount"], 1)


if __name__ == "__main__":
    unittest.main()
