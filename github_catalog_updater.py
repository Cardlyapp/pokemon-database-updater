#!/usr/bin/env python3
"""Export Cardly card and set catalogs directly from their upstream APIs.

This script deliberately does not read Supabase or Neon. It reuses the source
fetching and normalization functions in pokemon-db-updater.py, then writes a
small set of bulk JSON files intended for the Cardly mobile app.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable


SCHEMA_VERSION = 2
REGIONS = {
    "international": "data",
    "japan": "data-asia",
}


def load_source_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("cardly_source_updater", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load source updater: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def is_pocket_set(row: dict[str, Any]) -> bool:
    set_id = str(row.get("id") or "").lower()
    name = str(row.get("name") or "").lower()
    series = row.get("serie") or row.get("series") or ""
    if isinstance(series, dict):
        series = series.get("name") or ""
    return "pocket" in set_id or "pocket" in name or "pocket" in str(series).lower()


def clean_export_row(row: dict[str, Any]) -> dict[str, Any]:
    # Source update timestamps make identical catalogs look different every run.
    # Publication time and content hashes belong in manifest.json instead.
    return {key: value for key, value in row.items() if key != "updated_at"}


def stable_id(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Missing {label} ID")
    return text


def export_region(
    source: ModuleType,
    version: str,
    output_root: Path,
    limit_sets: int | None = None,
    request_delay: float = 0.05,
) -> dict[str, Any]:
    directory_name = REGIONS[version]
    print(f"Fetching {version} sets directly from the upstream source...")
    summaries = source.fetch_all_sets(version)
    if not isinstance(summaries, list):
        raise RuntimeError(f"The {version} source did not return a set list")

    summaries = [row for row in summaries if isinstance(row, dict) and not is_pocket_set(row)]
    if limit_sets is not None:
        summaries = summaries[:limit_sets]
    if not summaries:
        raise RuntimeError(f"The {version} source returned no usable sets")

    sets: list[dict[str, Any]] = []
    cards: list[dict[str, Any]] = []
    prices: list[dict[str, Any]] = []
    seen_set_ids: set[str] = set()
    seen_card_ids: set[str] = set()

    for set_index, summary in enumerate(summaries, 1):
        summary_id = stable_id(summary.get("id"), "set")
        print(f"[{version} {set_index}/{len(summaries)}] Fetching set {summary_id}")
        details = source.fetch_set_details(summary_id, version)
        if not isinstance(details, dict):
            raise RuntimeError(f"Could not fetch complete details for {version} set {summary_id}")
        if is_pocket_set(details):
            continue

        source_name = source.detect_data_source(details)
        set_row = clean_export_row(source.transform_set_data(details, version, source_name))
        set_id = stable_id(set_row.get("id") or summary_id, "set")
        set_row["id"] = set_id
        if set_id in seen_set_ids:
            raise RuntimeError(f"Duplicate {version} set ID: {set_id}")
        seen_set_ids.add(set_id)

        card_summaries = (
            source.fetch_cards_in_set(summary_id, version)
            if version == "japan"
            else details.get("cards", [])
        )
        if not isinstance(card_summaries, list):
            raise RuntimeError(f"Set {set_id} did not return a card list")

        set_card_count = 0
        for card_index, card_summary in enumerate(card_summaries, 1):
            if not isinstance(card_summary, dict):
                raise RuntimeError(f"Set {set_id} returned an invalid card summary")
            card_source_id = stable_id(card_summary.get("id") or card_summary.get("uuid"), "card")
            local_id = card_summary.get("localId") or card_summary.get("local_id")
            details_card = source.fetch_card_details(
                card_source_id,
                version,
                set_id=summary_id,
                local_id=local_id,
            )
            if not isinstance(details_card, dict):
                raise RuntimeError(f"Could not fetch complete details for {version} card {card_source_id}")
            card_source = source.detect_data_source(details_card)
            card_row = clean_export_row(source.transform_card_data(details_card, version, card_source))
            card_id = stable_id(card_row.get("id") or card_source_id, "card")
            if card_id in seen_card_ids:
                raise RuntimeError(f"Duplicate {version} card ID: {card_id}")
            seen_card_ids.add(card_id)

            card_row["id"] = card_id
            card_row["set_id"] = set_id
            card_row["set_name"] = card_row.get("set_name") or set_row.get("name")
            card_row["version"] = version
            cards.append(card_row)
            pricing = details_card.get("pricing")
            if isinstance(pricing, dict):
                prices.extend(clean_export_row(row) for row in source.transform_price_data(card_id, pricing))
            set_card_count += 1

            if request_delay > 0:
                time.sleep(request_delay)
            if card_index % 100 == 0:
                print(f"  Fetched {card_index}/{len(card_summaries)} cards")

        set_row["card_count"] = set_card_count
        set_row["version"] = version
        sets.append(set_row)

    if not cards:
        raise RuntimeError(f"The {version} export contained no cards")
    unknown_set_ids = sorted({stable_id(card.get("set_id"), "card set") for card in cards} - seen_set_ids)
    if unknown_set_ids:
        raise RuntimeError(f"Cards reference unknown sets: {', '.join(unknown_set_ids[:10])}")

    sets.sort(key=lambda row: stable_id(row.get("id"), "set"))
    cards.sort(key=lambda row: stable_id(row.get("id"), "card"))
    region_dir = output_root / directory_name
    region_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(region_dir / "sets.json", sets)
    write_json_atomic(region_dir / "cards.json", cards)
    prices.sort(
        key=lambda row: (
            stable_id(row.get("card_id"), "price card"),
            str(row.get("market_source") or ""),
            str(row.get("condition") or ""),
            str(row.get("price_type") or ""),
        )
    )
    write_json_atomic(region_dir / "prices.json", prices)
    print(f"Captured {len(prices)} price rows for {version}")

    return {
        "version": version,
        "directory": directory_name,
        "setCount": len(sets),
        "cardCount": len(cards),
        "priceCount": len(prices),
        "sets": file_metadata(output_root, region_dir / "sets.json"),
        "cards": file_metadata(output_root, region_dir / "cards.json"),
        "prices": file_metadata(output_root, region_dir / "prices.json"),
    }


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(canonical_json_bytes(value))
    temporary.replace(path)


def file_metadata(root: Path, path: Path) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def content_version(regions: Iterable[dict[str, Any]]) -> str:
    hashes = [item[kind]["sha256"] for item in regions for kind in ("sets", "cards", "prices")]
    return hashlib.sha256("".join(hashes).encode("ascii")).hexdigest()


def existing_publication_time(output_root: Path, version: str) -> str | None:
    manifest_path = output_root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if manifest.get("version") == version:
        value = manifest.get("publishedAt")
        return value if isinstance(value, str) else None
    return None


def publish_manifest(output_root: Path, regions: list[dict[str, Any]]) -> dict[str, Any]:
    version = content_version(regions)
    published_at = existing_publication_time(output_root, version) or datetime.now(timezone.utc).isoformat()
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "version": version,
        "publishedAt": published_at,
        "regions": {region["version"]: region for region in regions},
    }
    write_json_atomic(output_root / "manifest.json", manifest)
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export cards and sets from upstream APIs for Cardly")
    parser.add_argument("--output", type=Path, required=True, help="Checked-out cards-database repository")
    parser.add_argument(
        "--source-module",
        type=Path,
        default=Path(__file__).with_name("pokemon-db-updater.py"),
        help="Path to pokemon-db-updater.py",
    )
    parser.add_argument("--region", choices=("both", "international", "japan"), default="both")
    parser.add_argument("--limit-sets", type=int, help="Testing only: export the first N sets")
    parser.add_argument("--request-delay", type=float, default=0.05)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.limit_sets is not None and args.limit_sets < 1:
        raise ValueError("--limit-sets must be at least 1")
    if args.request_delay < 0:
        raise ValueError("--request-delay cannot be negative")

    output_root = args.output.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    source = load_source_module(args.source_module.resolve())
    versions = REGIONS if args.region == "both" else (args.region,)
    regions = [
        export_region(source, version, output_root, args.limit_sets, args.request_delay)
        for version in versions
    ]
    manifest = publish_manifest(output_root, regions)
    print(
        f"Catalog {manifest['version'][:12]} ready: "
        + ", ".join(f"{row['version']}={row['cardCount']} cards" for row in regions)
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Export cancelled", file=sys.stderr)
        raise SystemExit(130)
