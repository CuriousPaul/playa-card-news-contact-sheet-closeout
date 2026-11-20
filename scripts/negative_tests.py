#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["Pillow==12.0.0"]
# ///
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from contact_sheet_common import QA_GATES

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts/build_contact_sheets.py"
VERIFY = ROOT / "scripts/verify_final_set.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*args: object) -> subprocess.CompletedProcess:
    return subprocess.run([str(value) for value in args], capture_output=True, text=True)


def expect_fail(name: str, *args: object) -> None:
    result = command(*args)
    if result.returncode == 0:
        raise AssertionError(f"{name}: unexpectedly passed\n{result.stdout}")
    passed.append(name)


def write_ledger(root: Path, *, selected_parent: str = "selected") -> tuple[Path, dict]:
    source_dir = root / "source"
    selected_dir = root / selected_parent
    evidence_dir = root / "evidence"
    source_dir.mkdir(parents=True)
    selected_dir.mkdir(parents=True)
    evidence_dir.mkdir(parents=True)
    cards = []
    for number in (1, 2):
        source = source_dir / f"card-{number}.png"
        Image.new("RGB", (64, 64), (20 * number, 30 * number, 40 * number)).save(source)
        selected = source
        decision = "preserve_original"
        if number == 2:
            selected = selected_dir / "card-2-approved.png"
            Image.new("RGB", (64, 64), (210, 80, 90)).save(selected)
            decision = "use_approved_derivative"
        evidence = evidence_dir / f"card-{number}.json"
        approval_reference = f"negative-fixture-{number}"
        evidence.write_text(json.dumps({
            "schema": "playa-card-news-decision-evidence-v1",
            "card": number,
            "reviewer": "Kye",
            "status": "ACCEPTED",
            "approval_reference": approval_reference,
            "selected_sha256": sha(selected),
            "verbatim_human_decision": f"Fixture decision accepting card {number}.",
            "source_message_ref": f"fixture://negative/card/{number}",
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
                "canonical_source_mutated": False,
            }
        )
    ledger = {
        "schema": "playa-card-news-decision-ledger-v1",
        "set_id": "NEGATIVE-SET",
        "artifact_kind": "image_backgrounds",
        "fixture": True,
        "expected_card_count": 2,
        "expected_card_order": [1, 2],
        "columns": 2,
        "cards": cards,
    }
    path = root / "ledger.json"
    path.write_text(json.dumps(ledger, indent=2) + "\n")
    return path, ledger


def mutated_build_case(base: Path, name: str, mutate) -> None:
    root = base / name
    root.mkdir()
    ledger_path, ledger = write_ledger(root)
    mutate(ledger)
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")
    expect_fail(name, "uv", "run", "--script", BUILD, "--ledger", ledger_path, "--out", root / "out", "--allow-fixture")


passed: list[str] = []
with tempfile.TemporaryDirectory(prefix="playa-closeout-negative-") as directory:
    base = Path(directory).resolve()

    mutated_build_case(base, "wrong_order", lambda ledger: ledger.update(expected_card_order=[2, 1]))
    mutated_build_case(base, "wrong_ledger_schema", lambda ledger: ledger.update(schema="playa-card-news-decision-ledger-v0"))
    mutated_build_case(base, "invalid_columns_zero", lambda ledger: ledger.update(columns=0))
    mutated_build_case(base, "invalid_columns_too_large", lambda ledger: ledger.update(columns=9))
    mutated_build_case(base, "duplicate_card_collision", lambda ledger: ledger["cards"][1].update(card=1))
    mutated_build_case(base, "reviewer_not_allowlisted", lambda ledger: ledger["cards"][0].update(reviewer="Mallory"))
    mutated_build_case(base, "nonterminal_decision", lambda ledger: ledger["cards"][0].update(decision_status="PENDING"))
    mutated_build_case(base, "empty_evidence", lambda ledger: ledger["cards"][0].update(decision_evidence=[]))
    mutated_build_case(base, "fake_evidence_sha", lambda ledger: ledger["cards"][0]["decision_evidence"][0].update(evidence_sha256="0" * 64))
    mutated_build_case(base, "evidence_selected_sha_mismatch", lambda ledger: ledger["cards"][0]["decision_evidence"][0].update(selected_sha256="0" * 64))
    mutated_build_case(base, "invalid_evidence_type", lambda ledger: ledger["cards"][0]["decision_evidence"][0].update(type="filename_claim"))

    production_fixture_root = base / "fixture_evidence_in_production"
    production_fixture_root.mkdir()
    production_fixture_ledger_path, production_fixture_ledger = write_ledger(production_fixture_root)
    production_fixture_ledger["fixture"] = False
    production_fixture_ledger_path.write_text(json.dumps(production_fixture_ledger, indent=2) + "\n")
    expect_fail("fixture_evidence_in_production", "uv", "run", "--script", BUILD, "--ledger", production_fixture_ledger_path, "--out", production_fixture_root / "out")

    fixture_without_flag_root = base / "fixture_without_allow_flag"
    fixture_without_flag_root.mkdir()
    fixture_without_flag_ledger, _ = write_ledger(fixture_without_flag_root)
    expect_fail("fixture_without_allow_flag", "uv", "run", "--script", BUILD, "--ledger", fixture_without_flag_ledger, "--out", fixture_without_flag_root / "out")

    unstructured_root = base / "unstructured_decision_evidence"
    unstructured_root.mkdir()
    unstructured_ledger_path, unstructured_ledger = write_ledger(unstructured_root)
    evidence_path = Path(unstructured_ledger["cards"][0]["decision_evidence"][0]["path"])
    evidence_path.write_text("Kye ACCEPTED (fabricated plain text)\n")
    unstructured_ledger["cards"][0]["decision_evidence"][0]["evidence_sha256"] = sha(evidence_path)
    unstructured_ledger_path.write_text(json.dumps(unstructured_ledger, indent=2) + "\n")
    expect_fail("unstructured_decision_evidence", "uv", "run", "--script", BUILD, "--ledger", unstructured_ledger_path, "--out", unstructured_root / "out", "--allow-fixture")

    wrong_evidence_schema_root = base / "wrong_decision_evidence_schema"
    wrong_evidence_schema_root.mkdir()
    wrong_evidence_ledger_path, wrong_evidence_ledger = write_ledger(wrong_evidence_schema_root)
    evidence_path = Path(wrong_evidence_ledger["cards"][0]["decision_evidence"][0]["path"])
    evidence_data = json.loads(evidence_path.read_text())
    evidence_data["schema"] = "playa-card-news-decision-evidence-v0"
    evidence_path.write_text(json.dumps(evidence_data) + "\n")
    wrong_evidence_ledger["cards"][0]["decision_evidence"][0]["evidence_sha256"] = sha(evidence_path)
    wrong_evidence_ledger_path.write_text(json.dumps(wrong_evidence_ledger, indent=2) + "\n")
    expect_fail("wrong_decision_evidence_schema", "uv", "run", "--script", BUILD, "--ledger", wrong_evidence_ledger_path, "--out", wrong_evidence_schema_root / "out", "--allow-fixture")

    unsafe_root = base / "unsafe_path_component"
    unsafe_root.mkdir()
    unsafe_ledger, _ = write_ledger(unsafe_root, selected_parent="pending-review/approved")
    expect_fail("unsafe_path_component", "uv", "run", "--script", BUILD, "--ledger", unsafe_ledger, "--out", unsafe_root / "out", "--allow-fixture")

    existing_root = base / "preexisting_output"
    existing_root.mkdir()
    ledger_path, _ = write_ledger(existing_root)
    (existing_root / "out").mkdir()
    expect_fail("preexisting_output", "uv", "run", "--script", BUILD, "--ledger", ledger_path, "--out", existing_root / "out", "--allow-fixture")

    symlink_root = base / "output_symlink"
    symlink_root.mkdir()
    ledger_path, _ = write_ledger(symlink_root)
    (symlink_root / "target").mkdir()
    os.symlink(symlink_root / "target", symlink_root / "out")
    expect_fail("output_symlink", "uv", "run", "--script", BUILD, "--ledger", ledger_path, "--out", symlink_root / "out", "--allow-fixture")

    collision_root = base / "output_input_collision"
    collision_root.mkdir()
    ledger_path, _ = write_ledger(collision_root)
    expect_fail("output_input_collision", "uv", "run", "--script", BUILD, "--ledger", ledger_path, "--out", collision_root / "source", "--allow-fixture")

    valid_root = base / "verification_cases"
    valid_root.mkdir()
    ledger_path, _ = write_ledger(valid_root)
    output = valid_root / "out"
    build = command("uv", "run", "--script", BUILD, "--ledger", ledger_path, "--out", output, "--allow-fixture")
    assert build.returncode == 0, build.stderr
    manifest = json.loads((output / "MANIFEST.json").read_text())
    qa = {
        "schema": "playa-contact-sheet-visual-qa-v1",
        "reviewer": "Kye",
        "status": "PASS",
        "reviewed_sheet_sha256": manifest["sheets"]["final"]["sha256"],
        "source_message_ref": "fixture://negative/visual-qa",
        "verbatim_human_review": "Fixture review accepting all exhaustive gates.",
        "gates": {name: "PASS" for name in QA_GATES},
    }
    qa_path = valid_root / "qa.json"
    qa_path.write_text(json.dumps(qa) + "\n")

    def verify_fail(name: str, qa_file: Path = qa_path, *extra: object) -> None:
        expect_fail(name, "uv", "run", "--script", VERIFY, "--manifest", output / "MANIFEST.json", "--visual-qa", qa_file, *extra, "--report", valid_root / f"{name}-report.json")

    empty_qa = valid_root / "empty-gates.json"
    empty_data = copy.deepcopy(qa)
    empty_data["gates"] = {}
    empty_qa.write_text(json.dumps(empty_data))
    verify_fail("empty_visual_qa_gates", empty_qa)

    missing_qa = valid_root / "missing-gate.json"
    missing_data = copy.deepcopy(qa)
    missing_data["gates"].pop(QA_GATES[-1])
    missing_qa.write_text(json.dumps(missing_data))
    verify_fail("missing_visual_qa_gate", missing_qa)

    wrong_qa_schema = valid_root / "wrong-qa-schema.json"
    wrong_qa_data = copy.deepcopy(qa)
    wrong_qa_data["schema"] = "playa-contact-sheet-visual-qa-v0"
    wrong_qa_schema.write_text(json.dumps(wrong_qa_data))
    verify_fail("wrong_visual_qa_schema", wrong_qa_schema)

    unstructured_qa = valid_root / "unstructured-qa.txt"
    unstructured_qa.write_text("Kye says everything passes\n")
    verify_fail("unstructured_visual_qa", unstructured_qa)

    final_sheet = output / "final-contact-sheet.jpg"
    original_bytes = final_sheet.read_bytes()
    altered = Image.open(final_sheet).convert("RGB")
    altered.putpixel((0, 0), (255, 0, 0))
    altered.save(final_sheet, "JPEG", quality=95, subsampling=0)
    verify_fail("altered_contact_sheet")
    final_sheet.write_bytes(original_bytes)

    stale = output / "stale.txt"
    stale.write_text("stale")
    verify_fail("stale_extra_output")
    stale.unlink()

    extra_dir = output / "unexpected-empty-directory"
    extra_dir.mkdir()
    verify_fail("extra_empty_directory")
    extra_dir.rmdir()

    fifo = output / "unexpected.fifo"
    os.mkfifo(fifo)
    verify_fail("extra_fifo")
    fifo.unlink()

    symlink_extra = output / "cards" / "alias.png"
    os.symlink(output / "cards" / "card-01.png", symlink_extra)
    verify_fail("extra_output_symlink")
    symlink_extra.unlink()

    bad_approval = {
        "schema": "playa-contact-sheet-approval-v1",
        "reviewer": "Kye",
        "status": "ACCEPTED",
        "final_sheet_sha256": "0" * 64,
        "approval_reference": "negative-mismatch",
        "verbatim_human_approval": "Fixture approval of the exact final sheet.",
        "source_message_ref": "fixture://negative/approval",
    }
    bad_approval_path = valid_root / "bad-approval.json"
    bad_approval_path.write_text(json.dumps(bad_approval))
    verify_fail("approval_sha_mismatch", qa_path, "--authorization", "package", "--contact-sheet-approval", bad_approval_path)
    verify_fail("package_without_approval", qa_path, "--authorization", "package")

    unstructured_approval = valid_root / "unstructured-approval.txt"
    unstructured_approval.write_text("Kye ACCEPTED\n")
    verify_fail("unstructured_contact_sheet_approval", qa_path, "--authorization", "package", "--contact-sheet-approval", unstructured_approval)

    wrong_approval_schema_data = copy.deepcopy(bad_approval)
    wrong_approval_schema_data["schema"] = "playa-contact-sheet-approval-v0"
    wrong_approval_schema_data["final_sheet_sha256"] = manifest["sheets"]["final"]["sha256"]
    wrong_approval_schema = valid_root / "wrong-approval-schema.json"
    wrong_approval_schema.write_text(json.dumps(wrong_approval_schema_data))
    verify_fail("wrong_contact_sheet_approval_schema", qa_path, "--authorization", "package", "--contact-sheet-approval", wrong_approval_schema)

    valid_fixture_approval = copy.deepcopy(bad_approval)
    valid_fixture_approval["final_sheet_sha256"] = manifest["sheets"]["final"]["sha256"]
    valid_fixture_approval_path = valid_root / "valid-fixture-approval.json"
    valid_fixture_approval_path.write_text(json.dumps(valid_fixture_approval))
    verify_fail("fixture_manifest_package_rejected", qa_path, "--authorization", "package", "--contact-sheet-approval", valid_fixture_approval_path)

    canary = valid_root / "report-canary.txt"
    canary.write_bytes(b"REPORT-CANARY-UNCHANGED\n")
    canary_before = canary.read_bytes()
    report_symlink = valid_root / "report-symlink.json"
    os.symlink(canary, report_symlink)
    expect_fail("report_symlink_target", "uv", "run", "--script", VERIFY, "--manifest", output / "MANIFEST.json", "--visual-qa", qa_path, "--report", report_symlink)
    assert canary.read_bytes() == canary_before
    report_symlink.unlink()
    expect_fail("existing_regular_report", "uv", "run", "--script", VERIFY, "--manifest", output / "MANIFEST.json", "--visual-qa", qa_path, "--report", canary)
    assert canary.read_bytes() == canary_before

    tampered_manifest = json.loads((output / "MANIFEST.json").read_text())
    manifest_path = output / "MANIFEST.json"
    manifest_original = manifest_path.read_bytes()
    tampered_manifest["card_order"] = [2, 1]
    manifest_path.write_text(json.dumps(tampered_manifest))
    verify_fail("manifest_wrong_order")
    manifest_path.write_bytes(manifest_original)

print(json.dumps({"status": "PASS", "negative_cases": len(passed), "cases": passed}))
