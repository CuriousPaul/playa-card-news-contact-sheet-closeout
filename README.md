# PLAYA Card-News Contact-Sheet Closeout

A Hermes skill for reconciling per-card human decisions and producing verifiable original, final, and comparison contact sheets for PLAYA card-news sets.

## What it enforces

- Immutable canonical sources
- Explicit `preserve_original` or `use_approved_derivative` decisions
- Structured human-decision evidence bound to selected pixels
- Cross-card identity continuity and distinct-person checks
- Separate original, final, and original-vs-final contact sheets
- Exact card order, crop, dimensions, SHA-256, and pixel-relation checks
- Independent contact-sheet reconstruction
- Human approval bound to the exact final-sheet SHA before packaging
- Rejection of stale files, symlinks, FIFOs, sockets, pending/rejected paths, and source/output collisions

## Quality baseline

The workflow was derived from a human-rated 8/10 production contact sheet and retains both the successful patterns and the remaining quality risks. See [`references/quality-lessons.md`](references/quality-lessons.md).

## Verification

The included tests currently cover:

- Review verification: **104/104 checks**
- Production package authorization: **107/107 checks**
- Adversarial negative cases: **36/36 rejected as expected**

Run:

```bash
uv run --script scripts/smoke_test.py
uv run --script scripts/negative_tests.py
```

## Install for Hermes

Clone the repository and link its root into your Hermes skills directory:

```bash
git clone https://github.com/CuriousPaul/playa-card-news-contact-sheet-closeout.git
ln -s "$PWD/playa-card-news-contact-sheet-closeout" \
  ~/.hermes/skills/playa-card-news-contact-sheet-closeout
```

See [`SKILL.md`](SKILL.md) for the complete workflow, required artifacts, and trust boundary.

## Trust boundary

The verifier provides strict integrity and semantic binding for approval records. It does not cryptographically prove a person's identity. Approval evidence must come from an access-controlled authoritative source such as the actual review thread or governed approval store. Adversarial multi-user environments should add signed external approval records.
