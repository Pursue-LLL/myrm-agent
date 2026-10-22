/**
 * Domain types for Session Interactive HTML Export & Gist Share Bridge.
 *
 * [INPUT] None (Standard TypeScript)
 * [OUTPUT] Pure domain types for standalone HTML compilation, credential scrubbing, and share links.
 * [POS] src/components/features/session-export/sessionExportTypes.ts
 */

export interface RedactedPatternDetail {
  pattern_type: string;
  count: number;
  placeholder: string;
}

export interface RedactionSummary {
  total_redacted: number;
  has_secrets: boolean;
  details: RedactedPatternDetail[];
}

export interface ExportHtmlOptions {
  include_thinking: boolean;
  include_tool_calls: boolean;
  enable_redaction: boolean;
  theme: 'system' | 'light' | 'dark';
}

export interface InteractiveHtmlExportResult {
  chat_id: string;
  title: string;
  file_name: string;
  html_content: string;
  size_bytes: number;
  total_messages: number;
  redaction_summary: RedactionSummary;
}

export interface ShareLinkRequest {
  ttl_seconds?: number;
  password?: string | null;
}

export interface ShareLinkResponse {
  chat_id: string;
  share_url: string;
  share_token: string;
  expires_at_unix: number;
  is_password_protected: boolean;
}
