import { exportChat } from '@/services/chat';
import { formatChatAsMarkdown, formatChatAsJson, sanitizeFilename, type ExportData } from './chatExport';

/**
 * [INPUT] chatId[] + 导出格式 + 进度/取消回调。
 * [OUTPUT] ZIP Blob（按日期分文件夹 + DEFLATE 压缩）。
 * [POS] 批量导出编排器，复用 chatExport 格式化 + exportChat API。
 */

export type BatchExportFormat = 'markdown' | 'json' | 'html';

export interface BatchExportProgress {
  current: number;
  total: number;
  currentTitle: string;
  skipped: number;
  failed: number;
}

export interface BatchExportResult {
  exported: number;
  skipped: number;
  failed: number;
}

const BATCH_SIZE = 10;

const FORMAT_EXT: Record<BatchExportFormat, string> = {
  markdown: 'md',
  json: 'json',
  html: 'html',
};

async function formatContent(
  data: ExportData,
  format: BatchExportFormat,
  theme: 'light' | 'dark',
  lang: 'en' | 'zh',
): Promise<string> {
  switch (format) {
    case 'markdown':
      return formatChatAsMarkdown(data);
    case 'json':
      return formatChatAsJson(data);
    case 'html': {
      const { buildHtmlDocument } = await import('./chatExportHtml');
      return buildHtmlDocument(data, theme, lang);
    }
  }
}

function dateFolderName(isoDate: string): string {
  const d = new Date(isoDate);
  if (isNaN(d.getTime())) return 'unknown-date';
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export async function batchExportAsZip(
  chatIds: string[],
  format: BatchExportFormat,
  options: {
    theme: 'light' | 'dark';
    lang: 'en' | 'zh';
    onProgress?: (progress: BatchExportProgress) => void;
    signal?: AbortSignal;
  },
): Promise<{ blob: Blob; result: BatchExportResult }> {
  const { default: JSZip } = await import('jszip');
  const zip = new JSZip();

  let exported = 0;
  let skipped = 0;
  let failed = 0;
  const usedPaths = new Set<string>();

  for (let i = 0; i < chatIds.length; i++) {
    if (options.signal?.aborted) {
      throw new DOMException('Export cancelled', 'AbortError');
    }

    const chatId = chatIds[i];
    const title = `Chat ${i + 1}`;

    options.onProgress?.({
      current: i + 1,
      total: chatIds.length,
      currentTitle: title,
      skipped,
      failed,
    });

    try {
      const data = await exportChat(chatId);

      if (data.messages.length === 0) {
        skipped++;
        continue;
      }

      const chatTitle = sanitizeFilename(data.chat.title || `Untitled-${chatId.slice(0, 8)}`);
      const folder = dateFolderName(data.chat.createdAt);
      const ext = FORMAT_EXT[format];

      let path = `${folder}/${chatTitle}.${ext}`;
      if (usedPaths.has(path)) {
        path = `${folder}/${chatTitle}-${chatId.slice(0, 8)}.${ext}`;
      }
      usedPaths.add(path);

      options.onProgress?.({
        current: i + 1,
        total: chatIds.length,
        currentTitle: data.chat.title || chatTitle,
        skipped,
        failed,
      });

      const content = await formatContent(data, format, options.theme, options.lang);
      zip.file(path, content);
      exported++;
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') throw err;
      console.error(`[batchExport] Failed to export chat ${chatId}:`, err);
      failed++;
    }

    if ((i + 1) % BATCH_SIZE === 0 && i + 1 < chatIds.length) {
      await new Promise((r) => setTimeout(r, 50));
    }
  }

  const blob = await zip.generateAsync({
    type: 'blob',
    compression: 'DEFLATE',
    compressionOptions: { level: 6 },
  });

  return { blob, result: { exported, skipped, failed } };
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
