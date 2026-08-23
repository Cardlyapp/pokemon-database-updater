import importlib.util
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests


MODULE_PATH = Path(__file__).parents[1] / "pokemon-db-updater.py"
SPEC = importlib.util.spec_from_file_location("pokemon_db_updater", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class CardDetailFetchTests(unittest.TestCase):
    def test_404_retries_with_encoded_set_and_local_id(self):
        missing = Mock(status_code=404)
        missing.raise_for_status.side_effect = requests.HTTPError("not found")
        found = Mock(status_code=200)
        found.raise_for_status.return_value = None
        found.json.return_value = {"id": "exu-?", "name": "Unown"}

        with patch.object(MODULE.requests, "get", side_effect=[missing, found]) as get:
            result = MODULE.fetch_card_details("exu-?", set_id="exu", local_id="?")

        self.assertEqual(result["id"], "exu-?")
        self.assertEqual(
            get.call_args_list[1].args[0],
            "https://api.tcgdex.net/v2/en/cards/exu-%253F",
        )

    def test_already_escaped_local_id_is_not_double_canonicalized(self):
        missing = Mock(status_code=404)
        missing.raise_for_status.side_effect = requests.HTTPError("not found")
        found = Mock(status_code=200)
        found.raise_for_status.return_value = None
        found.json.return_value = {"id": "exu-%3F", "name": "Unown"}

        with patch.object(MODULE.requests, "get", side_effect=[missing, found]) as get:
            MODULE.fetch_card_details("exu-%3F", set_id="exu", local_id="%3F")

        self.assertEqual(
            get.call_args_list[1].args[0],
            "https://api.tcgdex.net/v2/en/cards/exu-%253F",
        )

    def test_non_404_does_not_fall_back(self):
        failed = Mock(status_code=503)
        failed.raise_for_status.side_effect = requests.HTTPError("unavailable")

        with patch.object(MODULE.requests, "get", return_value=failed) as get:
            with self.assertRaises(requests.HTTPError):
                MODULE.fetch_card_details("exu-?", set_id="exu", local_id="?")

        get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
