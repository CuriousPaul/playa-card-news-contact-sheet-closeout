#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["Pillow==12.0.0"]
# ///
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import tempfile
from pathlib import Path
from typing import NoReturn, cast

import PIL
from PIL import ImageChops

from contact_sheet_common import (
    DECISION_EVIDENCE_KEYS,
    DECISION_EVIDENCE_SCHEMA,
    DECISION_EVIDENCE_TYPES,
    LEDGER_SCHEMA,
    MAX_COLUMNS,
    RENDERER_ID,
    REVIEWERS,
    is_relative_to,
    is_regular_file,
    load_exact_json,
    load_rgb,
    nonempty,
    path_has_unsafe_component,
    render_comparison,
    render_sheet,
    save_jpeg,
    sha256,
)


def fail(message: str) -> NoReturn:
    raise SystemExit(message)


def require_sha(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        fail(f"{label}: expected lowercase SHA256")
    return cast(str, value)


def validate_evidence(card: dict, selected_sha: str, fixture: bool) -> list[dict]:
    number = card["card"]
    if card.get("reviewer") not in REVIEWERS:
        fail(f"card {number}: reviewer must be Kye or Paul")
    if card.get("decision_status") != "ACCEPTED":
        fail(f"card {number}: decision_status must be terminal ACCEPTED")
    evidence = card.get("decision_evidence")
    if not isinstance(evidence, list) or not evidence:
        fail(f"card {number}: decision_evidence must be a non-empty list")
    evidence = cast(list[dict], evidence)
    record_keys = {"type", "path", "evidence_sha256", "selected_sha256", "approval_status", "approval_reference"}
    for index, record in enumerate(evidence):
        label = f"card {number} evidence {index}"
        if not isinstance(record, dict) or not record:
            fail(f"{label}: evidence must be a non-empty object")
        if set(record) != record_keys:
            fail(f"{label}: exact evidence ledger fields required")
        if record.get("type") not in DECISION_EVIDENCE_TYPES:
            fail(f"{label}: invalid evidence type")
        if record.get("type") == "fixture" and not fixture:
            fail(f"{label}: fixture evidence is forbidden in production")
        if record.get("approval_status") != "ACCEPTED":
            fail(f"{label}: approval_status must be ACCEPTED")
        if not isinstance(record.get("approval_reference"), str) or not record["approval_reference"].strip():
            fail(f"{label}: approval_reference is required")
        if record.get("selected_sha256") != selected_sha:
            fail(f"{label}: selected_sha256 does not bind selected pixels")
        path_value = record.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            fail(f"{label}: evidence path is required")
        evidence_sha = require_sha(record.get("evidence_sha256"), f"{label} evidence_sha256")
        evidence_path = Path(cast(str, path_value)).expanduser()
        try:
            resolved = evidence_path.resolve(strict=True)
            payload = load_exact_json(resolved, DECISION_EVIDENCE_KEYS)
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
            fail(f"{label}: invalid structured evidence: {exc}")
        if not is_regular_file(resolved) or sha256(resolved) != evidence_sha:
            fail(f"{label}: evidence file SHA mismatch")
        expected = {
            "schema": DECISION_EVIDENCE_SCHEMA,
            "card": number,
            "reviewer": card.get("reviewer"),
            "status": card.get("decision_status"),
            "approval_reference": record.get("approval_reference"),
            "selected_sha256": selected_sha,
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            fail(f"{label}: ledger fields do not exactly match evidence payload")
        if not nonempty(payload.get("verbatim_human_decision")) or not nonempty(payload.get("source_message_ref")):
            fail(f"{label}: verbatim human decision and source_message_ref are required")
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a fresh, immutable PLAYA contact-sheet review set")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--allow-fixture", action="store_true", help="permit fixture:true ledgers for tests only")
    args = parser.parse_args()

    ledger_path = Path(args.ledger).expanduser().resolve(strict=True)
    ledger = json.loads(ledger_path.read_text())
    if ledger.get("schema") != LEDGER_SCHEMA:
        fail(f"ledger.schema must be exactly {LEDGER_SCHEMA}")
    if ledger.get("fixture") is not True and ledger.get("fixture") is not False:
        fail("ledger.fixture must be exactly true or false")
    if ledger["fixture"] and not args.allow_fixture:
        fail("fixture ledger requires explicit --allow-fixture (tests only)")
    raw_out = Path(args.out).expanduser()
    if os.path.lexists(raw_out):
        fail("output must not pre-exist (files, directories, and symlinks are rejected)")
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    out = raw_out.resolve(strict=False)
    if out == Path(out.anchor):
        fail("refusing filesystem-root output")

    cards = ledger.get("cards")
    expected_count = ledger.get("expected_card_count")
    expected_order = ledger.get("expected_card_order")
    if not isinstance(cards, list) or not isinstance(expected_count, int) or expected_count <= 0:
        fail("cards and positive expected_card_count are required")
    if not isinstance(expected_order, list) or len(expected_order) != expected_count:
        fail("expected_card_order must be an exhaustive list")
    numbers = [card.get("card") for card in cards]
    if numbers != expected_order or len(cards) != expected_count or len(set(numbers)) != len(numbers):
        fail("cards must exactly equal expected_card_order with no duplicates")
    if any(not isinstance(number, int) or number <= 0 or number > 999 for number in numbers):
        fail("card numbers must be positive integers <= 999")
    columns = ledger.get("columns")
    if not isinstance(columns, int) or isinstance(columns, bool) or not 1 <= columns <= min(MAX_COLUMNS, expected_count):
        fail(f"columns must be an integer from 1 through min({MAX_COLUMNS}, card count)")
    if not isinstance(ledger.get("set_id"), str) or not ledger["set_id"].strip():
        fail("set_id is required")

    fixture = ledger.get("fixture") is True
    prepared: list[tuple[dict, Path, Path, object, object, bool]] = []
    input_hashes: dict[Path, str] = {ledger_path: sha256(ledger_path)}
    for card in cards:
        number = card["card"]
        try:
            source = Path(card["source_path"]).expanduser().resolve(strict=True)
            selected = Path(card["selected_path"]).expanduser().resolve(strict=True)
        except (KeyError, FileNotFoundError) as exc:
            fail(f"card {number}: missing source/selected: {exc}")
        if is_relative_to(source, out) or is_relative_to(selected, out):
            fail(f"card {number}: source/selected may not be under output")
        if not is_regular_file(source) or not is_regular_file(selected):
            fail(f"card {number}: source/selected must be regular files")
        if path_has_unsafe_component(selected):
            fail(f"card {number}: selected path has pending/rejected/blocked component")
        source_sha = require_sha(card.get("source_sha256"), f"card {number} source_sha256")
        selected_sha = require_sha(card.get("selected_sha256"), f"card {number} selected_sha256")
        if sha256(source) != source_sha or sha256(selected) != selected_sha:
            fail(f"card {number}: ledger SHA mismatch")
        evidence = validate_evidence(card, selected_sha, fixture)
        decision = card.get("decision")
        if decision not in {"preserve_original", "use_approved_derivative"}:
            fail(f"card {number}: invalid decision")
        if card.get("canonical_source_mutated") is not False:
            fail(f"card {number}: canonical_source_mutated must be false")
        source_image, selected_image = load_rgb(source), load_rgb(selected)
        if source_image.size != selected_image.size:
            fail(f"card {number}: source/selected dimensions differ")
        equal = ImageChops.difference(source_image, selected_image).getbbox() is None
        if (decision == "preserve_original") != equal:
            fail(f"card {number}: decision does not match source/selected pixel relation")
        prepared.append((card, source, selected, source_image, selected_image, equal))
        input_hashes[source] = source_sha
        input_hashes[selected] = selected_sha
        for record in evidence:
            evidence_path = Path(record["path"]).expanduser()
            if evidence_path.exists():
                resolved_evidence = evidence_path.resolve(strict=True)
                input_hashes[resolved_evidence] = sha256(resolved_evidence)

    temp_root = Path(tempfile.mkdtemp(prefix=f".{out.name}.fresh-", dir=out.parent))
    try:
        cards_dir = temp_root / "cards"
        cards_dir.mkdir()
        originals, finals, items, edited, preserved = [], [], [], [], []
        for card, source, selected, source_image, selected_image, equal in prepared:
            number = card["card"]
            destination = cards_dir / f"card-{number:02d}.png"
            selected_image.save(destination, "PNG", optimize=True)
            items.append(
                {
                    "card": number,
                    "decision": card["decision"],
                    "source_path": str(source),
                    "source_sha256": sha256(source),
                    "selected_path": str(selected),
                    "selected_sha256": sha256(selected),
                    "final_path": str(out / "cards" / destination.name),
                    "final_sha256": sha256(destination),
                    "dimensions": list(selected_image.size),
                    "pixel_equal_to_source": equal,
                    "reviewer": card["reviewer"],
                    "decision_status": card["decision_status"],
                    "decision_evidence": card["decision_evidence"],
                    "canonical_source_mutated": card["canonical_source_mutated"],
                    "character_id": card.get("character_id"),
                    "same_source_person_group": card.get("same_source_person_group"),
                }
            )
            originals.append(source_image)
            finals.append(selected_image)
            (preserved if equal else edited).append(number)

        labels = [f"CARD {number:02d}" for number in numbers]
        original_sheet = render_sheet(originals, labels, f"{ledger['set_id']} · ORIGINAL", columns)
        final_sheet = render_sheet(finals, labels, f"{ledger['set_id']} · FINAL", columns)
        comparison = render_comparison(original_sheet, final_sheet)
        sheet_images = {"original": original_sheet, "final": final_sheet, "comparison": comparison}
        sheet_names = {
            "original": "original-contact-sheet.jpg",
            "final": "final-contact-sheet.jpg",
            "comparison": "original-vs-final-contact-sheet.jpg",
        }
        sheets = {}
        for kind, image in sheet_images.items():
            path = temp_root / sheet_names[kind]
            save_jpeg(image, path)
            sheets[kind] = {"path": str(out / path.name), "sha256": sha256(path), "dimensions": list(image.size)}

        expected_inventory = sorted(
            ["MANIFEST.json", *sheet_names.values(), *(f"cards/card-{number:02d}.png" for number in numbers)]
        )
        manifest = {
            "schema": "playa-card-news-final-set-v2",
            "set_id": ledger["set_id"],
            "artifact_kind": ledger.get("artifact_kind", "unspecified"),
            "status": "CONTACT_SHEET_VISUAL_QA_PENDING",
            "item_count": len(items),
            "expected_card_order": expected_order,
            "card_order": numbers,
            "columns": columns,
            "edited_cards": edited,
            "preserved_cards": preserved,
            "items": items,
            "sheets": sheets,
            "ledger_path": str(ledger_path),
            "ledger_sha256": sha256(ledger_path),
            "canonical_sources_mutated": False,
            "renderer": {
                "id": RENDERER_ID,
                "python": platform.python_version(),
                "pillow": PIL.__version__,
                "scope": "byte/pixel deterministic for identical inputs in this pinned Pillow 12.0.0 runtime; libjpeg/platform are recorded, not claimed cross-environment identical",
                "platform": platform.platform(),
            },
            "expected_build_inventory": expected_inventory,
            "packaging_allowed": False,
            "zip_allowed": False,
            "fixture": fixture,
        }
        (temp_root / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        for path, before in input_hashes.items():
            if not path.is_file() or sha256(path) != before:
                fail(f"input mutated during build: {path}")
        if os.path.lexists(out):
            fail("output appeared during build; refusing overwrite")
        temp_root.rename(out)
    except BaseException:
        if temp_root.exists():
            shutil.rmtree(temp_root)
        raise

    print(json.dumps({"status": "BUILT", "out": str(out), "cards": len(items), "edited": edited, "preserved": preserved}))


if __name__ == "__main__":
    main()
