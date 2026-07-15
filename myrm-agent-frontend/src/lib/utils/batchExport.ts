import { exportChat } from '@/services/chat';
import { formatChatAsMarkdown, formatChatAsJson, sanitizeFilename, type ExportData } from './chatExport';

/**
 * [INPUT] services/chat::exportChat (POS: 聊天 API 请求层) — 单聊天导出接口；
 *         chatExport (POS: 聊天导出数据与文件生成工具) — 格式化 + sanitizeFilename；
 *         jszip (external) — ZIP 打包；调用方传入 chatId[] + 格式 + 进度/取消回调。
 * [OUTPUT] batchExportAsZip, BatchExportFormat, BatchExportProgress, BatchExportResult;
 *          re-exports downloadBlob from chatExport.
 * [POS] 批量导出编排器。3 并发 + 1 次重试调用 exportChat，按日期归档为 DEFLATE ZIP。
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

const CONCURRENCY = 3;

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
  let completed = 0;
  const usedPaths = new Set<string>();

  const queue = chatIds.map((id, i) => ({ id, index: i }));
  let queuePos = 0;

  async function processOne(): Promise<void> {
    while (queuePos < queue.length) {
      if (options.signal?.aborted) throw new DOMException('Export cancelled', 'AbortError');

      const { id: chatId, index } = queue[queuePos++];

      options.onProgress?.({
        current: ++completed,
        total: chatIds.length,
        currentTitle: `Chat ${index + 1}`,
        skipped,
        failed,
      });

      try {
        let data: ExportData;
        try {
          data = await exportChat(chatId);
        } catch (retryErr) {
          if (retryErr instanceof DOMException && retryErr.name === 'AbortError') throw retryErr;
          data = await exportChat(chatId);
        }

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
          current: completed,
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
    }
  }

  const workers = Array.from({ length: Math.min(CONCURRENCY, chatIds.length) }, () => processOne());
  await Promise.all(workers);

  const blob = await zip.generateAsync({
    type: 'blob',
    compression: 'DEFLATE',
    compressionOptions: { level: 6 },
  });

  return { blob, result: { exported, skipped, failed } };
}

export { downloadBlob } from './chatExport';
