# Writing Good Tests — Deeper Reference

**Load this reference when:** writing or changing tests, adding mocks, or adding
test-only helpers. The core rules live in the SKILL.md body; this file holds
mock discipline, anti-pattern warnings, and a quick-reference table.

## Behavior, Not Text

Asserting that a script, skill, or config contains an exact line proves only
that the source is the source. Run scripts against controlled inputs and
assert outputs, side effects, or exit codes. Documents that instruct agents
are tested by the consuming agent's behavior; prose for humans earns no test
at all.

## Your Code, Not the Framework

Test the contract your code makes at its boundaries — the route you register,
the query you emit, the payload you produce. Upstream mechanics are their
maintainers' tests to write. The classic mistake: asserting your router invokes
a registered handler — that is the framework's test, not yours. When upstream
behavior genuinely surprised you, write one narrow characterization test naming
the assumption.

## Mock Discipline

**The mock earns no assertions.** A mock assertion passes when the mock is
present and fails when it is absent — it says nothing about the component.
Assert the real component's behavior; if the mock is what you are checking,
unmock it or delete the assertion.

**Mock at the right level.** Learn every side effect of the real method before
replacing it; mock the slow or external operation and keep what the test
depends on real. When unsure, run the test against the real implementation
first and observe what actually needs to happen.

**Make doubles specific.** When arguments, call counts, or ordering are part of
the contract, assert them — a fake that accepts anything verifies nothing. Give
each branch (success, error, malformed) its own fixture or spy, so the wrong
branch cannot satisfy the expectation.

**Mirror real data completely.** Mock the complete structure as it exists in
reality — all documented fields — not just the ones your test reads. Partial
mocks fail silently when downstream code reads an omitted field: the test
passes while integration breaks.

**Prefer real components over complex mocks.** When mock setup outgrows the
test logic, mocks miss methods the real components have, or tests break when
the mock changes, switch to an integration test with real components.

## Test-Only Code Stays in Test Utilities

Cleanup that only tests need lives in test utilities, never as a `destroy()`
method on the production class. Ask: is this method called only from tests?
Does this class own this resource's lifecycle? Wrong answers → test utility.

## Trivial Code Earns No Test

A test written to satisfy process costs maintenance forever. Trivial code and
human prose earn none. If the code validates, normalizes, defaults, derives,
enforces, or causes side effects, test the first consumer-visible result that
depends on it.

## Quick Reference

| When you... | Do |
|-------------|-----|
| Write any test | Name the break it catches — a bug, not a decision |
| Build an expected value | Derive it by hand; never with the code under test |
| Test a script or document | Run it / pressure-test its consumer; never grep its text |
| Reach for a dependency test | Test your boundary contract, not their documented mechanics |
| Want to assert on a mocked element | Test the real component, or unmock it |
| Are about to mock a method | Learn its side effects; mock the slow/external level |
| Build a mock response | Mirror the real structure completely |
| Need cleanup only tests use | Put it in test utilities |
| Watch mock setup balloon | Switch to an integration test with real components |
| Finish a test file | Run the mutation check (see SKILL.md body) |

## Warning Signs

- Setup and assertion share the same object, guaranteeing equality
- The test can fail only through a panic, crash, or missing selector
- The test fails on every intentional change, never on accidental breakage
- Expected values are hidden behind loops, builders, or helpers
- The test greps source text, or asserts a removed symbol stays removed
- The test would still matter if only the framework remained
- The test exists for coverage, checking no side effect or outcome
- An assertion checks a `*-mock` test ID, or fails if you remove the mock
- A method is called only from test files
- Mock setup is more than half the test, or you cannot explain why the mock is needed
