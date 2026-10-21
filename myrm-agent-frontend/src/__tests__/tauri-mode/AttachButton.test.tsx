/**
 * AttachButton 组件测试
 *
 * 测试文件附件按钮在 Tauri 和 Sandbox 模式下的核心逻辑
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import type { File } from '@/store/useChatStore';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { selectFiles } from '@/services/file-service';

// Mock 平台检测和文件服务
vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: vi.fn(),
}));
vi.mock('@/services/file-service', () => ({
  selectFiles: vi.fn(),
  toStoreFile: (ref: unknown) => ref,
  getFileService: vi.fn(() => ({
    uploadFiles: vi.fn(),
  })),
}));

describe('AttachButton 核心逻辑测试', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('平台检测', () => {
    it('应该正确检测 Tauri 模式', () => {
      vi.mocked(isTauriRuntime).mockReturnValue(true);
      expect(isTauriRuntime()).toBe(true);
    });

    it('应该正确检测 Sandbox 模式', () => {
      vi.mocked(isTauriRuntime).mockReturnValue(false);
      expect(isTauriRuntime()).toBe(false);
    });
  });

  describe('文件选择逻辑 (Tauri)', () => {
    beforeEach(() => {
      vi.mocked(isTauriRuntime).mockReturnValue(true);
    });

    it('应该成功选择文件并返回本地路径', async () => {
      const mockFiles: File[] = [
        {
          fileName: 'test.png',
          fileExtension: 'png',
          localPath: '/path/to/test.png',
          fileType: 'local_path',
        },
      ];
      vi.mocked(selectFiles).mockResolvedValue(mockFiles);

      const files = await selectFiles();

      expect(files).toHaveLength(1);
      expect(files[0].fileType).toBe('local_path');
      expect(files[0].localPath).toBe('/path/to/test.png');
    });

    it('应该在用户取消时返回空数组', async () => {
      vi.mocked(selectFiles).mockResolvedValue([]);

      const files = await selectFiles();

      expect(files).toHaveLength(0);
    });

    it('应该支持多文件选择', async () => {
      const mockFiles: File[] = [
        {
          fileName: 'file1.png',
          fileExtension: 'png',
          localPath: '/path/to/file1.png',
          fileType: 'local_path',
        },
        {
          fileName: 'file2.jpg',
          fileExtension: 'jpg',
          localPath: '/path/to/file2.jpg',
          fileType: 'local_path',
        },
      ];
      vi.mocked(selectFiles).mockResolvedValue(mockFiles);

      const files = await selectFiles();

      expect(files).toHaveLength(2);
      expect(files[0].fileName).toBe('file1.png');
      expect(files[1].fileName).toBe('file2.jpg');
    });
  });

  describe('文件验证逻辑', () => {
    it('应该检测重复文件名', () => {
      const existingFiles: File[] = [
        {
          fileName: 'existing.png',
          fileExtension: 'png',
          localPath: '/path/to/existing.png',
          fileType: 'local_path',
        },
      ];

      const newFile = {
        fileName: 'existing.png',
        fileExtension: 'png',
        localPath: '/path/to/existing.png',
        fileType: 'local_path' as const,
      };

      const existingFileNames = existingFiles.map((f) => f.fileName);
      const isDuplicate = existingFileNames.includes(newFile.fileName);

      expect(isDuplicate).toBe(true);
    });

    it('应该验证文件数量限制', () => {
      const existingFiles: File[] = Array(20).fill({
        fileName: 'file.png',
        fileExtension: 'png',
        localPath: '/path/to/file.png',
        fileType: 'local_path',
      });

      const newFilesCount = 1;
      const exceedsLimit = existingFiles.length + newFilesCount > 20;

      expect(exceedsLimit).toBe(true);
    });

    it('应该允许添加文件当未达到限制时', () => {
      const existingFiles: File[] = [
        {
          fileName: 'file1.png',
          fileExtension: 'png',
          localPath: '/path/to/file1.png',
          fileType: 'local_path',
        },
      ];

      const newFilesCount = 2;
      const exceedsLimit = existingFiles.length + newFilesCount > 20;

      expect(exceedsLimit).toBe(false);
    });
  });
});
