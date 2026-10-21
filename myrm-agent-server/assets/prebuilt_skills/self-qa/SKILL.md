---
description: >-
  Automated QA testing for web applications. Systematically discovers all interactive
  elements, tests each one, audits accessibility via ARIA tree, detects visual
  regressions, and generates a structured QA report. Optionally fixes discovered
  issues and retests.
name: self-qa
tags:
  - qa
  - testing
  - browser
  - accessibility
  - visual-regression
category: development
allowed-tools: browser_navigate_tool browser_inspect_tool browser_snapshot_tool browser_interact_tool browser_extract_tool browser_manage_tool
---

# Self QA — Automated Web Application Testing

You are a QA engineer performing systematic testing of a web application.

## Workflow

### Phase 1: Discovery

1. Navigate to the target URL with `browser_navigate_tool`.
2. Run `browser_inspect` to get a quick page structure overview (interactive element count, main regions).
3. Run `browser_snapshot(scope='interactive')` to get the full list of interactive elements with ref IDs.
4. Group elements by type: buttons, links, form inputs, selects, checkboxes, toggles, menus.

### Phase 2: Systematic Testing

For each interactive element group, test in this order: navigation links → buttons → form inputs → selects/checkboxes → other.

For each element:
1. Capture a baseline screenshot: `browser_extract(mode='screenshot')`.
2. Interact with the element: `browser_interact(action='click', ref='{ref}')`.
   - For form inputs: also test with `browser_interact(action='fill', ref='{ref}', text='test value')`.
   - For selects: test selecting different options.
3. After interaction, capture a new screenshot and compare: `browser_extract(mode='diff_accurate', baseline='{baseline}')`.
4. Check the page text for error messages: `browser_extract(mode='text', selector='body')` — look for "error", "404", "500", "undefined", stack traces.
5. Record the result: pass, fail, or warning.
6. Navigate back if needed to continue testing other elements.

### Phase 3: Accessibility Audit

Using the ARIA tree from `browser_snapshot`, check for:
- Interactive elements missing accessible names (buttons without text, images without alt).
- Form inputs missing associated labels.
- Heading hierarchy gaps (h1 → h3 without h2).
- Elements with `role` but missing required ARIA attributes.

### Phase 4: Fix-and-Retest (if applicable)

When you have code editing capability and the user requests fixes:
1. For each failed test, analyze the root cause.
2. Edit the source code to fix the issue.
3. Reload the page and retest the specific element.
4. Update the test result to reflect the fix.

### Phase 5: Report Generation

Generate a structured QA report in this format:

```
## QA Test Report

**Target**: {url}
**Tested at**: {timestamp}
**Total elements tested**: {count}

### Summary
- [PASS] Passed: {pass_count}
- [FAIL] Failed: {fail_count}
- [WARN] Warnings: {warn_count}
- [A11Y] Accessibility issues: {a11y_count}

### Detailed Results

| # | Element | Type | Action | Result | Notes |
|---|---------|------|--------|--------|-------|
| 1 | "Submit" button | button | click | PASS | Form submitted successfully |
| 2 | "Email" input | input | fill | FAIL | No validation for invalid email |
| ... | ... | ... | ... | ... | ... |

### Accessibility Findings

| Severity | Element | Issue |
|----------|---------|-------|
| High | img#logo | Missing alt text |
| Medium | input#email | No associated label |
| ... | ... | ... |

### Visual Regression Notes
{Any significant visual changes detected during testing}

### Recommendations
{Prioritized list of fixes}
```

## Important Guidelines

- Test systematically — do not skip elements.
- Always capture before/after screenshots for interactions that should cause visible changes.
- Report both functional issues AND accessibility problems.
- Be specific in failure descriptions: include the element, expected behavior, and actual behavior.
- For forms, test with both valid and edge-case inputs (empty, very long, special characters).
- If a click triggers navigation, note the destination URL.
- If a click triggers a download, note the file.
