/**
 * Sandbox 文件服务实现
 *
 * 使用 HTTP API 进行文件操作：
 * - 通过 input[type=file] 选择文件
 * - 上传到服务器
 * - 使用服务器返回的 URL
 */

import { uploadFiles as apiUploadFiles, uploadFilesWithProgress, type UploadProgress } from '@/services/file';
import { FileReference, FileService } from './types';

/**
 * MIME 类型映射
 */
const MIME_TYPES: Record<string, string> = {
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  gif: 'image/gif',
  webp: 'image/webp',
  pdf: 'application/pdf',
  txt: 'text/plain',
  csv: 'text/csv',
};

/**
 * Sandbox 文件服务
 */
export const sandboxFileService: FileService = {
  /**
   * 选择文件（Sandbox 模式由 AttachButton 的 input[type=file] 处理）
   *
   * 这个方法在 Sandbox 模式下不直接使用，
   * 因为文件选择和上传是在 AttachButton 中一起处理的。
   */
  async selectFiles(): Promise<FileReference[]> {
    // Sandbox 模式下，文件选择由 AttachButton 的 input[type=file] 处理
    // 这里返回空数组，实际的选择逻辑在组件中
    console.warn('sandboxFileService.selectFiles() should not be called directly');
    return [];
  },

  /**
   * 通过 fetch 读取远程文件
   */
  async readFile(file: FileReference): Promise<Uint8Array> {
    if (!file.fileUrl) {
      throw new Error('无效的文件引用：缺少文件 URL');
    }

    try {
      const response = await fetch(file.fileUrl);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const arrayBuffer = await response.arrayBuffer();
      return new Uint8Array(arrayBuffer);
    } catch (error) {
      console.error('下载文件失败:', error);
      throw new Error(`无法下载文件：${file.fileName}`);
    }
  },

  /**
   * 读取文件为 Data URL
   */
  async readFileAsDataURL(file: FileReference): Promise<string> {
    // 如果已经有 URL，可以直接返回（对于图片预览）
    if (file.fileUrl && file.fileExtension.match(/^(png|jpg|jpeg|gif|webp)$/i)) {
      return file.fileUrl;
    }

    const content = await this.readFile(file);
    const mimeType = MIME_TYPES[file.fileExtension.toLowerCase()] || 'application/octet-stream';
    const blob = new Blob([content.buffer as ArrayBuffer], { type: mimeType });

    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result as string);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  },

  /**
   * 读取文件为文本
   */
  async readFileAsText(file: FileReference, encoding = 'utf-8'): Promise<string> {
    const content = await this.readFile(file);
    const decoder = new TextDecoder(encoding);
    return decoder.decode(content);
  },

  /**
   * 获取文件 URL（直接返回服务器 URL）
   */
  getFileUrl(file: FileReference): string {
    if (!file.fileUrl) {
      throw new Error('无效的文件引用：缺少文件 URL');
    }
    return file.fileUrl;
  },

  /**
   * 上传文件到服务器（支持可选进度回调）
   */
  async uploadFiles(
    files: globalThis.File[],
    onProgress?: (progress: UploadProgress) => void,
    signal?: AbortSignal,
  ): Promise<FileReference[]> {
    try {
      const response = onProgress
        ? await uploadFilesWithProgress(files, onProgress, signal)
        : await apiUploadFiles(files, signal);

      if (response.uploaded_count === 0 || !response.files) {
        return [];
      }

      return response.files.map((file) => ({
        id: file.fileId,
        fileName: file.fileName,
        fileExtension: file.fileName.split('.').pop() || '',
        fileUrl: file.fileUrl,
        fileType: 'uploaded' as const,
      }));
    } catch (error) {
      console.error('上传文件失败:', error);
      if (error instanceof Error) {
        throw error;
      }
      throw new Error('文件上传失败，请重试');
    }
  },
};

export default sandboxFileService;
