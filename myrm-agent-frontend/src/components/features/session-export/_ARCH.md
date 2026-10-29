# session-export

Interactive Single-File HTML Exporter and Share Bridge Feature.

## Overview

Provides client-side capabilities to export multi-turn conversations into zero-network standalone interactive HTML files and issue secure time-limited HMAC read-only share links:

1. Interactive Standalone HTML: Self-contained compilation bundling inlined CSS, code block copy triggers, collapsible thinking/tool-call drawers, and full-text instant search.
2. Secret Redaction Preview: Visual security indicator reporting the high-risk API keys, tokens, passwords, and internal IPs stored in the conversation, with toggle protection.
3. Secure Web Share Bridge: Generates time-limited (7-day / 30-day) stateless HMAC URLs with optional password protection.

## File Structure

| File                          | Status    | Description                                                                                                                                                                |
| ----------------------------- | --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sessionExportTypes.ts`       | Core      | Pure domain types for export options, redaction summaries and scan states, compile results, and share link contracts.                                                      |
| `sessionExportService.ts`     | Service   | Authenticated REST client (`apiRequest`) for export, credential preview by chat id and share link; a failed request rejects, nothing is fabricated. Blob download trigger. |
| `SecretRedactionPreview.tsx`  | Component | Security panel with four scan states (scanning, unavailable, clean, found) and the auto-redact switch; a scan that did not finish never reads as clean.                    |
| `ShareLinkPanel.tsx`          | Component | Share-link tab: expiry window, optional passcode, generated link with copy button.                                                                                         |
| `SessionExportShareModal.tsx` | Component | Dual-mode modal: scans the stored conversation on open, downloads the HTML bundle or issues a share link, and shows a localized notice when a request fails.               |
| `index.ts`                    | Export    | Public entry barrel for all session-export types, services, and components.                                                                                                |
