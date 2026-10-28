# routing/reactions/

## Overview

The status reaction a turn shows on the message that started it: a mark that the message was received, then one verdict (completed, failed) or none (stopped). `pipeline/turn.py` is the only owner of that reaction; this package holds what it owns. Parent: [../_ARCH.md](../_ARCH.md).

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Facade | Re-exports `StatusReaction` and `TurnOutcome`. | [OK] |
| `status.py` | Core | `StatusReaction`: `received` puts the processing mark on the message when the policy asks for it and the platform accepts a glyph; `finish(TurnOutcome)` takes the mark off (only if one was put on) and shows the completion or failure glyph once, whichever way the turn ended; a stopped turn (`ABANDONED`) gets no verdict. The glyph chains (`👀🤔`, `✅👍🎉`, `❌😢`) live here; the platform's vocabulary decides which of them is sent. | [OK] |
