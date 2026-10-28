# routing/reactions/

## Overview

How the router reacts to messages: `ReactionFunnel` is the one place a reaction leaves the router, and `StatusReaction` is the reaction a turn shows on the message that started it (a mark that the message was received, then one verdict, completed or failed, or none when stopped). `pipeline/turn.py` is the only owner of that status reaction. Parent: [../_ARCH.md](../_ARCH.md).

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Facade | Re-exports `ReactionFunnel`, `StatusReaction` and `TurnOutcome`. | [OK] |
| `funnel.py` | Core | `ReactionFunnel`: `react` sets or takes off a reaction and never fails the caller (a message without a platform id, a channel without reaction support or an unknown channel is skipped; a platform that has not answered within 30 seconds is given up on and reported like any other failure, so a silent platform cannot hold a turn open); a failure that keeps happening is warned once per 10 minutes per channel and error type, the rest is logged at debug level; `accepted` picks the first glyph of a candidate chain that the channel's `reaction_glyphs` accepts, or nothing. `MessageEffects.reactions` holds the router's instance. | [OK] |
| `status.py` | Core | `StatusReaction`: `received` starts putting the processing mark on the message when the policy asks for it and the platform accepts a glyph, as a request that runs beside the turn (the agent never waits for the platform); `marked` waits for that request to be answered; `cancel` stops it if the turn leaves first; `finish(TurnOutcome)` waits for the mark to land, takes it off (only if one was put on) and shows the completion or failure glyph once, whichever way the turn ended; a stopped turn (`ABANDONED`) gets no verdict. The glyph chains (`👀🤔`, `✅👍🎉`, `❌😢`) live here; the platform's vocabulary decides which of them is sent. | [OK] |
