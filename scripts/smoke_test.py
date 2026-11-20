#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["Pillow==12.0.0"]
# ///
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from contact_sheet_common import QA_GATES

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts/build_contact_sheets.py"
VERIFY = ROOT / "scripts/verify_final_set.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args: object) -> None:
    subprocess.run([str(value) for value in args], check=True)


with tempfile.TemporaryDirectory(prefix="playa-closeout-smoke-") as directory:
    # macOS exposes /var as a symlink; resolve the fixture root so report-parent
    # symlink rejection is exercised without making every test path unsafe.
    root = Path(directory).resolve()
    source_dir, selected_dir, evidence_dir = root / "src", root / "selected", root / "evidence"
    source_dir.mkdir()
    selected_dir.mkdir()
    evidence_dir.mkdir()
    cards = []
    for number in range(1, 9):
        image = Image.new("RGB", (320, 320), (20 * number, 35 * number % 255, 55 * number % 255))
        ImageDraw.Draw(image).text((20, 20), f"SOURCE {number}", fill="white")
        source = source_dir / f"card-{number:02d}.png"
        image.save(source)
        decision = "use_approved_derivative" if number in (2, 5, 6, 7) else "preserve_original"
        selected = source
        if decision == "use_approved_derivative":
            edited = image.copy()
            ImageDraw.Draw(edited).ellipse((110, 80, 210, 190), fill=(240, 170, 130))
            selected = selected_dir / f"card-{number:02d}-approved.png"
            edited.save(selected)
        evidence = evidence_dir / f"card-{number:02d}-acceptance.json"
        approval_reference = f"smoke-card-{number}"
        evidence.write_text(json.dumps({
            "schema": "playa-card-news-decision-evidence-v1",
            "card": number,
            "reviewer": "Kye",
            "status": "ACCEPTED",
            "approval_reference": approval_reference,
            "selected_sha256": sha(selected),
            "verbatim_human_decision": f"Fixture decision: accept card {number}.",
            "source_message_ref": f"fixture://smoke/card/{number}",
        }, indent=2) + "\n")
        cards.append(
            {
                "card": number,
                "source_path": str(source),
                "source_sha256": sha(source),
                "decision": decision,
                "selected_path": str(selected),
                "selected_sha256": sha(selected),
                "reviewer": "Kye",
                "decision_status": "ACCEPTED",
                "decision_evidence": [
                    {
                        "type": "fixture",
                        "path": str(evidence),
                        "evidence_sha256": sha(evidence),
                        "selected_sha256": sha(selected),
                        "approval_status": "ACCEPTED",
                        "approval_reference": approval_reference,
                    }
                ],
                "character_id": f"CHAR-{number}@v1" if decision != "preserve_original" else None,
                "same_source_person_group": None,
                "reason": "smoke",
                "canonical_source_mutated": False,
            }
        )
    ledger = {
        "schema": "playa-card-news-decision-ledger-v1",
        "set_id": "SMOKE-SET",
        "artifact_kind": "image_backgrounds",
        "fixture": True,
        "expected_card_count": 8,
        "expected_card_order": list(range(1, 9)),
        "columns": 4,
        "cards": cards,
    }
    ledger_path = root / "ledger.json"
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")
    output = root / "out"
    run("uv", "run", "--script", BUILD, "--ledger", ledger_path, "--out", output, "--allow-fixture")
    manifest = json.loads((output / "MANIFEST.json").read_text())

    qa = {
        "schema": "playa-contact-sheet-visual-qa-v1",
        "reviewer": "Kye",
        "status": "PASS",
        "reviewed_sheet_sha256": manifest["sheets"]["final"]["sha256"],
        "source_message_ref": "fixture://smoke/visual-qa",
        "verbatim_human_review": "Fixture review: all exhaustive visual gates pass.",
        "gates": {name: "PASS" for name in QA_GATES},
    }
    qa_path = root / "VISUAL_QA.json"
    qa_path.write_text(json.dumps(qa, indent=2) + "\n")
    review_report = root / "review-verification.json"
    run("uv", "run", "--script", VERIFY, "--manifest", output / "MANIFEST.json", "--visual-qa", qa_path, "--authorization", "review", "--report", review_report)
    review = json.loads(review_report.read_text())
    assert review["status"] == "PASS" and review["packaging_allowed"] is False

    approval = {
        "schema": "playa-contact-sheet-approval-v1",
        "reviewer": "Kye",
        "status": "ACCEPTED",
        "final_sheet_sha256": manifest["sheets"]["final"]["sha256"],
        "approval_reference": "smoke-contact-sheet-approval",
        "verbatim_human_approval": "Fixture approval: accept this exact final contact sheet.",
        "source_message_ref": "fixture://smoke/contact-sheet-approval",
    }
    approval_path = root / "CONTACT_SHEET_APPROVAL.json"
    approval_path.write_text(json.dumps(approval, indent=2) + "\n")
    package_report = root / "package-verification.json"
    package_result = subprocess.run(["uv", "run", "--script", str(VERIFY), "--manifest", str(output / "MANIFEST.json"), "--visual-qa", str(qa_path), "--contact-sheet-approval", str(approval_path), "--authorization", "package", "--report", str(package_report)])
    assert package_result.returncode != 0
    package = json.loads(package_report.read_text())
    assert package["status"] == "FAIL" and package["packaging_allowed"] is False and package["zip_allowed"] is False

    # Also exercise the positive production authorization path. These are
    # synthetic test records, but they deliberately use production schemas and
    # types rather than the fixture marker.
    production_ledger = json.loads(ledger_path.read_text())
    production_ledger["fixture"] = False
    for card in production_ledger["cards"]:
        card["decision_evidence"][0]["type"] = "preserve_record" if card["decision"] == "preserve_original" else "human_selection"
    production_ledger_path = root / "production-shaped-ledger.json"
    production_ledger_path.write_text(json.dumps(production_ledger, indent=2) + "\n")
    production_output = root / "production-out"
    run("uv", "run", "--script", BUILD, "--ledger", production_ledger_path, "--out", production_output)
    production_manifest = json.loads((production_output / "MANIFEST.json").read_text())
    production_qa = dict(qa)
    production_qa["reviewed_sheet_sha256"] = production_manifest["sheets"]["final"]["sha256"]
    production_qa_path = root / "PRODUCTION_VISUAL_QA.json"
    production_qa_path.write_text(json.dumps(production_qa, indent=2) + "\n")
    production_approval = dict(approval)
    production_approval["final_sheet_sha256"] = production_manifest["sheets"]["final"]["sha256"]
    production_approval_path = root / "PRODUCTION_CONTACT_SHEET_APPROVAL.json"
    production_approval_path.write_text(json.dumps(production_approval, indent=2) + "\n")
    production_package_report = root / "production-package-verification.json"
    run("uv", "run", "--script", VERIFY, "--manifest", production_output / "MANIFEST.json", "--visual-qa", production_qa_path, "--contact-sheet-approval", production_approval_path, "--authorization", "package", "--report", production_package_report)
    production_package = json.loads(production_package_report.read_text())
    assert production_package["status"] == "PASS" and production_package["packaging_allowed"] is True and production_package["zip_allowed"] is True
    assert manifest["edited_cards"] == [2, 5, 6, 7] and manifest["preserved_cards"] == [1, 3, 4, 8]
    print(json.dumps({"status": "PASS", "review_checks": review["checks_total"], "fixture_package_rejected": True, "fixture_package_checks": package["checks_total"], "production_package_checks": production_package["checks_total"], "production_packaging_allowed": True, "edited": manifest["edited_cards"], "preserved": manifest["preserved_cards"]}))
