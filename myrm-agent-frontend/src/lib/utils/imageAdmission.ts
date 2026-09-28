/**
 * [INPUT]
 * - Browser File / Blob (user upload or paste candidate)
 * - @/lib/utils/fileUtils::isImageFile, getFileExtension
 *
 * [OUTPUT]
 * - admitAndCompressImageFile: 单图准入尺寸检查与超限等比有损速压。
 * - admitAndCompressFiles: 批量文件准入处理。
 *
 * [POS]
 * 前端端侧图片准入与轻量速压防线。
 * 在图片入队和上传前执行尺寸（默认 <=2048px）与体积（默认 <=4MB）预检，
 * 采用 OffscreenCanvas / createImageBitmap 执行无阻塞等比缩放与高效 WebP 压缩，
 * 阻断超大原图（如 30MB+ / 8000px）拖慢上传、爆内存与耗尽模型视觉 Token。
 */

import { isImageFile, getFileExtension } from '@/lib/utils/fileUtils';

export interface ImageAdmissionOptions {
  /**
   * 单边最大像素尺寸（默认 2048px，对齐视觉模型最佳长边输入）。
   */
  maxDimension?: number;
  /**
   * 触发强行压缩的文件体积门限（默认 4MB）。
   */
  maxFileSizeBytes?: number;
  /**
   * 有损压缩质量（0~1，默认 0.82，肉眼无损且体积极小）。
   */
  quality?: number;
  /**
   * 目标输出 MIME（默认 'image/webp'）。
   */
  targetMimeType?: string;
}

const DEFAULT_MAX_DIMENSION = 2048;
const DEFAULT_MAX_FILE_SIZE_BYTES = 4 * 1024 * 1024; // 4MB
const DEFAULT_QUALITY = 0.82;
const DEFAULT_TARGET_MIME = 'image/webp';

/**
 * 替换文件名末尾的扩展名为新扩展名。
 */
function replaceFileExtension(fileName: string, newExt: string): string {
  const lastDot = fileName.lastIndexOf('.');
  if (lastDot <= 0) {
    return `${fileName}.${newExt}`;
  }
  return `${fileName.slice(0, lastDot)}.${newExt}`;
}

/**
 * 将 ImageBitmap 渲染到 Canvas 并导出为指定 MIME 的 Blob。
 */
async function renderBitmapToBlob(
  bitmap: ImageBitmap,
  targetWidth: number,
  targetHeight: number,
  mimeType: string,
  quality: number,
): Promise<Blob | null> {
  if (typeof OffscreenCanvas !== 'undefined') {
    const offscreen = new OffscreenCanvas(targetWidth, targetHeight);
    const ctx = offscreen.getContext('2d');
    if (!ctx) {
      return null;
    }
    ctx.drawImage(bitmap, 0, 0, targetWidth, targetHeight);
    return await offscreen.convertToBlob({ type: mimeType, quality });
  }

  if (typeof document !== 'undefined') {
    const canvas = document.createElement('canvas');
    canvas.width = targetWidth;
    canvas.height = targetHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      return null;
    }
    ctx.drawImage(bitmap, 0, 0, targetWidth, targetHeight);
    return await new Promise<Blob | null>((resolve) => {
      canvas.toBlob(resolve, mimeType, quality);
    });
  }

  return null;
}

/**
 * 单图准入与轻量速压。
 * 若图片尺寸与体积在门限之内，或遇非光栅图（SVG/GIF）与无 Canvas 环境，则无损直接放行原 File。
 */
export async function admitAndCompressImageFile(file: File, options?: ImageAdmissionOptions): Promise<File> {
  const ext = getFileExtension(file.name).toLowerCase();
  const isImage = isImageFile(ext) || file.type.startsWith('image/');
  if (!isImage) {
    return file;
  }

  // 动图与矢量图跳过栅格有损压缩，保留原始动画帧与矢量特性
  if (ext === 'svg' || ext === 'gif' || file.type === 'image/svg+xml' || file.type === 'image/gif') {
    return file;
  }

  // 环境嗅探：无位图解码能力时安全跳过
  if (typeof createImageBitmap === 'undefined') {
    return file;
  }

  const maxDimension = options?.maxDimension ?? DEFAULT_MAX_DIMENSION;
  const maxFileSizeBytes = options?.maxFileSizeBytes ?? DEFAULT_MAX_FILE_SIZE_BYTES;
  const quality = options?.quality ?? DEFAULT_QUALITY;
  const targetMimeType = options?.targetMimeType ?? DEFAULT_TARGET_MIME;

  try {
    const bitmap = await createImageBitmap(file);
    const origWidth = bitmap.width;
    const origHeight = bitmap.height;

    const isOverDimension = origWidth > maxDimension || origHeight > maxDimension;
    const isOverSize = file.size > maxFileSizeBytes;

    // 尺寸与体积均在合规范围，零损耗直接放行
    if (!isOverDimension && !isOverSize) {
      if ('close' in bitmap) {
        bitmap.close();
      }
      return file;
    }

    const scale = Math.min(maxDimension / origWidth, maxDimension / origHeight, 1);
    const targetWidth = Math.max(1, Math.round(origWidth * scale));
    const targetHeight = Math.max(1, Math.round(origHeight * scale));

    const compressedBlob = await renderBitmapToBlob(bitmap, targetWidth, targetHeight, targetMimeType, quality);

    if ('close' in bitmap) {
      bitmap.close();
    }

    if (!compressedBlob) {
      return file;
    }

    // 保底机制：若极端情况下压缩后体积未减少且尺寸未缩，放行原图
    if (compressedBlob.size >= file.size && !isOverDimension) {
      return file;
    }

    const newFileName =
      targetMimeType === 'image/webp' && ext !== 'webp' ? replaceFileExtension(file.name, 'webp') : file.name;

    return new File([compressedBlob], newFileName, {
      type: targetMimeType,
      lastModified: Date.now(),
    });
  } catch (error) {
    console.warn(`[imageAdmission] Failed to downsample image ${file.name}, using original:`, error);
    return file;
  }
}

/**
 * 批量文件准入处理，非图片或合规文件保持原样，超标图片完成并发速压。
 */
export async function admitAndCompressFiles(files: File[], options?: ImageAdmissionOptions): Promise<File[]> {
  if (files.length === 0) {
    return [];
  }
  return Promise.all(files.map((file) => admitAndCompressImageFile(file, options)));
}
