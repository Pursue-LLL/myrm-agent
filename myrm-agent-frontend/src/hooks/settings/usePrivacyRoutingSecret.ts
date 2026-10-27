'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { getConfigSyncManager } from '@/services/config';
import { loadPrivacyRoutingSecret, writePrivacyRoutingSecret } from '@/store/config/privacyRoutingSecret';

/**
 * 本地模型端点的密钥：读自独立的加密配置行，与路由偏好分开存取。
 * 首次读取要等该行同步完成；用户在此之前已经输入的内容不会被加载结果覆盖。
 */
export function usePrivacyRoutingSecret(): readonly [string, (localApiKey: string) => void] {
  const [localApiKey, setLocalApiKey] = useState('');
  const edited = useRef(false);

  useEffect(() => {
    let active = true;
    void loadPrivacyRoutingSecret().then((loaded) => {
      if (active && !edited.current) {
        setLocalApiKey(loaded);
      }
    });
    const unsubscribe = getConfigSyncManager().subscribe('privacyRoutingSecret', (_key, value) => {
      if (active) {
        setLocalApiKey(value?.localApiKey ?? '');
      }
    });
    return () => {
      active = false;
      unsubscribe();
    };
  }, []);

  const update = useCallback((next: string) => {
    edited.current = true;
    setLocalApiKey(next);
    writePrivacyRoutingSecret(next);
  }, []);

  return [localApiKey, update] as const;
}
