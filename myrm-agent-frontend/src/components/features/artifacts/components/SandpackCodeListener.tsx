/**
 * [INPUT]
 * - @codesandbox/sandpack-react::useActiveCode (POS: Sandpack 代码读取上下文)
 * - useArtifactPortalStore (POS: artifact 门户状态管理器)
 *
 * [OUTPUT]
 * - SandpackCodeListener: 监听 Sandpack 代码变更并同步 artifact 脏状态。
 *
 * [POS]
 * Sandpack artifact 变更桥接层。负责把编辑后的代码延迟同步到 artifact 门户状态，避免频繁写入。
 */
import React, { useEffect, useRef, useState } from 'react';
import { useActiveCode } from '@codesandbox/sandpack-react';
import useArtifactPortalStore from '@/store/useArtifactPortalStore';

interface SandpackCodeListenerProps {
  artifactId: string;
  originalCode: string;
}

export const SandpackCodeListener: React.FC<SandpackCodeListenerProps> = ({ artifactId, originalCode }) => {
  const { code } = useActiveCode();
  const markAsDirty = useArtifactPortalStore((state) => state.markAsDirty);
  const clearDirtyState = useArtifactPortalStore((state) => state.clearDirtyState);

  const [debouncedCode, setDebouncedCode] = useState(code);
  const isInitialMount = useRef(true);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedCode(code);
    }, 2000);

    return () => window.clearTimeout(timer);
  }, [code]);

  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }

    // 只有当代码真正发生改变，且不是初始代码时，才标记为脏状态
    // 注意：这里的 code 是被 wrapCodeAsApp 包装过的，所以不能直接和 originalCode 比较
    // 更好的做法是依赖 Sandpack 的内部状态，但这里为了简单，只要有修改就标记
    if (debouncedCode) {
      // 提取真实代码（去除包装）
      let realCode = debouncedCode;
      const match = debouncedCode.match(/\/\/ --- BEGIN ORIGINAL CODE ---\n([\s\S]*?)\n\/\/ --- END ORIGINAL CODE ---/);
      if (match && match[1]) {
        realCode = match[1];
      }

      if (realCode.trim() !== originalCode.trim()) {
        markAsDirty(artifactId, realCode);
      } else {
        clearDirtyState(artifactId);
      }
    }
  }, [debouncedCode, artifactId, originalCode, markAsDirty, clearDirtyState]);

  return null; // 这是一个纯逻辑组件，不渲染任何 UI
};
