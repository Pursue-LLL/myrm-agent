'use client';

import { useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { setGlobalTranslator } from '@/services/i18nToastService';

/**
 * Toast 服务初始化器
 * 在应用启动时初始化全局翻译服务，用于 store 中的 i18n toast
 */
const ToastServiceInitializer = () => {
  const t = useTranslations();

  useEffect(() => {
    // 初始化全局翻译服务
    setGlobalTranslator(t);
  }, [t]);

  return null; // 这个组件不需要渲染任何内容
};

export default ToastServiceInitializer;
