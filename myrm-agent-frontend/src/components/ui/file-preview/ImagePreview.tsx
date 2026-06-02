/**
 * 图片预览组件
 *
 * 仅支持图片文件的预览（png, jpg, jpeg, gif, webp）
 * 自动适配 Tauri 和 Sandbox 模式
 */

import { useState, useEffect } from 'react';
import { File } from '@/store/chat/types';
import { readFileAsDataURL, fromStoreFile } from '@/services/file-service';
import { Loader2 } from 'lucide-react';

export interface ImagePreviewProps {
  file: File;
  className?: string;
}

const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'gif', 'webp'];

/**
 * 检查文件是否为图片
 */
function isImageFile(file: File): boolean {
  return IMAGE_EXTENSIONS.includes(file.fileExtension.toLowerCase());
}

export function ImagePreview({ file, className = '' }: ImagePreviewProps) {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    // 仅预览图片文件
    if (!isImageFile(file)) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(false);

    // 根据文件类型获取图片 URL
    if (file.fileType === 'uploaded' && file.fileUrl) {
      // Sandbox 模式：直接使用服务器 URL
      setImageUrl(file.fileUrl);
      setLoading(false);
    } else if (file.fileType === 'local_path') {
      // Tauri 模式：读取本地文件并转换为 Data URL
      // 使用新的 file-service 统一接口
      readFileAsDataURL(fromStoreFile(file))
        .then((dataUrl) => {
          setImageUrl(dataUrl);
          setLoading(false);
        })
        .catch((err) => {
          console.error('Failed to read image file:', err);
          setError(true);
          setLoading(false);
        });
    } else {
      setLoading(false);
    }
  }, [file]);

  // 非图片文件：不渲染
  if (!isImageFile(file)) {
    return null;
  }

  // 加载中
  if (loading) {
    return (
      <div className={`flex items-center justify-center p-4 ${className}`}>
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // 加载失败
  if (error || !imageUrl) {
    return (
      <div className={`flex items-center justify-center p-4 text-muted-foreground ${className}`}>
        <span className="text-sm">图片加载失败</span>
      </div>
    );
  }

  // 图片预览
  return (
    <img
      src={imageUrl}
      alt={file.fileName}
      className={`max-w-full max-h-48 object-contain rounded-lg ${className}`}
      loading="lazy"
    />
  );
}

export default ImagePreview;
