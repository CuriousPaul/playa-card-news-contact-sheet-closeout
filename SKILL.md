---
name: playa-card-news-contact-sheet-closeout
description: Use when reconciling per-card human decisions, approved face-edited derivatives, preserved originals, and final PLAYA card-news contact sheets before packaging. Builds original/final/comparison review sheets, enforces cross-card identity continuity and distinct-person checks, blocks stale or pending candidates, and requires pixel/SHA verification plus Kye/Paul contact-sheet approval before ZIP delivery.
version: 1.1.0
author: Market Fit Lab / Hermes Agent
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [playa, card-news, contact-sheet, face-edit, qa, closeout]
    related_skills: [playa-card-news-production, identity-safe-image-editing, artifact-package-verification]
---

# PLAYA Card-News Contact-Sheet Closeout

## Overview

Close the gap between individually reviewed card images and a trustworthy final card-news set. This skill does not write copy, search assets, generate faces, render branded cards, or publish. It reconciles the authoritative decision for every card, materializes a deterministic final set, creates separate original/final/comparison contact sheets, and proves that the selected pixels match the human decisions.

The central rule is **decision fidelity before visual polish**. A clean-looking contact sheet is invalid if it silently uses an old source, misses an approved derivative, promotes a pending candidate, or forces an unnecessary edit. Preserving the original is a valid positive quality decision when Kye/Paul says the edit is unnecessary or worse.

Load `playa-card-news-production` for the larger production contract, `identity-safe-image-editing` for any new or revised recognizable face, and `artifact-package-verification` before packaging or delivery. Read `references/quality-lessons.md` before reconciling a set.

## When to Use

Use this skill when:

- all or most cards have individual human decisions and the set needs a final contact sheet;
- some cards use approved face-edited derivatives while others preserve immutable originals;
- approval records are distributed across `ACCEPTANCE`, `human-selection`, `approved`, and `PRESERVE` artifacts;
- the same real person appears on multiple cards and must retain one approved fictional identity;
- a contact sheet must be approved before ZIP creation;
- a prior contact sheet may have omitted approved edits or included stale candidates.

Do not use this skill to:

- decide copy, CTA, brand layout, or asset semantics;
- invent approval from filenames alone;
- perform a new face edit without `identity-safe-image-editing`;
- publish, post, or run paid media;
- replace the final branded-card renderer when the inputs are only image backgrounds.

## Authority Model

For each card, resolve one terminal decision:

1. **Explicit latest human decision** recorded with reviewer, verbatim or message reference, selected path/SHA, and terminal status.
2. **Human-selection or acceptance artifact** binding a selected derivative SHA.
3. **Approved pair/group QA** for recurring people, if it includes human acceptance and selected SHAs.
4. **Explicit preserve record** such as `PRESERVE_ORIGINAL_BY_KYE` or `no_face_edit_required`.
5. **No decision:** block closeout. A candidate QA PASS is not human approval.

Later explicit human decisions supersede earlier candidate QA. A stale `pending_kye_review` record does not invalidate a later acceptance artifact, but the ledger must cite the later evidence. Conversely, a filename containing `approved` is evidence to investigate, not sufficient proof by itself.

Never infer that no approved derivative exists from one narrow search such as `*accepted*`. Search all relevant forms:

- `*approved*`
- `*accepted*`
- `*human-selection*`
- `*ACCEPTANCE*`
- `*FINAL_QA*`
- `*PRESERVE*`
- decision or manifest JSON containing the card number or selected SHA

Completion criterion: every card has exactly one terminal decision and every selected SHA is bound to human evidence.

## Workflow

### 1. Freeze scope

Record `set_id`, ordered card numbers, expected card count, immutable source path/SHA, final review destination, and whether the inputs are backgrounds or fully rendered cards.

Do not mix image-background closeout with branded-card delivery. Label the artifact truthfully.

**Done when:** the expected card list is exhaustive and each source decodes at the intended dimensions/orientation.

### 2. Build the decision ledger

Start from `templates/decision-ledger.json`. `expected_card_order` is mandatory and the `cards` sequence must equal it exactly. `columns` must be an integer from 1 through the smaller of 8 and card count. For every card record:

- immutable source path and SHA-256;
- decision: `preserve_original` or `use_approved_derivative`;
- selected path and SHA-256;
- reviewer (`Kye` or `Paul`) and terminal `ACCEPTED` decision evidence;
- selected character ID/version for edited recognizable faces;
- `same_source_person_group` when one real person recurs across cards;
- reason for preserve or edit;
- canonical mutation flag, which must remain false.

For `preserve_original`, selected pixels must equal source pixels after EXIF normalization. For `use_approved_derivative`, selected pixels must differ from source pixels and equal the approved derivative.

Each ledger evidence object must use the exact documented fields and an allowed production type (`human_selection`, `acceptance_record`, `preserve_record`, or `pair_group_qa`). Its path must name a regular structured JSON artifact created from `templates/decision-evidence.json`; arbitrary text is rejected. The entire evidence file is SHA-bound. Its exact versioned schema internally binds card number, reviewer (`Kye`/`Paul`), `ACCEPTED`, approval reference, selected SHA, non-empty verbatim human decision, and non-empty authoritative source-message reference. Those duplicated ledger/card values must exactly equal the internal payload. Unsafe `pending`, `rejected`, and `blocked` tokens are checked in every selected-path component, not only the basename.

Fixture evidence is test-only. A ledger with `fixture: true` requires the explicit `--allow-fixture` build flag, records `fixture: true` in the manifest, and can pass review verification but can never authorize packaging. `type: fixture` is rejected when the ledger is production (`fixture: false`). Never use `--allow-fixture` in a production command.

**Trust boundary:** these JSON documents provide integrity and semantic binding to authoritative records whose storage and source-message references are access controlled. They are not cryptographic identity authentication, and this CLI does not cryptographically authenticate Kye or Paul. For adversarial multi-user systems, require externally signed approval records and validate those signatures against trusted identities.

**Done when:** all cards are terminal, no selected path component is unsafe, and every selected/evidence SHA and approval binding matches the live files.

### 3. Reconcile people across the deck

Before building sheets, inspect the final selected pixels at full size.

- The same real person across cards must map to the same approved fictional `character_id@version`, unless a later explicit human decision says to preserve the original.
- Different people must not collapse into visually similar faces merely because contract IDs differ.
- Within a multi-person card, inspect pairwise face geometry, age impression, presentation, hair shell, and expression. Distinct IDs alone are insufficient.
- Preserve source gender and age impression unless a human-approved contract says otherwise.
- Do not force an edit when generation repeatedly damages scale, pose, gaze, hair occlusion, jewelry, or scene credibility. Escalate to preserve-original review.

**Done when:** recurring-person groups are consistent and no two distinct people read as the same synthetic face.

### 4. Materialize the final set

Run:

```bash
uv run --script scripts/build_contact_sheets.py \
  --ledger /absolute/path/to/decision-ledger.json \
  --out /absolute/path/to/set-final-review
```

The output path must not already exist, including as a symlink. The builder resolves every path, rejects any source/selected path beneath output, builds in a fresh temporary sibling, snapshots input hashes, and atomically renames only after completion. It never cleans, merges into, or overwrites an old output.

Tests may append `--allow-fixture`; production commands must not.

The builder must create exactly:

- `cards/card-NN.png` in exact order;
- `original-contact-sheet.jpg`;
- `final-contact-sheet.jpg`;
- `original-vs-final-contact-sheet.jpg`;
- `MANIFEST.json` with source/selected/final paths, SHAs, pixel relation, dimensions, and sheet SHAs.

The manifest declares the exact build inventory. Verification inventories every entry with `lstat`: only the `cards/` directory and exact declared regular files are permitted. Extra directories, stale files, symlinks, FIFOs, sockets, and device nodes fail. Rendering pins Pillow `12.0.0`. Determinism is environment-scoped: identical inputs are byte/pixel deterministic in the recorded Python/Pillow/libjpeg/platform environment; cross-platform libjpeg identity is not claimed. It never mutates immutable sources or approved derivatives.

**Done when:** expected count equals produced count and the manifest lists every output.

### 5. Run visual QA on exact final pixels

Inspect the final and comparison sheets, then full-size cards where faces are small in the sheet. Start from `templates/visual-qa.json`. The verifier requires its exact versioned schema and exact fields: reviewer, exact reviewed-sheet SHA, non-empty verbatim human review, non-empty authoritative source-message reference, status, and gates. Its named gate set is exhaustive: missing, extra, empty, or non-`PASS` gates fail. Record PASS/FAIL for:

- exact card count and order;
- no missing or duplicate cards;
- no crop, aspect, rotation, or stale-render error;
- edited cards visibly use the approved identity;
- preserved cards remain the intended originals;
- recurring-person continuity;
- distinct-person non-collapse;
- natural face integration and no seam, halo, fragmented features, or pasted appearance;
- card-level semantic fit and intact principal subject;
- no unintended text, logo, hand, object, or scene drift;
- truthful artifact label: background set vs final rendered cards.

A contact sheet is an overview, not proof of fine face quality. Zoom into any ambiguous face.

**Done when:** all hard gates pass and the exact `VISUAL_QA.json` points to the reviewed sheet SHA.

### 6. Run independent artifact verification

```bash
uv run --script scripts/verify_final_set.py \
  --manifest /absolute/path/to/set-final-review/MANIFEST.json \
  --visual-qa /absolute/path/to/governance/VISUAL_QA.json \
  --authorization review \
  --report /absolute/path/to/governance/FRESH-REVIEW-VERIFICATION.json
```

Keep QA, approval, and reports outside the immutable build output and all source, selected, ledger, evidence, QA, and approval files. `--report` is always a new artifact: the raw caller path must not exist as any file type, no existing parent component may be a symlink, missing parents are created component-by-component, and the report is exclusively created with `O_EXCL` plus `O_NOFOLLOW` where available. It never overwrites a regular, symlink, or special file. The verifier snapshots every input hash and rechecks all of them after writing the report; mutation removes the report and fails closed.

The verifier checks exact inventory, evidence files/bindings, exact ledger and visual-QA schemas, card count/order, pixel equality, source relation, all path components, and visual-QA SHA/gates. It independently recomputes sheet dimensions and rerenders original/final/comparison sheets from verified card pixels, then compares decoded rendered pixels; it does not trust manifest sheet metadata alone.

If verification fails, fix the artifact or the verifier assumption and rerun. Never report PASS from a partially passing check set.

Review mode intentionally returns `packaging_allowed: false`. **Done when:** fresh report status is `PASS`, `checks_passed == checks_total`, and the exact sheets are ready for human review.

### 7. Human contact-sheet gate

Deliver the **final contact sheet** and, when comparison is useful, the **original and comparison sheets as separate files**. Do not assume the user can extract the original half from a combined board.

Stop at `contact_sheet_review_pending`. Do not build or deliver a final ZIP until Kye/Paul explicitly approves the exact contact sheet. If feedback says an edit is unnecessary, update the ledger to `preserve_original`, rebuild all sheets and manifests, and rerun verification.

Record approval using `templates/contact-sheet-approval.json`. This structured JSON is the evidence artifact itself, not metadata pointing at meaningless free text. Its exact schema internally requires reviewer `Kye` or `Paul`, terminal `ACCEPTED`, exact final-sheet SHA, durable approval reference, non-empty verbatim human approval, and non-empty authoritative source-message reference. The verifier binds the whole approval-file SHA into its report. Ledger or CLI metadata cannot substitute for these internal fields. Never put this approval inside the decision ledger or infer it from visual QA.

**Done when:** the separate human approval artifact binds the exact final contact-sheet SHA.

### 8. Package only after approval

After approval, authorize packaging first:

```bash
uv run --script scripts/verify_final_set.py \
  --manifest /absolute/path/to/set-final-review/MANIFEST.json \
  --visual-qa /absolute/path/to/governance/VISUAL_QA.json \
  --contact-sheet-approval /absolute/path/to/governance/CONTACT_SHEET_APPROVAL.json \
  --authorization package \
  --report /absolute/path/to/governance/FRESH-PACKAGE-AUTHORIZATION.json
```

Only a full PASS in package mode sets `packaging_allowed` and `zip_allowed` true. Then freeze pixels, run `artifact-package-verification`, build the ZIP, and verify ZIP membership against the manifest. Send one ZIP per set only after confirmed delivery requirements are met.

**Done when:** extracted ZIP contents reproduce the verified file inventory and SHA set.

## Quality Heuristics from the 8/10 Baseline

- **Restraint beats forced novelty.** If the source already meets the practical requirement and the edit reduces naturalness, preserve it.
- **One coherent face, not feature fragments.** Local edits must use a broad coherent internal-face support and lock ears, earrings, neck, necklace, collar, and external hair unless explicitly targeted.
- **No manual rescue drift.** Avoid arbitrary pixel translation to repair a generated face. Require stable registration from source context; otherwise reject.
- **Source-context over full-scene regeneration.** When exact scene pixels matter, generate in a bounded source-context crop, align deterministically, and restore immutable pixels outside support.
- **Human decisions are data.** Store preserve/approve/reject decisions as machine-readable artifacts immediately.
- **Reconciliation is a separate stage.** Individual card completion does not prove the set uses the right card versions.
- **Contact sheets need separate deliverables.** Always retain original-only, final-only, and comparison boards.

## Common Pitfalls

1. **Searching only `*accepted*`.** This misses `approved`, pair QA, selection records, and preserve decisions. Use the full authority search set.
2. **Treating candidate QA as approval.** `PASS_CANDIDATE_FOR_HUMAN_REVIEW` remains pending.
3. **Using filenames as the only evidence.** Read the binding JSON and verify SHA.
4. **Building from memory.** Reconcile live files and records; session summaries are secondary context.
5. **Assuming preserved means unfinished.** Preserve-original can be the best approved outcome.
6. **Checking only the combined board.** Deliver original and final sheets separately too.
7. **Validating IDs but not faces.** Different IDs can still look like the same person.
8. **Letting a stale verifier fail a good artifact.** Check whether expected dimensions or status vocabulary are wrong, then fix and rerun; never waive the failure.
9. **Creating ZIP before the human gate.** Contact-sheet feedback often changes card selection and invalidates packaging.
10. **Calling backgrounds final cards.** State whether typography, wordmark, CTA, and full branded rendering are included.

## Verification Checklist

- [ ] Every expected card has exactly one terminal decision
- [ ] `expected_card_order` exactly equals ledger cards and columns are bounded
- [ ] Every decision has exact-schema structured evidence with matching card/reviewer/status/reference/selected SHA, verbatim decision, source-message reference, and whole-file hash
- [ ] No selected path component contains pending/rejected/blocked
- [ ] Preserved cards are pixel-equal to immutable sources
- [ ] Edited cards are pixel-equal to approved derivatives and differ from sources
- [ ] Same-person groups retain one approved fictional identity
- [ ] Distinct people do not visually collapse to the same face
- [ ] Original, final, and comparison sheets exist separately
- [ ] Exact `lstat` output inventory has only the permitted directory and regular files; no extra directory, symlink, FIFO, socket, or device
- [ ] Card count, order, crop, aspect, rotation, dimensions, and independent sheet rerender pass
- [ ] Full-size face/scene QA passes
- [ ] Fresh verifier passes all checks
- [ ] Separate exact-schema contact-sheet approval internally binds reviewer, verbatim approval, source reference, and exact final sheet SHA; verification report binds the approval-file SHA
- [ ] No final ZIP exists before that approval
- [ ] Immutable sources and canonical assets were not mutated

For changes to this skill, run `python3 -m py_compile scripts/*.py`, `uv run --script scripts/smoke_test.py`, and `uv run --script scripts/negative_tests.py` plus an accessible real-set replay.
