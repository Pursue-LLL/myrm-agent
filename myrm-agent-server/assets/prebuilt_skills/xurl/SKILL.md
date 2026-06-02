---
name: xurl
description: >-
  X/Twitter account operations via the xurl CLI: post, search, reply, quote,
  bookmark, DM, media upload, and raw v2 API access. OAuth 2.0 with auto-refresh.
version: 1.1.0
category: social-media
tags:
  - twitter
  - x
  - social-media
  - xurl
  - content-publishing
allowed-tools: bash_tool file_write_tool file_read_tool
requires:
  bins: [xurl]
contract:
  steps:
    - "Phase 1: Verify — confirm xurl is installed and authenticated"
    - "Phase 2: Understand — clarify the user's intent (read vs write action)"
    - "Phase 3: Execute — run the appropriate xurl command(s)"
    - "Phase 4: Confirm — show results and confirm before destructive actions"
  potential_traps:
    - description: "Exposing OAuth tokens or credentials to the LLM context"
      mitigation: "Never read, print, or reference ~/.xurl contents. Never use --verbose flag."
      severity: critical
    - description: "Publishing content without user confirmation"
      mitigation: "Always show draft content and get explicit approval before post/reply/DM"
      severity: high
    - description: "Hitting rate limits on write endpoints"
      mitigation: "Check for 429 responses and wait before retrying. Write endpoints have tighter limits."
      severity: medium
  verification_steps:
    - step_id: auth_check
      description: "xurl is installed and authenticated with a valid app"
      validation_method: "xurl auth status shows a default app with oauth2 tokens"
      is_required: true
    - step_id: write_confirmed
      description: "Write actions (post, reply, DM, delete) are confirmed by user"
      validation_method: "User explicitly approves the content before execution"
      is_required: true
  success_criteria: "Requested X/Twitter action completed successfully with user confirmation"
  estimated_duration_seconds: 120
---

# xurl — X (Twitter) API via Official CLI

`xurl` is the X developer platform's official CLI for the X API v2. It supports shortcut commands for common actions and raw curl-style access to any v2 endpoint. All commands return JSON.

## Secret Safety (MANDATORY)

- **Never** read, print, or send `~/.xurl` contents to LLM context
- **Never** ask the user to paste credentials/tokens into chat
- **Never** use `--verbose` / `-v` — it can expose auth headers
- **Never** use inline secret flags: `--bearer-token`, `--consumer-key`, `--consumer-secret`, `--access-token`, `--token-secret`, `--client-id`, `--client-secret`
- To verify credentials exist, only use: `xurl auth status`

## Prerequisites

The user must install xurl and complete OAuth setup **outside the agent session**:

```bash
# Install (pick one)
curl -fsSL https://raw.githubusercontent.com/xdevplatform/xurl/main/install.sh | bash
brew install --cask xdevplatform/tap/xurl
npm install -g @xdevplatform/xurl
go install github.com/xdevplatform/xurl@latest
```

One-time auth setup (user runs manually):
1. Create app at https://developer.x.com/en/portal/dashboard
2. Set redirect URI to `http://localhost:8080/callback`
3. `xurl auth apps add my-app --client-id ID --client-secret SECRET`
4. `xurl auth oauth2 --app my-app`
5. `xurl auth default my-app`
6. `xurl whoami` to verify

## Quick Reference

| Action | Command |
|--------|---------|
| Post | `xurl post "text"` |
| Reply | `xurl reply POST_ID "text"` |
| Quote | `xurl quote POST_ID "text"` |
| Delete | `xurl delete POST_ID` |
| Read post | `xurl read POST_ID` |
| Search | `xurl search "query" -n 10` |
| Who am I | `xurl whoami` |
| User info | `xurl user @handle` |
| Timeline | `xurl timeline -n 20` |
| Mentions | `xurl mentions -n 10` |
| Like / Unlike | `xurl like POST_ID` / `xurl unlike POST_ID` |
| Repost / Undo | `xurl repost POST_ID` / `xurl unrepost POST_ID` |
| Bookmark | `xurl bookmark POST_ID` / `xurl unbookmark POST_ID` |
| List bookmarks | `xurl bookmarks -n 10` |
| Follow / Unfollow | `xurl follow @handle` / `xurl unfollow @handle` |
| Send DM | `xurl dm @handle "message"` |
| List DMs | `xurl dms -n 10` |
| Upload media | `xurl media upload path/to/file` |
| Media status | `xurl media status MEDIA_ID` |
| Post with image | `xurl media upload photo.jpg` → `xurl post "caption" --media-id MEDIA_ID` |

Notes:
- POST_ID accepts full URLs (e.g. `https://x.com/user/status/123`)
- Usernames work with or without `@`
- All output is JSON

## Raw API Access

For any v2 endpoint not covered by shortcuts:

```bash
xurl /2/users/me
xurl -X POST /2/tweets -d '{"text":"Hello"}'
xurl -X DELETE /2/tweets/123
```

## Agent Workflow

1. Verify: `xurl --help` and `xurl auth status`
2. Check default app has credentials (look for `▸` marker in auth status)
3. If auth missing, stop and direct user to the prerequisite setup
4. Start with a cheap read (`xurl whoami`) to confirm connectivity
5. **Always confirm with user before any write action** (post, reply, DM, like, follow, delete)
6. Use JSON output directly — every response is structured

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Auth errors after OAuth | `xurl auth oauth2 --app my-app` then `xurl auth default my-app` |
| 401 on every request | Check `xurl auth status` — verify default app has tokens |
| `CreditsDepleted` | Buy credits (min $5) in Developer Console → Billing |
| Media upload fails | Add `--category tweet_image --media-type image/png` |

## Common Workflows

### Monitor and curate content
```bash
xurl search "topic" -n 10
xurl bookmarks -n 20
xurl mentions -n 10
```

### Draft and publish
```bash
xurl media upload image.jpg
xurl post "Content here" --media-id MEDIA_ID
```

### Engage with community
```bash
xurl search "#topic" -n 15
xurl like POST_ID
xurl reply POST_ID "Thoughtful response"
```
