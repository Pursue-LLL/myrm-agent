/**
 * External browser clean preview service.
 * Dispatches preview registration and triggers real native browser tab.
 */

import { ExternalPreviewPayload, ExternalPreviewResult } from './externalPreviewTypes';

export class ExternalPreviewService {
  /**
   * Register clean preview session with relaxed CSP & no-referrer on server.
   */
  public static async registerPreview(
    payload: ExternalPreviewPayload
  ): Promise<ExternalPreviewResult> {
    const res = await fetch('/api/v1/skills/solidify/preview', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        content: payload.content,
        content_type: payload.contentType || 'text/html',
        title: payload.title || 'Deliverable Preview',
      }),
    });

    if (!res.ok) {
      throw new Error(`Failed to register clean preview: ${res.statusText}`);
    }

    const data = await res.json();
    return {
      previewId: data.preview_id,
      title: data.title,
      contentType: data.content_type,
      viewUrl: data.view_url,
    };
  }

  /**
   * Launch external browser tab to render standalone HTML without iframe constraints.
   */
  public static async openInExternalBrowser(
    payload: ExternalPreviewPayload
  ): Promise<string> {
    try {
      const result = await this.registerPreview(payload);
      if (typeof window !== 'undefined') {
        window.open(result.viewUrl, '_blank', 'noopener,noreferrer');
      }
      return result.viewUrl;
    } catch {
      // Offline / test suite fallback using Blob URL with no-referrer meta
      if (typeof window !== 'undefined' && typeof window.URL !== 'undefined') {
        const relaxedHtml = payload.content.includes('<head>')
          ? payload.content.replace(
              '<head>',
              '<head><meta name="referrer" content="no-referrer">'
            )
          : `<meta name="referrer" content="no-referrer">${payload.content}`;
        const blob = new Blob([relaxedHtml], { type: 'text/html;charset=utf-8' });
        const blobUrl = URL.createObjectURL(blob);
        window.open(blobUrl, '_blank', 'noopener,noreferrer');
        return blobUrl;
      }
      throw new Error('Window environment is not available to launch preview');
    }
  }
}
