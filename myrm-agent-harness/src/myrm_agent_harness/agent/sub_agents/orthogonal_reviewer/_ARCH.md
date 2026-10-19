# orthogonal_reviewer/

## Overview

Dual orthogonal review: two independent reviewers judge the same work from different
perspectives, and an arbiter reconciles them into one verdict. The blind reviewer never sees
the author's reasoning, so its verdict cannot be anchored by it.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports the arbiter, both reviewers and models. | — |
| arbiter.py | Core | `OrthogonalReviewArbiter` — reconciles two review verdicts into a final decision. | — |
| blind_reviewer.py | Core | `BlindCleanContextReviewer` — reviews in a clean context with no author rationale. | — |
| intent_reviewer.py | Core | Reviews the change against the stated intent. | — |
| types.py | Core | `ReviewerPerspective`, verdict and report models. | — |

## Key Dependencies

- `pydantic` (models)

## Key Design Decisions

- **Blind is structural, not instructed**: the blind reviewer is handed a context that never
  contained the author's reasoning, so "ignore the rationale" is not a prompt instruction that
  can be talked out of.
- **Two perspectives, one verdict**: the arbiter owns the reconciliation so neither reviewer can
  unilaterally approve.
- **Perspective is typed**: `ReviewerPerspective` is a closed enum, so a new reviewer cannot
  silently reuse an existing perspective label.
