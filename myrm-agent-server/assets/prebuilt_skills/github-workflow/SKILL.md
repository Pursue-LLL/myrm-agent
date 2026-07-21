---
name: github-workflow
description: >-
  Complete GitHub PR workflow: branch management, structured commits, PR creation,
  code review response, and merge. Follows conventional commits and team best practices.
version: 1.0.0
category: development
tags:
  - git
  - github
  - pull-request
  - version-control
  - collaboration
allowed-tools: bash_code_execute_tool file_read_tool file_write_tool
contract:
  steps:
    - "Phase 1: Branch — create a feature branch with descriptive naming"
    - "Phase 2: Commit — make atomic, well-described commits following conventional format"
    - "Phase 3: PR Creation — write a comprehensive PR description"
    - "Phase 4: Review Response — address review feedback systematically"
    - "Phase 5: Merge — ensure CI passes, squash if needed, clean up branch"
  potential_traps:
    - description: "Large PRs with mixed concerns that are difficult to review"
      mitigation: "One PR = one concern. If changes span multiple concerns, split into separate PRs."
      severity: high
    - description: "Force-pushing over review comments, losing discussion context"
      mitigation: "Use incremental commits to address review feedback; never force-push during review"
      severity: medium
  verification_steps:
    - step_id: branch_clean
      description: "Branch is up to date with target and has no merge conflicts"
      validation_method: "git fetch && git rebase origin/main succeeds cleanly"
      is_required: true
    - step_id: ci_passes
      description: "All CI checks pass"
      validation_method: "GitHub Actions / CI pipeline shows all green"
      is_required: true
  success_criteria: "PR merged cleanly with comprehensive description and all checks passing"
  estimated_duration_seconds: 600
---

# GitHub Workflow

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## Overview

A good PR workflow makes code review efficient and keeps the repository history clean. This skill enforces best practices from branch creation through merge.

## Phase 1: Branch

### Naming Convention

```
{type}/{ticket-id}-{short-description}

# Examples:
feat/PROJ-123-user-auth
fix/PROJ-456-null-pointer
refactor/PROJ-789-extract-service
```

### Branch Types

| Prefix | Purpose |
|--------|---------|
| `feat/` | New feature |
| `fix/` | Bug fix |
| `refactor/` | Code restructuring (no behavior change) |
| `docs/` | Documentation only |
| `test/` | Adding or fixing tests |
| `chore/` | Maintenance, dependencies, tooling |

### Commands

```bash
git fetch origin
git checkout -b feat/PROJ-123-description origin/main
```

## Phase 2: Commit

### Conventional Commits

```
{type}({scope}): {description}

{body - optional, explains WHY}

{footer - optional, references}
```

### Types

| Type | When |
|------|------|
| `feat` | New feature for the user |
| `fix` | Bug fix |
| `refactor` | Code change that doesn't fix a bug or add a feature |
| `test` | Adding or correcting tests |
| `docs` | Documentation changes |
| `perf` | Performance improvement |
| `chore` | Build process, tooling, dependencies |

### Commit Guidelines

- **Atomic commits** — Each commit is one logical change
- **Present tense** — "add feature" not "added feature"
- **No period** at end of subject line
- **Body explains WHY**, not what (the diff shows what)
- **Reference issues** in footer: `Closes #123`

### Examples

```bash
git add src/auth/
git commit -m "feat(auth): add JWT refresh token rotation

Tokens now rotate on each refresh to prevent token theft.
Previous implementation reused the same refresh token indefinitely.

Closes #123"
```

## Phase 3: PR Creation

### PR Title

Same format as commit message: `{type}({scope}): {description}`

### PR Description Template

```markdown
## Summary
[1-3 sentences: what this PR does and why]

## Changes
- [Bullet list of specific changes]

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing completed

## Screenshots
[If UI changes, before/after screenshots]

## Related
- Closes #{issue_number}
- Related: #{related_pr}
```

### PR Best Practices

- **One concern per PR** — Don't mix feature + refactor + fix
- **Small PRs** — Under 400 lines of changes (excluding tests)
- **Draft PR early** — Open as draft for early feedback on approach
- **Self-review first** — Review your own diff before requesting others

## Phase 4: Review Response

When receiving review feedback:

1. **Read ALL comments** before responding to any
2. **Address each comment** — either fix or explain why not
3. **Use incremental commits** — one commit per review round
4. **Don't force-push** during active review — it hides discussion context
5. **Re-request review** after addressing all feedback

### Responding to Comments

| Comment Type | Response |
|-------------|----------|
| Bug/issue | Fix it + confirm in reply |
| Suggestion | Accept or explain trade-off |
| Question | Answer clearly with context |
| Nit/style | Fix if reasonable, note if disagreed |

## Phase 5: Merge

### Pre-Merge Checklist

- [ ] All CI checks pass
- [ ] All review comments addressed
- [ ] Branch is up to date with target (`git rebase origin/main`)
- [ ] No merge conflicts
- [ ] PR description is accurate and complete

### Merge Strategy

```bash
# Update branch
git fetch origin
git rebase origin/main

# Push updated branch
git push

# After merge (clean up)
git checkout main
git pull
git branch -d feat/PROJ-123-description
```

### Squash vs Merge

- **Squash** — For feature branches with messy history. Creates one clean commit.
- **Merge** — For branches with meaningful commit history. Preserves all commits.
- **Rebase** — For linear history preference. Replays commits on top of target.
