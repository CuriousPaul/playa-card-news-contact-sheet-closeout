# Quality Lessons Behind the 8/10 Contact-Sheet Baseline

## What worked

1. **Card-level human decisions were preserved.** Edited and untouched cards coexisted in one final set instead of forcing every card through the same operation.
2. **Recurring-person continuity was explicit.** Two cards showing the same source person used one approved fictional identity while preserving frame-specific pose, gaze, mouth state, and lighting.
3. **Controlled local editing protected the scene.** Approved local edits restored immutable pixels outside the face support and verified zero unintended changed pixels there.
4. **Original preservation remained available.** A difficult final card was preserved after generated variants repeatedly changed head scale, forehead exposure, hair occlusion, expression, and polish.
5. **Three review views were useful.** Original-only, final-only, and stacked comparison sheets answered different review questions.
6. **Fresh verification caught a reconciliation error.** The first set assembly accidentally selected only one approved edit because discovery searched too narrowly. Broader decision search found three additional approved cards before delivery.

## What limited the score to roughly 8/10

- Some source scenes already had polished subjects, so edited faces could still read more model-like than ordinary.
- Small face scale in contact sheets can hide fine seams or weak identity distance.
- Face editing can preserve source pose and hair while still changing subtle affect.
- A clean contact sheet proves set coherence, not campaign-level copy, typography, CTA, or semantic asset quality.
- The workflow had stale candidate QA files alongside later acceptance records, increasing reconciliation risk.

## Rules derived from the misses

### Approval discovery

Search by status semantics, not one filename pattern. Read acceptance, selection, pair/group QA, preserve records, and manifest rows. Resolve conflicts by explicit human decision time and selected SHA.

### Preserve-original branch

Use preserve-original when:

- the human reviewer says the edit is unnecessary;
- three bounded attempts fail scale/pose/hair/scene gates;
- the person is already allowed or not a required edit target;
- the edit is technically different but visually less natural.

Preserve-original is not a fallback embarrassment. It is a terminal quality decision.

### Face-edit escalation

1. Start from immutable source.
2. Try bounded direct in-scene generation only when it can preserve the scene.
3. If full-scene generation drifts, switch to source-context local generation.
4. Register without arbitrary translation.
5. Use coherent face support; lock hair shell, visible ears, earrings, neck, jewelry, collar, body, and scene.
6. Reject fragmented or pasted-looking features.
7. After bounded failure, return to human preserve/reselect decision rather than endless prompt tuning.

### Set reconciliation

Individual approvals are not a final set. Rebuild an authoritative ledger every time the contact sheet changes. The ledger is the only input to assembly.

### Contact-sheet gate

Deliver all three views:

- original-only: confirms source sequence and scene baseline;
- final-only: assesses production coherence;
- comparison: audits which cards changed.

The original-only sheet should be separately downloadable, not only embedded in a combined image.

### Verification truth boundary

Machine checks prove paths, hashes, pixels, dimensions, order, and status bindings. Human review proves naturalness, identity continuity, distinct-person appearance, crop meaning, and overall quality. Neither replaces the other.
