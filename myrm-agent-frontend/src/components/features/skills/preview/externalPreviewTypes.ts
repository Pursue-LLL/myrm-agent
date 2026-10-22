/**
 * External browser clean preview contracts and state types.
 * Solves iframe anti-hotlinking image breakages & CSP restrictions.
 */

export interface ExternalPreviewPayload {
  content: string;
  contentType?: string;
  title?: string;
}

export interface ExternalPreviewResult {
  previewId: string;
  title: string;
  contentType: string;
  viewUrl: string;
}

export type ExternalPreviewButtonStatus = 'idle' | 'opening' | 'success' | 'error';
