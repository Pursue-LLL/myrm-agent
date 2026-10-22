# session-export

Interactive Single-File HTML Exporter and Share Bridge Feature.

## Overview
Provides client-side capabilities to export multi-turn conversations into zero-network standalone interactive HTML files and issue secure time-limited HMAC read-only share links:
1. Interactive Standalone HTML: Self-contained compilation bundling inlined CSS, code block copy triggers, collapsible thinking/tool-call drawers, and full-text instant search.
2. Secret Redaction Preview: Visual security indicator detecting high-risk API keys, tokens, passwords, and internal IPs with toggle protection.
3. Secure Web Share Bridge: Generates time-limited (7-day / 30-day) stateless HMAC URLs with optional password protection.

## File Structure

| File | Status | Description |
| --- | --- | --- |
| `sessionExportTypes.ts` | Core | Pure domain types for export options, redaction summaries, compile results, and share link contracts. |
| `sessionExportService.ts` | Service | Client REST API service with offline standalone HTML compilation and Blob download triggers. |
| `SecretRedactionPreview.tsx` | Component | Security inspection panel displaying detected sensitive patterns and auto-redact switch. |
| `SessionExportShareModal.tsx` | Component | Dual-mode modal dialog supporting standalone HTML download and HMAC share link generation. |
| `index.ts` | Export | Public entry barrel for all session-export types, services, and components. |
