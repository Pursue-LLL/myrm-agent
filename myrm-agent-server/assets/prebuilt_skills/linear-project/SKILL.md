---
name: linear-project
description: >-
  Manage Linear projects and issues: create, update, and query issues; manage
  cycles and projects; track team workload. Requires a Linear API key.
version: 1.0.0
category: productivity
tags:
  - linear
  - project-management
  - issues
  - agile
  - team
allowed-tools: web_fetch_tool bash_code_execute_tool file_write_tool
requires:
  env: [LINEAR_API_KEY]
contract:
  steps:
    - "Phase 1: Connect — verify Linear API access"
    - "Phase 2: Query — understand current state (team, projects, cycles)"
    - "Phase 3: Execute — perform requested operations"
    - "Phase 4: Report — confirm changes and provide status summary"
  potential_traps:
    - description: "Creating duplicate issues"
      mitigation: "Search existing issues before creating new ones"
      severity: medium
    - description: "Moving issues without understanding workflow states"
      mitigation: "Query team workflow states first to use correct status names"
      severity: low
  verification_steps:
    - step_id: api_access
      description: "Linear API key is configured and valid"
      validation_method: "GraphQL query to viewer returns user data"
      is_required: true
  success_criteria: "Requested Linear operations completed with verification"
  estimated_duration_seconds: 300
---

# Linear Project Management

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## Overview

Linear is a modern project management tool for software teams. This skill provides workflows for managing issues, cycles, and projects via the Linear GraphQL API.

## Prerequisites

1. Get an API key from Linear: Settings → API → Personal API Keys
2. Set environment variable: `LINEAR_API_KEY=lin_api_xxx`

## API Basics

All requests use the GraphQL endpoint:

```
POST https://api.linear.app/graphql
Authorization: $LINEAR_API_KEY
Content-Type: application/json
```

## Common Operations

### Get Current User and Teams

```graphql
query {
  viewer {
    id
    name
    email
    teams {
      nodes {
        id
        name
        key
      }
    }
  }
}
```

### List Issues (with filters)

```graphql
query {
  issues(
    filter: {
      team: { key: { eq: "TEAM" } }
      state: { type: { in: ["started", "unstarted"] } }
      assignee: { isMe: { eq: true } }
    }
    first: 20
    orderBy: updatedAt
  ) {
    nodes {
      id
      identifier
      title
      description
      priority
      state { name type }
      assignee { name }
      labels { nodes { name } }
      dueDate
      estimate
    }
  }
}
```

### Create Issue

```graphql
mutation {
  issueCreate(input: {
    teamId: "TEAM_ID"
    title: "Issue title"
    description: "Detailed description in markdown"
    priority: 2
    labelIds: ["LABEL_ID"]
    assigneeId: "USER_ID"
  }) {
    success
    issue {
      id
      identifier
      url
    }
  }
}
```

### Update Issue

```graphql
mutation {
  issueUpdate(
    id: "ISSUE_ID"
    input: {
      stateId: "STATE_ID"
      priority: 1
      assigneeId: "USER_ID"
    }
  ) {
    success
    issue {
      identifier
      title
      state { name }
    }
  }
}
```

### Search Issues

```graphql
query {
  issueSearch(query: "search terms", first: 10) {
    nodes {
      identifier
      title
      state { name }
      assignee { name }
    }
  }
}
```

### List Workflow States

```graphql
query {
  team(id: "TEAM_ID") {
    states {
      nodes {
        id
        name
        type
        position
      }
    }
  }
}
```

### Current Cycle

```graphql
query {
  team(id: "TEAM_ID") {
    activeCycle {
      id
      name
      startsAt
      endsAt
      issues {
        nodes {
          identifier
          title
          state { name }
          assignee { name }
          estimate
        }
      }
    }
  }
}
```

## Workflow Patterns

### Sprint Planning
1. Query current cycle issues and their states
2. Identify unestimated or unassigned issues
3. Suggest prioritization based on due dates and dependencies

### Daily Standup Summary
1. Query my assigned issues (in progress + completed today)
2. Format as standup update: done / doing / blocked

### Issue Triage
1. List new issues without labels or priority
2. Suggest categorization based on title and description
3. Batch-update with labels and priority

### Weekly Status Report
1. Query issues completed this cycle
2. Query issues in progress
3. Calculate cycle progress (done / total)
4. Generate formatted status report

## Priority Mapping

| Priority | Value | Meaning |
|----------|-------|---------|
| No priority | 0 | Unset |
| Urgent | 1 | Drop everything |
| High | 2 | Do this cycle |
| Medium | 3 | Plan for next cycle |
| Low | 4 | Backlog |

## Error Handling

| Error | Cause | Fix |
|-------|-------|-----|
| 401 | Invalid API key | Check LINEAR_API_KEY env var |
| 400 | Invalid GraphQL | Check query syntax and field names |
| "Entity not found" | Wrong ID | Query for correct IDs first |
