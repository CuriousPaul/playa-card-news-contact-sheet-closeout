#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["Pillow==12.0.0"]
# ///
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import stat
from pathlib import Path

import PIL
from PIL import Image, ImageChops

from contact_sheet_common import (
    CONTACT_SHEET_APPROVAL_KEYS,
    CONTACT_SHEET_APPROVAL_SCHEMA,
    DECISION_EVIDENCE_KEYS,
    DECISION_EVIDENCE_SCHEMA,
    DECISION_EVIDENCE_TYPES,
    LEDGER_SCHEMA,
    MAX_COLUMNS,
    QA_GATES,
    RENDERER_ID,
    REVIEWERS,
    VISUAL_QA_KEYS,
    VISUAL_QA_SCHEMA,
    expected_sheet_size,
    is_relative_to,
    is_regular_file,
    jpeg_bytes,
    load_exact_json,
    load_rgb,
    nonempty,
    path_has_unsafe_component,
    render_comparison,
    render_sheet,
    sha256,
    valid_sha,
)


def decoded_jpeg(image) -> Image.Image:
    with Image.open(io.BytesIO(jpeg_bytes(image))) as decoded:
        return decoded.convert("RGB")


def pixels_equal(left: Image.Image, right: Image.Image) -> bool:
    return left.size == right.size and ImageChops.difference(left, right).getbbox() is None


def prepare_new_report(raw: Path) -> tuple[Path, int, str]:
    if os.path.lexists(raw):
        raise ValueError("report path already exists (regular, symlink, or special)")
    absolute = Path(os.path.abspath(raw))
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    parent_fd = os.open(absolute.anchor, directory_flags)
    traversed = Path(absolute.anchor)
    try:
        for name in absolute.parent.parts[1:]:
            traversed /= name
            try:
                mode = os.stat(name, dir_fd=parent_fd, follow_symlinks=False).st_mode
            except FileNotFoundError:
                os.mkdir(name, mode=0o700, dir_fd=parent_fd)
                mode = os.stat(name, dir_fd=parent_fd, follow_symlinks=False).st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise ValueError(f"report parent component is not a real directory: {traversed}")
            child_fd = os.open(name, directory_flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = child_fd
        try:
            os.stat(absolute.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValueError("report path appeared while preparing parent")
        return absolute, parent_fd, absolute.name
    except BaseException:
        os.close(parent_fd)
        raise


def write_new_report(parent_fd: int, name: str, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(fd)


def main() -> None:
    parser = argparse.ArgumentParser(description="Independently verify a PLAYA contact-sheet set")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--visual-qa", required=True)
    parser.add_argument("--contact-sheet-approval")
    parser.add_argument("--authorization", choices=("review", "package"), default="review")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve(strict=True)
    output_root = manifest_path.parent
    raw_report = Path(args.report).expanduser()
    report_candidate = Path(os.path.abspath(raw_report))
    if is_relative_to(report_candidate, output_root):
        print(json.dumps({"status": "FAIL", "error": "report must be outside immutable build output"}))
        raise SystemExit(2)
    try:
        report_path, report_parent_fd, report_name = prepare_new_report(raw_report)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}))
        raise SystemExit(2)
    checks: list[dict] = []
    input_hashes: dict[Path, str] = {manifest_path: sha256(manifest_path)}

    def bind_input(path: Path) -> None:
        if not is_regular_file(path):
            raise ValueError(f"input is not a regular file: {path}")
        input_hashes.setdefault(path, sha256(path))

    def check(name: str, ok: bool, detail=None) -> None:
        checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    check("report_outside_build_output", not is_relative_to(report_path, output_root), str(report_path))
    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception as exc:
        manifest = {}
        check("manifest_parse", False, str(exc))
    else:
        check("manifest_parse", True)

    items = manifest.get("items", []) if isinstance(manifest.get("items"), list) else []
    order = manifest.get("card_order")
    expected_order = manifest.get("expected_card_order")
    columns = manifest.get("columns")
    check("manifest_schema", manifest.get("schema") == "playa-card-news-final-set-v2")
    check("item_count", isinstance(manifest.get("item_count"), int) and manifest.get("item_count") == len(items) > 0)
    check("expected_card_order_exact", expected_order == order == [item.get("card") for item in items] and len(set(order or [])) == len(order or []))
    check("columns_bounded", isinstance(columns, int) and not isinstance(columns, bool) and 1 <= columns <= min(MAX_COLUMNS, len(items)))
    check("canonical_immutable", manifest.get("canonical_sources_mutated") is False)
    check("fixture_marker_exact", manifest.get("fixture") is True or manifest.get("fixture") is False)
    renderer = manifest.get("renderer", {})
    check("renderer_environment", renderer.get("id") == RENDERER_ID and renderer.get("pillow") == PIL.__version__ == "12.0.0", renderer)

    ledger_ok = False
    ledger = {}
    try:
        ledger_path = Path(manifest["ledger_path"]).resolve(strict=True)
        bind_input(ledger_path)
        ledger = json.loads(ledger_path.read_text())
        ledger_ok = sha256(ledger_path) == manifest.get("ledger_sha256") and ledger.get("schema") == LEDGER_SCHEMA
    except Exception:
        pass
    check("ledger_binding", ledger_ok)
    if ledger_ok:
        check("ledger_expected_order", ledger.get("expected_card_order") == order and [c.get("card") for c in ledger.get("cards", [])] == order)
        check("ledger_columns", ledger.get("columns") == columns)
        check("ledger_fixture_marker", ledger.get("fixture") == manifest.get("fixture") and (ledger.get("fixture") is True or ledger.get("fixture") is False))

    originals, finals, final_hashes = [], [], []
    for item in items:
        number = item.get("card", 0)
        prefix = f"card{number:02d}"
        try:
            source = Path(item["source_path"]).resolve(strict=True)
            selected = Path(item["selected_path"]).resolve(strict=True)
            final = Path(item["final_path"]).resolve(strict=True)
            bind_input(source)
            bind_input(selected)
            bind_input(final)
            expected_final = (output_root / "cards" / f"card-{number:02d}.png").resolve(strict=True)
            files_ok = all(path.is_file() for path in (source, selected, final)) and final == expected_final
        except Exception as exc:
            files_ok = False
            check(f"{prefix}_files", False, str(exc))
            continue
        check(f"{prefix}_files", files_ok)
        if not files_ok:
            continue
        check(f"{prefix}_inputs_outside_output", not is_relative_to(source, output_root) and not is_relative_to(selected, output_root))
        check(f"{prefix}_safe_selected_path", not path_has_unsafe_component(selected), str(selected))
        source_image, selected_image, final_image = load_rgb(source), load_rgb(selected), load_rgb(final)
        relation_equal = pixels_equal(source_image, final_image)
        decision = item.get("decision")
        check(f"{prefix}_dimensions", source_image.size == selected_image.size == final_image.size and list(final_image.size) == item.get("dimensions"))
        check(f"{prefix}_selected_pixels", pixels_equal(selected_image, final_image))
        check(f"{prefix}_source_relation", decision in {"preserve_original", "use_approved_derivative"} and relation_equal == (decision == "preserve_original"))
        check(
            f"{prefix}_sha",
            sha256(source) == item.get("source_sha256")
            and sha256(selected) == item.get("selected_sha256")
            and sha256(final) == item.get("final_sha256"),
        )
        check(f"{prefix}_reviewer_status", item.get("reviewer") in REVIEWERS and item.get("decision_status") == "ACCEPTED")
        ledger_card = next((card for card in ledger.get("cards", []) if card.get("card") == number), None) if ledger_ok else None
        ledger_fields = ("decision", "source_sha256", "selected_sha256", "reviewer", "decision_status", "decision_evidence", "canonical_source_mutated")
        check(
            f"{prefix}_ledger_decision_binding",
            isinstance(ledger_card, dict) and all(ledger_card.get(field) == item.get(field) for field in ledger_fields),
        )
        evidence = item.get("decision_evidence")
        evidence_ok = isinstance(evidence, list) and bool(evidence)
        record_keys = {"type", "path", "evidence_sha256", "selected_sha256", "approval_status", "approval_reference"}
        if evidence_ok:
            for record in evidence:
                if not isinstance(record, dict) or set(record) != record_keys:
                    evidence_ok = False
                    break
                evidence_ok = evidence_ok and record.get("type") in DECISION_EVIDENCE_TYPES
                evidence_ok = evidence_ok and not (record.get("type") == "fixture" and manifest.get("fixture") is not True)
                evidence_ok = evidence_ok and record.get("approval_status") == "ACCEPTED"
                evidence_ok = evidence_ok and isinstance(record.get("approval_reference"), str) and bool(record["approval_reference"].strip())
                evidence_ok = evidence_ok and record.get("selected_sha256") == item.get("selected_sha256")
                evidence_ok = evidence_ok and valid_sha(record.get("evidence_sha256"))
                try:
                    evidence_path = Path(str(record.get("path", ""))).expanduser().resolve(strict=True)
                    bind_input(evidence_path)
                    payload = load_exact_json(evidence_path, DECISION_EVIDENCE_KEYS)
                except Exception:
                    evidence_ok = False
                    break
                expected_payload = {
                    "schema": DECISION_EVIDENCE_SCHEMA,
                    "card": number,
                    "reviewer": item.get("reviewer"),
                    "status": item.get("decision_status"),
                    "approval_reference": record.get("approval_reference"),
                    "selected_sha256": item.get("selected_sha256"),
                }
                evidence_ok = evidence_ok and sha256(evidence_path) == record.get("evidence_sha256")
                evidence_ok = evidence_ok and all(payload.get(key) == value for key, value in expected_payload.items())
                evidence_ok = evidence_ok and nonempty(payload.get("verbatim_human_decision")) and nonempty(payload.get("source_message_ref"))
        check(f"{prefix}_decision_evidence", bool(evidence_ok))
        originals.append(source_image)
        finals.append(final_image)
        final_hashes.append(sha256(final))
    check("unique_final_cards", len(final_hashes) == len(items) and len(set(final_hashes)) == len(final_hashes))

    sheets = manifest.get("sheets", {})
    sheets_ok = len(originals) == len(items) and isinstance(columns, int) and columns > 0
    if sheets_ok:
        labels = [f"CARD {number:02d}" for number in order]
        expected_original = render_sheet(originals, labels, f"{manifest.get('set_id')} · ORIGINAL", columns)
        expected_final = render_sheet(finals, labels, f"{manifest.get('set_id')} · FINAL", columns)
        expected_comparison = render_comparison(expected_original, expected_final)
        expected_images = {
            "original": decoded_jpeg(expected_original),
            "final": decoded_jpeg(expected_final),
            "comparison": decoded_jpeg(expected_comparison),
        }
        expected_names = {
            "original": "original-contact-sheet.jpg",
            "final": "final-contact-sheet.jpg",
            "comparison": "original-vs-final-contact-sheet.jpg",
        }
        base_size = expected_sheet_size(len(items), columns)
        expected_sizes = {"original": base_size, "final": base_size, "comparison": (base_size[0], base_size[1] * 2)}
        for kind, expected_image in expected_images.items():
            record = sheets.get(kind, {})
            try:
                path = Path(record["path"]).resolve(strict=True)
                bind_input(path)
                actual = load_rgb(path)
                ok = path == (output_root / expected_names[kind]).resolve(strict=True)
                ok = ok and actual.size == expected_sizes[kind] and record.get("dimensions") == list(expected_sizes[kind])
                ok = ok and sha256(path) == record.get("sha256") and pixels_equal(actual, expected_image)
            except Exception:
                ok = False
            check(f"sheet_{kind}_independent_render", ok, {"expected_dimensions": expected_sizes[kind]})
    else:
        for kind in ("original", "final", "comparison"):
            check(f"sheet_{kind}_independent_render", False, "cards/columns unavailable")

    expected_inventory = sorted(
        [
            "MANIFEST.json",
            "original-contact-sheet.jpg",
            "final-contact-sheet.jpg",
            "original-vs-final-contact-sheet.jpg",
            *(f"cards/card-{number:02d}.png" for number in (order or [])),
        ]
    )
    actual_inventory: list[str] = []
    actual_dirs: list[str] = []
    inventory_bad_types: list[str] = []

    def inventory(directory: Path) -> None:
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                relative = path.relative_to(output_root).as_posix()
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISDIR(mode):
                    actual_dirs.append(relative)
                    inventory(path)
                elif stat.S_ISREG(mode):
                    actual_inventory.append(relative)
                else:
                    inventory_bad_types.append(relative)

    inventory(output_root)
    actual_inventory.sort()
    actual_dirs.sort()
    check("manifest_inventory_declaration", manifest.get("expected_build_inventory") == expected_inventory)
    check(
        "exact_output_inventory",
        actual_inventory == expected_inventory and actual_dirs == ["cards"] and not inventory_bad_types,
        {"actual_files": actual_inventory, "actual_dirs": actual_dirs, "bad_types": inventory_bad_types, "expected": expected_inventory},
    )

    qa_path: Path | None = None
    try:
        qa_path = Path(args.visual_qa).expanduser().resolve(strict=True)
        bind_input(qa_path)
        qa = load_exact_json(qa_path, VISUAL_QA_KEYS)
        gates = qa.get("gates")
        qa_ok = (
            qa.get("schema") == VISUAL_QA_SCHEMA
            and qa.get("reviewer") in REVIEWERS
            and qa.get("status") == "PASS"
            and nonempty(qa.get("source_message_ref"))
            and nonempty(qa.get("verbatim_human_review"))
        )
        qa_binding = qa.get("reviewed_sheet_sha256") == sheets.get("final", {}).get("sha256")
        gates_ok = isinstance(gates, dict) and set(gates) == set(QA_GATES) and all(gates[name] == "PASS" for name in QA_GATES)
    except Exception as exc:
        qa_ok = qa_binding = gates_ok = False
        check("visual_qa_parse", False, str(exc))
    else:
        check("visual_qa_parse", True)
    check("visual_qa_status", qa_ok)
    check("visual_qa_sheet_binding", qa_binding)
    check("visual_qa_exhaustive_named_gates", gates_ok, list(QA_GATES))

    approval_valid = False
    approval_sha = None
    if args.contact_sheet_approval:
        try:
            approval_path = Path(args.contact_sheet_approval).expanduser().resolve(strict=True)
            bind_input(approval_path)
            approval = load_exact_json(approval_path, CONTACT_SHEET_APPROVAL_KEYS)
            approval_sha = sha256(approval_path)
            approval_valid = (
                approval.get("schema") == CONTACT_SHEET_APPROVAL_SCHEMA
                and approval.get("reviewer") in REVIEWERS
                and approval.get("status") == "ACCEPTED"
                and approval.get("final_sheet_sha256") == sheets.get("final", {}).get("sha256")
                and nonempty(approval.get("approval_reference"))
                and nonempty(approval.get("verbatim_human_approval"))
                and nonempty(approval.get("source_message_ref"))
            )
        except Exception as exc:
            check("contact_sheet_approval_parse", False, str(exc))
        else:
            check("contact_sheet_approval_parse", True)
        check("contact_sheet_approval_valid", approval_valid)
    else:
        check("contact_sheet_approval_not_supplied", args.authorization == "review")

    if args.authorization == "package":
        check("package_non_fixture", manifest.get("fixture") is False, "fixture manifests can never authorize packaging")
        check("package_authorization", approval_valid, "exact-sheet structured human approval required")
    packaging_allowed = args.authorization == "package" and approval_valid and manifest.get("fixture") is False
    status = "PASS" if all(record["status"] == "PASS" for record in checks) else "FAIL"
    report = {
        "schema": "playa-card-news-final-set-verification-v2",
        "status": status,
        "authorization": args.authorization,
        "packaging_allowed": status == "PASS" and packaging_allowed,
        "zip_allowed": status == "PASS" and packaging_allowed,
        "checks_total": len(checks),
        "checks_passed": sum(record["status"] == "PASS" for record in checks),
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256(manifest_path),
        "visual_qa_sha256": input_hashes.get(qa_path) if qa_path is not None else None,
        "contact_sheet_approval_sha256": approval_sha,
        "checks": checks,
    }
    if is_relative_to(report_path, output_root):
        print(json.dumps({"status": "FAIL", "error": "report must be outside immutable build output"}))
        raise SystemExit(2)
    if report_path in input_hashes:
        os.close(report_parent_fd)
        print(json.dumps({"status": "FAIL", "error": "report collides with an input file"}))
        raise SystemExit(2)
    payload = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
    try:
        write_new_report(report_parent_fd, report_name, payload)
    except OSError as exc:
        os.close(report_parent_fd)
        print(json.dumps({"status": "FAIL", "error": f"exclusive report creation failed: {exc}"}))
        raise SystemExit(2)
    mutated = [str(path) for path, before in input_hashes.items() if not is_regular_file(path) or sha256(path) != before]
    if mutated:
        try:
            os.unlink(report_name, dir_fd=report_parent_fd)
        finally:
            os.close(report_parent_fd)
        print(json.dumps({"status": "FAIL", "error": "input mutated during verification", "paths": mutated}))
        raise SystemExit(2)
    os.close(report_parent_fd)
    print(json.dumps({"status": status, "checks": len(checks), "passed": report["checks_passed"], "packaging_allowed": report["packaging_allowed"], "report": str(report_path)}))
    raise SystemExit(0 if status == "PASS" else 2)


if __name__ == "__main__":
    main()
