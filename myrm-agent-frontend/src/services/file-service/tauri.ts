/**
 * Tauri 文件服务实现
 *
 * 使用 Tauri 原生 API 进行文件操作：
 * - 本地文件对话框选择
 * - 直接读取本地文件
 * - file:// 或 asset:// URL
 */

import { open } from '@tauri-apps/plugin-dialog';
import { readFile } from '@tauri-apps/plugin-fs';
import { convertFileSrc } from '@tauri-apps/api/core';
import { FileReference, FileService } from './types';

/**
 * 支持的文件扩展名
 */
const SUPPORTED_EXTENSIONS = ['png', 'jpeg', 'jpg', 'gif', 'webp', 'bmp', 'pdf'];

/**
 * MIME 类型映射
 */
const MIME_TYPES: Record<string, string> = {
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  gif: 'image/gif',
  webp: 'image/webp',
  bmp: 'image/bmp',
  pdf: 'application/pdf',
};

/**
 * Tauri 文件服务
 */
export const tauriFileService: FileService = {
  /**
   * 上传文件（Tauri 模式不支持）
   *
   * Tauri 模式使用本地文件选择，不需要上传。
   */
  async uploadFiles(): Promise<FileReference[]> {
    throw new Error('Tauri 模式不支持上传文件，请使用 selectFiles() 选择本地文件');
  },

  /**
   * 使用 Tauri 原生对话框选择文件
   */
  async selectFiles(): Promise<FileReference[]> {
    try {
      const selected = await open({
        multiple: true,
        filters: [
          {
            name: 'Supported Files',
            extensions: SUPPORTED_EXTENSIONS,
          },
        ],
      });

      if (!selected) {
        return [];
      }

      const paths = Array.isArray(selected) ? selected : [selected];

      return paths.map((path) => {
        // 兼容 Unix 和 Windows 路径
        const separator = path.includes('\\') ? '\\' : '/';
        const fileName = path.split(separator).pop() || 'unknown';
        const fileExtension = fileName.split('.').pop() || '';

        return {
          fileName,
          fileExtension,
          localPath: path,
          fileType: 'local_path' as const,
        };
      });
    } catch (error) {
      console.error('文件选择失败:', error);
      throw new Error('文件选择失败，请重试');
    }
  },

  /**
   * 直接读取本地文件
   */
  async readFile(file: FileReference): Promise<Uint8Array> {
    if (!file.localPath) {
      throw new Error('无效的文件引用：缺少本地路径');
    }

    try {
      return await readFile(file.localPath);
    } catch (error) {
      console.error('读取文件失败:', error);
      throw new Error(`无法读取文件：${file.fileName}`);
    }
  },

  /**
   * 读取文件为 Data URL
   */
  async readFileAsDataURL(file: FileReference): Promise<string> {
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
   * 获取文件 URL（使用 Tauri 的 convertFileSrc）
   */
  getFileUrl(file: FileReference): string {
    if (!file.localPath) {
      throw new Error('无效的文件引用：缺少本地路径');
    }
    // 使用 Tauri API 转换为安全的 asset:// URL
    return convertFileSrc(file.localPath);
  },
};

export default tauriFileService;
