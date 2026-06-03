/**
 * UI 图片组件
 * 支持图片展示、懒加载、错误处理
 */

'use client';

import React, { useState } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { ImageIcon, AlertCircle } from 'lucide-react';
import { UIComponentProps } from '../UIComponentRegistry';
import { getValueByPath } from '../utils';

export const UIImage: React.FC<UIComponentProps> = ({ props, bindings, data }) => {
  const t = useTranslations('interactiveUI.image');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // 从 props 或数据绑定获取图片 URL
  const srcPath = bindings.src || bindings.value;
  const src = srcPath ? (getValueByPath(data, srcPath) as string) : (props.src as string);

  const alt = (props.alt as string) || t('alt');
  const width = props.width as number | string | undefined;
  const height = props.height as number | string | undefined;
  const objectFit = (props.objectFit as 'cover' | 'contain' | 'fill' | 'none') || 'cover';
  const rounded = (props.rounded as boolean) !== false;
  const className = (props.className as string) || '';
  const caption = props.caption as string | undefined;

  const handleLoad = () => {
    setLoading(false);
    setError(false);
  };

  const handleError = () => {
    setLoading(false);
    setError(true);
  };

  if (!src) {
    return (
      <div
        className={cn(
          'flex flex-col items-center justify-center gap-2 p-8',
          'bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-500',
          rounded && 'rounded-lg',
          className,
        )}
        style={{ width, height: height || 120 }}
      >
        <ImageIcon className="w-8 h-8" />
        <span className="text-xs">{t('loading')}</span>
      </div>
    );
  }

  return (
    <figure className={cn('overflow-hidden', className)}>
      <div
        className={cn('relative overflow-hidden bg-gray-100 dark:bg-gray-800', rounded && 'rounded-lg')}
        style={{ width, height }}
      >
        {/* 加载占位 */}
        {loading && !error && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-100 dark:bg-gray-800 animate-pulse">
            <ImageIcon className="w-8 h-8 text-gray-400 dark:text-gray-500" />
          </div>
        )}

        {/* 错误状态 */}
        {error && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-500">
            <AlertCircle className="w-8 h-8" />
            <span className="text-xs">{t('loadError')}</span>
          </div>
        )}

        {/* 图片 */}
        {!error && (
          <img
            src={src}
            alt={alt}
            onLoad={handleLoad}
            onError={handleError}
            className={cn('w-full h-full transition-opacity duration-300', loading ? 'opacity-0' : 'opacity-100', {
              'object-cover': objectFit === 'cover',
              'object-contain': objectFit === 'contain',
              'object-fill': objectFit === 'fill',
              'object-none': objectFit === 'none',
            })}
          />
        )}
      </div>

      {/* 图片说明 */}
      {caption && (
        <figcaption className="mt-2 text-xs text-center text-gray-500 dark:text-gray-400">{caption}</figcaption>
      )}
    </figure>
  );
};
