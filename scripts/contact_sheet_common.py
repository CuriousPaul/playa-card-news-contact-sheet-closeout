from __future__ import annotations

import hashlib
import io
import json
import math
import stat
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont, ImageOps

CELL_W = 600
IMAGE_H = 560
LABEL_H = 60
TITLE_H = 80
MAX_COLUMNS = 8
RENDERER_ID = "playa-contact-sheet-v2-pillow-12.0.0"
QA_GATES = (
    "exact_card_count_and_order",
    "no_missing_or_duplicate_cards",
    "crop_aspect_rotation_and_stale_render",
    "approved_identity_on_edited_cards",
    "preserved_originals_unchanged",
    "recurring_person_continuity",
    "distinct_person_non_collapse",
    "natural_face_integration",
    "semantic_fit_and_principal_subject",
    "no_unintended_text_logo_object_or_scene_drift",
    "truthful_artifact_label",
)
DECISION_EVIDENCE_TYPES = {
    "human_selection",
    "acceptance_record",
    "preserve_record",
    "pair_group_qa",
    "fixture",
}
LEDGER_SCHEMA = "playa-card-news-decision-ledger-v1"
DECISION_EVIDENCE_SCHEMA = "playa-card-news-decision-evidence-v1"
VISUAL_QA_SCHEMA = "playa-contact-sheet-visual-qa-v1"
CONTACT_SHEET_APPROVAL_SCHEMA = "playa-contact-sheet-approval-v1"
DECISION_EVIDENCE_KEYS = {
    "schema", "card", "reviewer", "status", "approval_reference",
    "selected_sha256", "verbatim_human_decision", "source_message_ref",
}
VISUAL_QA_KEYS = {
    "schema", "reviewer", "status", "reviewed_sheet_sha256",
    "source_message_ref", "verbatim_human_review", "gates",
}
CONTACT_SHEET_APPROVAL_KEYS = {
    "schema", "reviewer", "status", "final_sheet_sha256",
    "approval_reference", "verbatim_human_approval", "source_message_ref",
}
REVIEWERS = {"Kye", "Paul"}
UNSAFE_TOKENS = ("pending", "rejected", "blocked")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def valid_sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def load_exact_json(path: Path, keys: set[str]) -> dict:
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or set(data) != keys:
        raise ValueError(f"exact keys required: {sorted(keys)}")
    return data


def is_regular_file(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.stat(follow_symlinks=False).st_mode)
    except (FileNotFoundError, OSError):
        return False


def load_rgb(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def default_font(size: int):
    # Pillow's bundled font plus a pinned Pillow version makes rendering deterministic
    # within the declared Python/Pillow/libjpeg environment recorded in the manifest.
    return ImageFont.load_default(size=size)


def expected_sheet_size(count: int, columns: int) -> tuple[int, int]:
    rows = math.ceil(count / columns)
    return CELL_W * columns, TITLE_H + rows * (IMAGE_H + LABEL_H)


def render_sheet(images: Iterable[Image.Image], labels: list[str], title: str, columns: int) -> Image.Image:
    image_list = list(images)
    width, height = expected_sheet_size(len(image_list), columns)
    canvas = Image.new("RGB", (width, height), "#111111")
    draw = ImageDraw.Draw(canvas)
    draw.text((24, 20), title, font=default_font(28), fill="white")
    for index, (image, label) in enumerate(zip(image_list, labels, strict=True)):
        row, column = divmod(index, columns)
        thumb = image.copy()
        thumb.thumbnail((CELL_W - 20, IMAGE_H - 20), Image.Resampling.LANCZOS)
        x = column * CELL_W + (CELL_W - thumb.width) // 2
        y = TITLE_H + row * (IMAGE_H + LABEL_H) + LABEL_H + (IMAGE_H - thumb.height) // 2
        canvas.paste(thumb, (x, y))
        draw.text(
            (column * CELL_W + 16, TITLE_H + row * (IMAGE_H + LABEL_H) + 14),
            label,
            font=default_font(26),
            fill="white",
        )
    return canvas


def render_comparison(original: Image.Image, final: Image.Image) -> Image.Image:
    result = Image.new("RGB", (max(original.width, final.width), original.height + final.height), "#080808")
    result.paste(original, (0, 0))
    result.paste(final, (0, original.height))
    return result


def jpeg_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=95, subsampling=0)
    return buffer.getvalue()


def save_jpeg(image: Image.Image, path: Path) -> None:
    path.write_bytes(jpeg_bytes(image))


def path_has_unsafe_component(path: Path) -> bool:
    return any(token in component.lower() for component in path.parts for token in UNSAFE_TOKENS)


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
