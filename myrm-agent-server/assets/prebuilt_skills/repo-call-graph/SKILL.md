---
name: repo-call-graph
description: >-
  Structural navigation of Python and TypeScript/JavaScript code: where a symbol is
  defined, which call sites call a function, what a function calls, which classes extend a class, which files
  import a module, and which test files call a function. Use it before changing a function signature, behavior
  or location, when plain-text search would return too many unrelated matches.
version: 2.0.0
category: development
tags:
  - code-intelligence
  - call-graph
  - refactoring
  - impact-analysis
contract:
  steps:
    - "Phase 1: Resolve — turn the name into one qualified name and location (action resolve)"
    - "Phase 2: Trace — list callers, callees, implementors or importers of that symbol"
    - "Phase 3: Verify — open every location you rely on and check match=name rows before acting on them"
    - "Phase 4: Cover — list the test files that call the function directly and state what that list does not cover"
  potential_traps:
    - description: "Treating match=name rows as certain call sites when several functions share the name"
      mitigation: "Read each call site; when definitions is above 1 decide per row which function is called"
      severity: high
    - description: "Concluding a function is unused because callers returned nothing"
      mitigation: "Dynamic calls (getattr, strings, decorators, injection) are not seen; confirm with grep_tool"
      severity: high
    - description: "Trusting the calling function of a TypeScript/JavaScript row"
      mitigation: "Open the location; for JS/TS the enclosing function can be wrong"
      severity: medium
  verification_steps:
    - step_id: call_sites_opened
      description: "Every call site that drives an edit was read in its file"
      validation_method: "file_read_tool output exists for each location cited"
      is_required: true
    - step_id: coverage_stated
      description: "The report says which kinds of callers the graph cannot see"
      validation_method: "Final answer names dynamic calls and indirect tests as not covered"
      is_required: true
  success_criteria: "Every affected call site and direct test is identified, and the limits of the search are stated"
  estimated_duration_seconds: 300
---

# Repo Call Graph

Use `code_graph_tool` for structural questions about Python and TypeScript/JavaScript code: who calls a function, what a function calls, which classes extend a class, which Python files import a module, which test files call a function. It reads the workspace you are working in and brings its index up to date on every call, so there is nothing to build or refresh.

## When to use it

- Before changing a function's signature, behavior or location: find every caller.
- Before refactoring a class: find its subclasses and the files that import it.
- After a change: find the test files that call the changed function directly and run those first.
- Use `grep_tool` instead for plain text, string literals, comments, config files, and languages other than Python and TypeScript/JavaScript.

## Workflow

1. Call `resolve` with the plain name. Pick the row you mean by file path. If several rows still fit, ask the user which one.
2. Ask the question about that symbol: `callers` (plain function name), `callees` (the qualified name from step 1), `implementors`, `importers`, or `tests_calling`.
3. Open each location you will rely on with `file_read_tool` before you edit anything.
4. In your answer, say what you checked and what the graph cannot see.

## Reading results

- `match: exact` means the call text equals the name you asked for. `match: name` means only the last part matches (`obj.save()` matches `save`). When `definitions` is above 1, a `match: name` row may call a different function with the same name; read the call site and decide.
- `callees` returns call text as written. It does not say which definition is called; run `resolve` on a name to find out.
- `tests_calling` lists direct callers inside test files only. A test that reaches the function through other functions is not listed; follow `callers` one level at a time or search with `grep_tool`.
- `total` larger than the rows shown means the list was cut at 50. Use a more specific name, such as a qualified name.
- No rows: check spelling and case, try `resolve` with a shorter name, then use `grep_tool`. An empty `callers` result does not prove a function is unused, because calls made through `getattr`, strings, bare `@decorator` lines or dependency injection are not seen.

## Limits

- Calls are matched by name. The tool does not follow imports or infer types.
- Python results are normally right about which function contains a call; a call outside any function (module level, class body) has the module name as `caller`. TypeScript/JavaScript results are approximate and that function can be wrong.
- Imports are indexed for Python only: `importers` finds nothing in TypeScript/JavaScript files.
- Files ignored by git, dependency and build folders, files over 1 MB, symbolic links, and Python files with syntax errors are not indexed.
- Very large workspaces are indexed only in part. When `notes` says so, a missing result is unconfirmed: use `grep_tool`.
