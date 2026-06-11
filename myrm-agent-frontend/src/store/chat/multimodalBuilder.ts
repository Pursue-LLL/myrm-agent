import { File } from '@/store/chat/types';
import { partitionFilesByType, getMimeType } from '@/lib/utils/fileUtils';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { fromStoreFile } from '@/services/file-service/types';
import { extractPdfContent, extractDocumentContent } from '@/services/file';
import { toast } from '@/lib/utils/toast';
import useConfigStore from '@/store/useConfigStore';

type VisionTextPart = { type: 'text'; text: string };
type VisionImagePart = { type: 'image_url'; image_url: { url: string; detail: string } };
type VisionVideoPart = { type: 'video_url'; video_url: { url: string; mime_type: string } };
export type VisionContentPart = VisionTextPart | VisionImagePart | VisionVideoPart;

/**
 * Resolve an image file to a URL for the message payload.
 * Tauri mode: reads from disk as base64 data URL (no StorageProvider).
 * Sandbox mode: passes the StorageProvider HTTP URL directly — the harness
 * pipeline resolves it to base64 right before the LLM call, avoiding
 * redundant encoding in checkpoints and message history.
 */
const resolveImageUrl = async (file: File): Promise<string | null> => {
  try {
    if (isTauriRuntime()) {
      const { tauriFileService } = await import('@/services/file-service/tauri');
      return await tauriFileService.readFileAsDataURL(fromStoreFile(file));
    }
    return file.fileUrl || null;
  } catch (err) {
    console.error(`Failed to resolve image URL: ${file.fileName}`, err);
    return null;
  }
};

const buildExtractParams = (file: File): { fileId: string } | { filePath: string } => {
  if (isTauriRuntime()) {
    return { filePath: file.localPath || '' };
  }
  return { fileId: file.id || '' };
};

/**
 * Process PDF files via backend extraction API (parallel).
 * Text-first; when text is sparse, backend renders pages as images.
 * Image parts are always included — the server-side VisionFallback
 * handles routing to a vision model when the primary model lacks vision.
 */
const attachmentReferencePart = (fileName: string): VisionContentPart => ({
  type: 'text',
  text: `[Attachment: ${fileName}]`,
});

const processPdfFiles = async (pdfFiles: File[]): Promise<VisionContentPart[]> => {
  const extractEnabled = useConfigStore.getState().extractDocumentText ?? true;
  if (!extractEnabled) {
    return pdfFiles.map((file) => attachmentReferencePart(file.fileName));
  }

  const results = await Promise.allSettled(
    pdfFiles.map((file) => extractPdfContent(buildExtractParams(file)).then((result) => ({ file, result }))),
  );

  const parts: VisionContentPart[] = [];

  for (const settled of results) {
    if (settled.status === 'rejected') {
      console.error('PDF extraction failed:', settled.reason);
      continue;
    }
    const { file, result } = settled.value;

    if (result.text) {
      parts.push({ type: 'text', text: `[PDF: ${file.fileName}]\n${result.text}` });
    }

    if (result.images && result.images.length > 0) {
      for (const img of result.images) {
        const url = img.fileUrl || `data:${img.mimeType};base64,${img.data}`;
        parts.push({ type: 'image_url', image_url: { url, detail: 'auto' } });
      }

      if (result.imageTrace && result.imageTrace.droppedCount > 0) {
        toast.success(
          `[PDF] 解析优化：已提取 ${result.imageTrace.keptCount} 张核心图像（拦截 ${result.imageTrace.droppedCount} 张视觉噪点，为您节省约 ${result.imageTrace.droppedCount * 2}s 耗时）`,
          { duration: 6000 },
        );
      }
    }
  }

  return parts;
};

/**
 * Process Office document files (.docx/.xlsx/.xls) via backend extraction API (parallel).
 * Backend uses Harness parsers to convert to Markdown text.
 */
const processDocumentFiles = async (docFiles: File[]): Promise<VisionContentPart[]> => {
  const extractEnabled = useConfigStore.getState().extractDocumentText ?? true;
  if (!extractEnabled) {
    return docFiles.map((file) => attachmentReferencePart(file.fileName));
  }

  const results = await Promise.allSettled(
    docFiles.map((file) => extractDocumentContent(buildExtractParams(file)).then((result) => ({ file, result }))),
  );

  const parts: VisionContentPart[] = [];
  for (let i = 0; i < results.length; i++) {
    const settled = results[i];
    if (settled.status === 'rejected') {
      console.error('Document extraction failed:', settled.reason);
      const failedFile = docFiles[i];
      parts.push({
        type: 'text',
        text: `[Document: ${failedFile.fileName}] (Extraction failed — the file may be corrupted or in an unsupported format)`,
      });
      continue;
    }
    const { file, result } = settled.value;
    if (result.text) {
      parts.push({ type: 'text', text: `[Document: ${file.fileName}]\n${result.text}` });
    }
  }
  return parts;
};

/**
 * Process video files by passing their URLs as video_url content parts.
 * Video analysis (frame extraction, native pass-through) is handled server-side
 * by VideoAnalysisEngine based on model capabilities.
 */
const processVideoFiles = async (videoFiles: File[]): Promise<VisionContentPart[]> => {
  const parts: VisionContentPart[] = [];
  for (const file of videoFiles) {
    let url: string;
    if (isTauriRuntime() && file.localPath) {
      const { tauriFileService } = await import('@/services/file-service/tauri');
      url = await tauriFileService.readFileAsDataURL(fromStoreFile(file));
    } else {
      url = file.fileUrl || '';
    }
    if (!url) {
      parts.push({ type: 'text', text: `[Video: ${file.fileName}] (Failed to read video file)` });
      continue;
    }
    const mime = getMimeType(file.fileExtension);
    parts.push({ type: 'video_url', video_url: { url, mime_type: mime } });
  }
  return parts;
};

const MAX_TEXT_INJECT_CHARS = 200_000;

/**
 * Process plain text files (.csv/.txt/.md/.json) by fetching their content directly.
 * Tauri mode reads via native file service; Sandbox mode fetches from storage URL.
 */
const processTextFiles = async (textFiles: File[]): Promise<VisionContentPart[]> => {
  const results = await Promise.allSettled(
    textFiles.map(async (file) => {
      let text: string;
      if (isTauriRuntime() && file.localPath) {
        const { tauriFileService } = await import('@/services/file-service/tauri');
        const dataUrl = await tauriFileService.readFileAsDataURL(fromStoreFile(file));
        const base64 = dataUrl.split(',')[1] || '';
        text = atob(base64);
      } else {
        const url = file.fileUrl || '';
        if (!url) throw new Error(`No URL for text file: ${file.fileName}`);
        const res = await fetch(url);
        if (!res.ok) throw new Error(`Failed to fetch ${file.fileName}: ${res.status}`);
        text = await res.text();
      }
      return { file, text };
    }),
  );

  const parts: VisionContentPart[] = [];
  for (const settled of results) {
    if (settled.status === 'rejected') {
      console.error('Text file read failed:', settled.reason);
      continue;
    }
    const { file, text } = settled.value;
    if (text) {
      const truncated =
        text.length > MAX_TEXT_INJECT_CHARS
          ? text.slice(0, MAX_TEXT_INJECT_CHARS) + `\n\n... [truncated at ${MAX_TEXT_INJECT_CHARS} chars]`
          : text;
      parts.push({ type: 'text', text: `[File: ${file.fileName}]\n${truncated}` });
    }
  }
  return parts;
};

/**
 * Build multimodal query from attached files and optional camera frames.
 *
 * All visual content (images, camera frames, PDF charts) is always included
 * regardless of primary model vision capability — the server-side
 * VisionFallbackEngine handles routing to a vision model when needed.
 *
 * - Camera frames: injected as image_url parts.
 * - Images: converted to base64 data URLs as image_url parts.
 * - Videos: passed as video_url parts for server-side analysis.
 * - PDFs: text-first extraction; sparse-text PDFs rendered as page images.
 * - Documents (.docx/.xlsx/.xls): extracted to Markdown text via backend.
 * - Text files (.csv/.txt/.md/.json): content fetched directly.
 * - If no multimodal content, returns plain text.
 */
export const buildMultimodalQuery = async (
  textInput: string,
  files: File[],
  cameraFrames?: string[],
): Promise<string | VisionContentPart[]> => {
  const { imageFiles, videoFiles, pdfFiles, documentFiles, textFiles } = partitionFilesByType(files);
  const hasCameraFrames = cameraFrames && cameraFrames.length > 0;
  const hasAttachments =
    imageFiles.length > 0 ||
    videoFiles.length > 0 ||
    pdfFiles.length > 0 ||
    documentFiles.length > 0 ||
    textFiles.length > 0;

  if (!hasAttachments && !hasCameraFrames) return textInput;

  const contentParts: VisionContentPart[] = [{ type: 'text', text: textInput }];

  if (hasCameraFrames) {
    for (const frameDataUrl of cameraFrames) {
      contentParts.push({ type: 'image_url', image_url: { url: frameDataUrl, detail: 'auto' } });
    }
  }

  if (imageFiles.length > 0) {
    const imageUrls = await Promise.all(imageFiles.map(resolveImageUrl));
    for (const url of imageUrls) {
      if (url) {
        contentParts.push({ type: 'image_url', image_url: { url, detail: 'auto' } });
      }
    }
  }

  if (videoFiles.length > 0) {
    const videoParts = await processVideoFiles(videoFiles);
    contentParts.push(...videoParts);
  }

  if (pdfFiles.length > 0) {
    const pdfParts = await processPdfFiles(pdfFiles);
    contentParts.push(...pdfParts);
  }

  if (documentFiles.length > 0) {
    const docParts = await processDocumentFiles(documentFiles);
    contentParts.push(...docParts);
  }

  if (textFiles.length > 0) {
    const txtParts = await processTextFiles(textFiles);
    contentParts.push(...txtParts);
  }

  return contentParts.length === 1 ? textInput : contentParts;
};
