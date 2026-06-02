/**
 * 文件服务入口
 *
 * 根据运行环境自动选择合适的文件服务实现：
 * - Tauri 桌面端：使用本地文件系统
 * - 其他环境：使用 HTTP API
 */

import { isTauriRuntime } from '@/lib/deploy-mode';
import { FileService, FileReference, toStoreFile, fromStoreFile } from './types';

// 服务单例缓存
let _fileService: FileService | null = null;

/**
 * 获取文件服务实例
 *
 * 使用单例模式，首次调用时根据平台创建对应的服务实例。
 *
 * @returns 文件服务实例
 */
export function getFileService(): FileService {
  if (_fileService) {
    return _fileService;
  }

  let service: FileService;
  if (isTauriRuntime()) {
    // Tauri 桌面端：动态导入本地文件服务
    const { tauriFileService } = require('./tauri');
    service = tauriFileService;
  } else {
    // Sandbox 模式：使用云端文件服务
    const { sandboxFileService } = require('./sandbox');
    service = sandboxFileService;
  }

  _fileService = service;
  return service;
}

/**
 * 重置文件服务（仅用于测试）
 */
export function resetFileService(): void {
  _fileService = null;
}

// 导出类型和工具函数
export type { FileService, FileReference };
export { toStoreFile, fromStoreFile };

// 导出便捷方法
export const selectFiles = () => getFileService().selectFiles();
export const readFile = (file: FileReference) => getFileService().readFile(file);
export const readFileAsDataURL = (file: FileReference) => getFileService().readFileAsDataURL(file);
export const readFileAsText = (file: FileReference, encoding?: string) =>
  getFileService().readFileAsText(file, encoding);
export const getFileUrl = (file: FileReference) => getFileService().getFileUrl(file);
