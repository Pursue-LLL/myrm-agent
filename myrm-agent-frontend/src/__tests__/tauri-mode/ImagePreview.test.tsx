/**
 * ImagePreview 组件测试
 *
 * 测试图片预览组件在 Tauri 和 Sandbox 模式下的行为
 */

// Mock 声明必须在所有导入之前（Vitest hoisting）
import { vi } from 'vitest';

vi.mock('@/services/file-service', () => ({
  readFileAsDataURL: vi.fn(),
  fromStoreFile: (file: unknown) => file, // 直接返回原对象
}));

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ImagePreview } from '@/components/features/file-preview/ImagePreview';
import type { File } from '@/store/useChatStore';
import { readFileAsDataURL } from '@/services/file-service';

describe('ImagePreview', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('本地文件预览 (local_path)', () => {
    it('应该成功显示本地图片', async () => {
      const mockDataUrl = 'data:image/png;base64,iVBORw0KGgo=';
      (readFileAsDataURL as any).mockResolvedValue(mockDataUrl);

      const file: File = {
        fileName: 'test.png',
        fileExtension: 'png',
        localPath: '/path/to/test.png',
        fileType: 'local_path',
      };

      render(<ImagePreview file={file} />);

      // 等待图片加载
      await waitFor(() => {
        const img = screen.getByAltText('test.png') as HTMLImageElement;
        expect(img.src).toBe(mockDataUrl);
      });

      expect(readFileAsDataURL).toHaveBeenCalledWith(file);
    });

    it('应该在加载失败时显示错误提示', async () => {
      (readFileAsDataURL as any).mockRejectedValue(new Error('File not found'));

      const file: File = {
        fileName: 'missing.png',
        fileExtension: 'png',
        localPath: '/path/to/missing.png',
        fileType: 'local_path',
      };

      render(<ImagePreview file={file} />);

      await waitFor(() => {
        expect(screen.getByText('图片加载失败')).toBeInTheDocument();
      });
    });
  });

  describe('上传文件预览 (uploaded)', () => {
    it('应该直接使用服务器 URL 显示图片', async () => {
      const file: File = {
        fileName: 'uploaded.png',
        fileExtension: 'png',
        fileUrl: 'https://example.com/files/uploaded.png',
        fileType: 'uploaded',
      };

      render(<ImagePreview file={file} />);

      // 不应该调用 readFileAsDataURL
      expect(readFileAsDataURL).not.toHaveBeenCalled();

      // 应该直接显示图片
      await waitFor(() => {
        const img = screen.getByAltText('uploaded.png') as HTMLImageElement;
        expect(img.src).toBe('https://example.com/files/uploaded.png');
      });
    });
  });

  describe('非图片文件', () => {
    it('应该不渲染非图片文件', () => {
      const file: File = {
        fileName: 'document.pdf',
        fileExtension: 'pdf',
        localPath: '/path/to/document.pdf',
        fileType: 'local_path',
      };

      const { container } = render(<ImagePreview file={file} />);

      expect(container.firstChild).toBeNull();
    });

    it('应该支持所有图片格式', async () => {
      const formats = ['png', 'jpg', 'jpeg', 'gif', 'webp'];

      for (const ext of formats) {
        const mockDataUrl = `data:image/${ext};base64,abc`;
        (readFileAsDataURL as any).mockResolvedValue(mockDataUrl);

        const file: File = {
          fileName: `test.${ext}`,
          fileExtension: ext,
          localPath: `/path/to/test.${ext}`,
          fileType: 'local_path',
        };

        const { unmount } = render(<ImagePreview file={file} />);

        await waitFor(() => {
          expect(screen.getByAltText(`test.${ext}`)).toBeInTheDocument();
        });

        unmount();
      }
    });
  });

  describe('加载状态', () => {
    it('应该在加载时显示加载动画', async () => {
      (readFileAsDataURL as any).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve('data:image/png;base64,abc'), 100)),
      );

      const file: File = {
        fileName: 'slow.png',
        fileExtension: 'png',
        localPath: '/path/to/slow.png',
        fileType: 'local_path',
      };

      render(<ImagePreview file={file} />);

      // 加载动画应该显示（查找 loader SVG）
      const loader = document.querySelector('.lucide-loader-circle');
      expect(loader).toBeInTheDocument();

      // 等待加载完成
      await waitFor(() => {
        expect(screen.getByAltText('slow.png')).toBeInTheDocument();
      });
    });
  });

  describe('自定义样式', () => {
    it('应该应用自定义 className', async () => {
      const mockDataUrl = 'data:image/png;base64,abc';
      (readFileAsDataURL as any).mockResolvedValue(mockDataUrl);

      const file: File = {
        fileName: 'styled.png',
        fileExtension: 'png',
        localPath: '/path/to/styled.png',
        fileType: 'local_path',
      };

      const { container } = render(<ImagePreview file={file} className="custom-class" />);

      await waitFor(() => {
        const img = screen.getByAltText('styled.png');
        expect(img).toBeInTheDocument();
        // className 在父元素或图片本身
        expect(container.innerHTML).toContain('custom-class');
      });
    });
  });

  describe('懒加载', () => {
    it('应该设置 loading="lazy" 属性', async () => {
      const mockDataUrl = 'data:image/png;base64,abc';
      (readFileAsDataURL as any).mockResolvedValue(mockDataUrl);

      const file: File = {
        fileName: 'lazy.png',
        fileExtension: 'png',
        localPath: '/path/to/lazy.png',
        fileType: 'local_path',
      };

      render(<ImagePreview file={file} />);

      await waitFor(() => {
        const img = screen.getByAltText('lazy.png') as HTMLImageElement;
        expect(img.getAttribute('loading')).toBe('lazy');
      });
    });
  });
});
