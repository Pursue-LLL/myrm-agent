/**
 * 文件服务类型定义
 *
 * 定义统一的文件服务接口，支持 Tauri 和 Sandbox 两种模式。
 */

import { File } from '@/store/chat/types';
import type { UploadProgress } from '@/services/file';

/**
 * 文件引用类型
 */
export interface FileReference {
  /** 文件 ID */
  id?: string;
  /** 文件名 */
  fileName: string;
  /** 文件扩展名 */
  fileExtension: string;
  /** 本地路径（Tauri 模式） */
  localPath?: string;
  /** 服务器 URL（Sandbox 模式） */
  fileUrl?: string;
  /** 文件类型 */
  fileType: 'local_path' | 'uploaded';
}

/**
 * 文件服务接口
 *
 * 所有文件服务实现必须满足此接口。
 */
export interface FileService {
  /**
   * 选择文件
   *
   * @returns 选择的文件引用列表
   */
  selectFiles(): Promise<FileReference[]>;

  /**
   * 读取文件内容
   *
   * @param file - 文件引用
   * @returns 文件二进制内容
   */
  readFile(file: FileReference): Promise<Uint8Array>;

  /**
   * 读取文件为 Data URL（用于预览）
   *
   * @param file - 文件引用
   * @returns Data URL 字符串
   */
  readFileAsDataURL(file: FileReference): Promise<string>;

  /**
   * 读取文件为文本
   *
   * @param file - 文件引用
   * @param encoding - 编码格式
   * @returns 文本内容
   */
  readFileAsText(file: FileReference, encoding?: string): Promise<string>;

  /**
   * 获取文件访问 URL
   *
   * @param file - 文件引用
   * @returns 可访问的 URL
   */
  getFileUrl(file: FileReference): string;

  /**
   * 上传文件
   *
   * - Sandbox 模式：上传到服务器
   * - Tauri 模式：抛出错误（本地模式不需要上传）
   *
   * @param files - 原生 File 对象列表
   * @param onProgress - 上传进度回调（可选）
   * @returns 上传后的文件引用列表
   */
  uploadFiles(
    files: globalThis.File[],
    onProgress?: (progress: UploadProgress) => void,
    signal?: AbortSignal,
  ): Promise<FileReference[]>;
}

/**
 * 将 FileReference 转换为 store 中的 File 类型
 */
export function toStoreFile(ref: FileReference): File {
  return {
    id: ref.id,
    fileName: ref.fileName,
    fileExtension: ref.fileExtension,
    localPath: ref.localPath,
    fileUrl: ref.fileUrl,
    fileType: ref.fileType,
  };
}

/**
 * 将 store 中的 File 类型转换为 FileReference
 */
export function fromStoreFile(file: File): FileReference {
  return {
    id: file.id,
    fileName: file.fileName,
    fileExtension: file.fileExtension,
    localPath: file.localPath,
    fileUrl: file.fileUrl,
    fileType: file.fileType,
  };
}
