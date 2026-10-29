/**
 * Client-side Service for Session HTML Export & Share Links.
 *
 * [INPUT] lib/api.ts::apiRequest, sessionExportTypes.ts
 * [OUTPUT] sessionExportService: Authenticated REST client whose failures reject (nothing is fabricated) and the Blob file trigger.
 * [POS] src/components/features/session-export/sessionExportService.ts
 */

import { apiRequest } from '@/lib/api';
import type {
  ExportHtmlOptions,
  InteractiveHtmlExportResult,
  RedactionSummary,
  ShareLinkRequest,
  ShareLinkResponse,
} from './sessionExportTypes';

/** Compiling a long conversation takes longer than the default request budget. */
const EXPORT_TIMEOUT_MS = 120_000;

class SessionExportService {
  exportInteractiveHtml(
    chatId: string,
    options: ExportHtmlOptions,
  ): Promise<InteractiveHtmlExportResult> {
    return apiRequest<InteractiveHtmlExportResult>(`/chats/${chatId}/export/interactive-html`, {
      method: 'POST',
      body: JSON.stringify(options),
      timeout: EXPORT_TIMEOUT_MS,
      silent: true,
    });
  }

  previewRedaction(chatId: string): Promise<RedactionSummary> {
    return apiRequest<RedactionSummary>(`/chats/${chatId}/export/redact-preview`, {
      method: 'POST',
      silent: true,
    });
  }

  createShareLink(chatId: string, req: ShareLinkRequest): Promise<ShareLinkResponse> {
    return apiRequest<ShareLinkResponse>(`/chats/${chatId}/export/share-link`, {
      method: 'POST',
      body: JSON.stringify(req),
      silent: true,
    });
  }

  triggerDownload(fileName: string, content: string): void {
    if (typeof window === 'undefined') {
      return;
    }
    const blob = new Blob([content], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }
}

export const sessionExportService = new SessionExportService();
