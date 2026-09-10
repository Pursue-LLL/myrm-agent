---
name: desktop-browser-profile-bridge
description: "Desktop native browser profile detection, read-only session reuse, and isolated cookie snapshot bridge for authenticated intranet and SSO task automation."
version: "1.0.0"
category: "automation"
tags:
  - browser-automation
  - profile-bridge
  - session-reuse
  - desktop-native
  - hermes-agent
  - cdp
allowed-tools:
  - bash_code_execute_tool
  - file_read_tool
  - file_write_tool
---

# Desktop Native Browser Profile Bridge & Session Reuse Protocol (桌面原生浏览器 Profile 桥接与会话复用协议)

## Overview

Based on architecture principles from Hermes Agent v0.21.0 Pantheon ("Pantheon Release: Controlling Desktop Browsers & Reusing Sessions"), this skill equips the Agent with **authenticated browser execution capabilities**.
Instead of launching a cold, unauthenticated browser that gets blocked by enterprise Single Sign-On (Okta, Feishu, Google Workspace, GitHub 2FA), this protocol creates a **read-only isolated session snapshot** from the user's host desktop browser (Chrome, Edge, Brave) to seamlessly execute automation tasks.

---

## 1. Safety Gates & Boundaries (安全红线)

1. **Zero Raw Master Key Export (严禁导出主密码)**:
   - Never attempt to dump master operating system keychains or decrypt foreign passwords.
2. **Read-Only SQLite Clone (只读副本隔离)**:
   - Operating system Chrome profiles lock `Cookies` SQLite databases when running (`database is locked`).
   - The Agent MUST copy the required session files to an ephemeral temporary directory (`/tmp/myrm_browser_profile_*`) before opening.
3. **Domain Whitelisting (目标域名白名单)**:
   - Only session tokens corresponding to the task's explicitly authorized domain (e.g. `*.internal.net`, `jira.corp.com`) are injected.
4. **Immediate Ephemeral Cleanup (任务完成即刻销毁)**:
   - When the automation run concludes, the temporary snapshot directory is wiped immediately.

---

## 2. The 4-Phase Operating Lifecycle

```
[Task Initiated] ──> [1. Host Browser Detection & Port Check]
                                   │
                                   ▼
                      [2. Ephemeral Profile Snapshot & Domain Filtering]
                                   │
                                   ▼
                      [3. Driver Attachment & Session Validation]
                                   │
                                   ▼
                      [4. Task Execution & Ephemeral Teardown]
```

### Phase 1: Host Browser Detection & Port Check (宿主浏览器探测)
- Inspect standard OS profile locations:
  - macOS: `~/Library/Application Support/Google/Chrome/Default`
  - Linux: `~/.config/google-chrome/Default`
  - Windows: `%LOCALAPPDATA%\Google\Chrome\User Data\Default`
- Check if a running Chrome instance exposes Remote Debugging Port (`--remote-debugging-port=9222`).

### Phase 2: Ephemeral Profile Snapshot (临时隔离镜像)
- Create isolated sandbox directory: `mkdir -p /tmp/myrm_session_mirror`
- Copy relevant state files (`Network/Cookies`, `Local State`, `Preferences`) safely.
- Never write back to the user's live profile directory.

### Phase 3: Driver Attachment & Validation (驱动附加与登录态校验)
- Attach Patchright / Playwright using `launch_persistent_context` pointing to the snapshot directory.
- Navigate to the target URL; assert that no redirect to a login/SSO URL occurs.
- If expired, gracefully prompt the user for human-in-the-loop (HITL) refresh.

### Phase 4: Task Execution & Ephemeral Teardown (执行与销毁)
- Execute required data extraction, report downloading, or form submission.
- Close browser context.
- Wipe `/tmp/myrm_session_mirror` completely.

---

## 3. Pre-flight Verification Gate

Before running automated browser tasks:
- [ ] Target URL is explicitly within user authorization boundaries.
- [ ] Snapshot directory is outside the main user profile path.
- [ ] No credential or sensitive password files are dumped or logged.
- [ ] Teardown hooks are registered to guarantee cleanup on task crash or exit.
