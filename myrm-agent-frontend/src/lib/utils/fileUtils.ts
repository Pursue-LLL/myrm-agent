import type { File } from '@/store/chat/types';
import { isTauriRuntime } from '@/lib/deploy-mode';

const IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'avif', 'ico'];
const VIDEO_EXTENSIONS = ['mp4', 'mov', 'webm', 'avi', 'mkv', 'flv', 'wmv', 'm4v'];
const DOCUMENT_EXTENSIONS = ['docx', 'xlsx', 'xls', 'pptx', 'ppt'];
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
};

export const isImageFile = (fileExtension: string): boolean => {
  return IMAGE_EXTENSIONS.includes(fileExtension.toLowerCase());
};

export const isVideoFile = (fileExtension: string): boolean => {
  return VIDEO_EXTENSIONS.includes(fileExtension.toLowerCase());
};

/**
 * Get the display URL for a file, handling both Web (fileUrl) and Tauri (localPath) environments.
 */
export const getDisplayUrl = (file: File): string => {
  if (file.fileUrl) return file.fileUrl;
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
