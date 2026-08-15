/**
 * [INPUT]
 * - @/store/chat/types::File (POS: @/store/chat/types 稳定入口；实现位于 types/)
 * - @/lib/deploy-mode::isTauriRuntime (POS: 前端部署模式与基础地址解析层)
 *
 * [OUTPUT]
 * - getDisplayUrl: Web/Tauri 文件展示 URL 解析。
 * - fetchFileAsBase64DataURL: 文件 URL → base64 data URL。
 * - partitionFilesByType / isXxxFile / getFileExtension / getMimeType: 扩展名分类与 MIME 推断。
 * - computeFileHash: Blob/File SHA-256 哈希。
 * - sanitizeFilename: 文件名非法字符清理（空名回退 Untitled）。
 * - buildZipFromFiles: 「路径 → 内容」字典 → DEFLATE zip Blob。
 * - triggerDownload: 触发文件下载（Web a[download] / Tauri 系统保存对话框）。
 *
 * [POS]
 * 通用文件工具集。提供扩展名分类、MIME 推断、哈希计算、zip 打包与 Blob 下载等纯函数能力。
 */
import type { File } from '@/store/chat/types';
import { isTauriRuntime } from '@/lib/deploy-mode';

const IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'avif', 'ico'];
const VIDEO_EXTENSIONS = ['mp4', 'mov', 'webm', 'avi', 'mkv', 'flv', 'wmv', 'm4v'];
const AUDIO_EXTENSIONS = ['mp3', 'wav', 'ogg', 'flac', 'm4a', 'aac', 'wma', 'opus'];
const DOCUMENT_EXTENSIONS = ['docx', 'xlsx', 'xls', 'pptx', 'ppt', 'ipynb'];
const TEXT_EXTENSIONS = ['csv', 'txt', 'md', 'json'];

const EXTENSION_TO_MIME: Record<string, string> = {
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  gif: 'image/gif',
  webp: 'image/webp',
  bmp: 'image/bmp',
  pdf: 'application/pdf',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  xls: 'application/vnd.ms-excel',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  ppt: 'application/vnd.ms-powerpoint',
  csv: 'text/csv',
  txt: 'text/plain',
  md: 'text/markdown',
  json: 'application/json',
  mp4: 'video/mp4',
  mov: 'video/quicktime',
  webm: 'video/webm',
  avi: 'video/x-msvideo',
  mkv: 'video/x-matroska',
  flv: 'video/x-flv',
  wmv: 'video/x-ms-wmv',
  m4v: 'video/x-m4v',
  mp3: 'audio/mpeg',
  wav: 'audio/wav',
  ogg: 'audio/ogg',
  flac: 'audio/flac',
  m4a: 'audio/mp4',
  aac: 'audio/aac',
  wma: 'audio/x-ms-wma',
  opus: 'audio/opus',
};

export const isImageFile = (fileExtension: string): boolean => {
  return IMAGE_EXTENSIONS.includes(fileExtension.toLowerCase());
};

export const isVideoFile = (fileExtension: string): boolean => {
  return VIDEO_EXTENSIONS.includes(fileExtension.toLowerCase());
};

export const isAudioFile = (fileExtension: string): boolean => {
  return AUDIO_EXTENSIONS.includes(fileExtension.toLowerCase());
};

/**
 * Get the display URL for a file, handling both Web (fileUrl) and Tauri (localPath) environments.
 */
export const getDisplayUrl = (file: File): string => {
  if (file.fileUrl) {return file.fileUrl;}
  if (isTauriRuntime() && file.localPath) {
    try {
      const { convertFileSrc } = require('@tauri-apps/api/core');
      return convertFileSrc(file.localPath) as string;
    } catch {
      return '';
    }
  }
  return '';
};

/**
 * Fetch a file URL and return its base64 data URL via FileReader (native, efficient).
 * Works for both server-hosted URLs and blob: / asset: URLs.
 */
export const fetchFileAsBase64DataURL = async (url: string, mimeType: string): Promise<string> => {
  const res = await fetch(url);
  const blob = await res.blob();
  const typedBlob = blob.type ? blob : new Blob([blob], { type: mimeType });
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result as string);
    reader.onerror = () => reject(new Error(`FileReader failed for ${url}`));
    reader.readAsDataURL(typedBlob);
  });
};

/**
 * Partition files into image / video / PDF / document / text / other buckets.
 */
export const partitionFilesByType = (
  files: File[],
): {
  imageFiles: File[];
  videoFiles: File[];
  pdfFiles: File[];
  documentFiles: File[];
  textFiles: File[];
  otherFiles: File[];
} => {
  const imageFiles: File[] = [];
  const videoFiles: File[] = [];
  const pdfFiles: File[] = [];
  const documentFiles: File[] = [];
  const textFiles: File[] = [];
  const otherFiles: File[] = [];
  for (const f of files) {
    if (isImageFile(f.fileExtension)) {
      imageFiles.push(f);
    } else if (isVideoFile(f.fileExtension)) {
      videoFiles.push(f);
    } else if (isPdfFile(f.fileExtension)) {
      pdfFiles.push(f);
    } else if (isDocumentFile(f.fileExtension)) {
      documentFiles.push(f);
    } else if (isTextFile(f.fileExtension)) {
      textFiles.push(f);
    } else {
      otherFiles.push(f);
    }
  }
  return { imageFiles, videoFiles, pdfFiles, documentFiles, textFiles, otherFiles };
};

/**
 * Get MIME type from file extension.
 */
export const getMimeType = (extension: string): string => {
  return EXTENSION_TO_MIME[extension.toLowerCase()] || 'application/octet-stream';
};

/**
 * Compute SHA-256 hash of a native File/Blob (Web Crypto API).
 * Returns lowercase hex string.
 */
export const computeFileHash = async (file: globalThis.File | Blob): Promise<string> => {
  const buffer = await file.arrayBuffer();
  const bytes = buffer instanceof ArrayBuffer ? new Uint8Array(buffer) : new Uint8Array();
  const hashBuffer = await crypto.subtle.digest('SHA-256', bytes);
  const hashArray = new Uint8Array(hashBuffer);
  return Array.from(hashArray, (b) => b.toString(16).padStart(2, '0')).join('');
};

export const isPdfFile = (fileExtension: string): boolean => {
  return fileExtension.toLowerCase() === 'pdf';
};

export const isDocumentFile = (fileExtension: string): boolean => {
  return DOCUMENT_EXTENSIONS.includes(fileExtension.toLowerCase());
};

export const isTextFile = (fileExtension: string): boolean => {
  return TEXT_EXTENSIONS.includes(fileExtension.toLowerCase());
};

export const getFileExtension = (fileName: string): string => {
  return fileName.split('.').pop()?.toLowerCase() || '';
};

/**
 * 清理文件名中的非法字符（跨平台保留字符与控制字符），空名回退为 Untitled。
 */
export function sanitizeFilename(name: string): string {
  // eslint-disable-next-line no-control-regex
  return name.replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').trim() || 'Untitled';
}

/**
 * 将「路径 → 内容」字典打包为 DEFLATE zip Blob。
 * 目录路径由 key 携带（如 `skills/myrm-memory/SKILL.md`），保持 zip 内目录结构。
 * JSZip 动态导入避免打进主 bundle，与 batchExport / WikiSection 打包先例一致。
 */
export async function buildZipFromFiles(files: Record<string, string>): Promise<Blob> {
  const { default: JSZip } = await import('jszip');
  const zip = new JSZip();
  for (const [path, content] of Object.entries(files)) {
    zip.file(path, content);
  }
  return zip.generateAsync({ type: 'blob', compression: 'DEFLATE' });
}

/**
 * 触发文件下载。
 * - Tauri 桌面端：弹出系统保存对话框并将 Blob 写入用户选择的路径。
 *   WKWebView/WebView2 的 `<a download>` + blob URL 下载不可靠，官方推荐 dialog.save + fs.writeFile。
 * - Web 端：保留 a[download] 下载逻辑。
 * @param blob 文件内容
 * @param filename 建议文件名
 * @returns Promise；Tauri 端用户取消保存对话框时正常 resolve，写入失败则 reject
 */
export async function triggerDownload(blob: Blob, filename: string): Promise<void> {
  if (isTauriRuntime()) {
    const [{ save }, { writeFile }] = await Promise.all([
      import('@tauri-apps/plugin-dialog'),
      import('@tauri-apps/plugin-fs'),
    ]);
    const path = await save({ defaultPath: filename });
    if (!path) {return;} // 用户取消保存
    await writeFile(path, new Uint8Array(await blob.arrayBuffer()));
    return;
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
