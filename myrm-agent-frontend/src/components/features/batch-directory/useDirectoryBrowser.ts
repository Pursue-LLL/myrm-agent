/**
 * [INPUT] @/services/chat::browseDirectories (POS: 目录浏览 API), @/hooks/shared/useToast (POS: 浏览失败提示)
 * [OUTPUT] useDirectoryBrowser: 当前目录、条目列表、浏览中状态、已选目录集合，以及浏览 / 上一级 / 勾选 / 重置动作
 * [POS] 创建向导的目录选择状态层；已选目录在浏览间保留，创建成功后与条目列表一并清空。
 */

import { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/hooks/shared/useToast';
import { browseDirectories, type DirectoryEntry } from '@/services/chat';

export function useDirectoryBrowser() {
  const t = useTranslations('batchDirectory');
  const [currentDir, setCurrentDir] = useState('~');
  const [entries, setEntries] = useState<DirectoryEntry[]>([]);
  const [browsing, setBrowsing] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);

  const browse = useCallback(
    async (path: string) => {
      setBrowsing(true);
      try {
        const res = await browseDirectories(path);
        setCurrentDir(res.current);
        setEntries(res.entries);
      } catch {
        toast.error(t('browseError'));
      } finally {
        setBrowsing(false);
      }
    },
    [t],
  );

  const goUp = useCallback(() => {
    const parts = currentDir.split('/').filter(Boolean);
    parts.pop();
    void browse(parts.length ? `/${parts.join('/')}` : '~');
  }, [currentDir, browse]);

  const toggle = useCallback((path: string) => {
    setSelected((prev) => (prev.includes(path) ? prev.filter((p) => p !== path) : [...prev, path]));
  }, []);

  const reset = useCallback(() => {
    setSelected([]);
    setEntries([]);
  }, []);

  return { currentDir, entries, browsing, selected, browse, goUp, toggle, reset };
}

export type DirectoryBrowser = ReturnType<typeof useDirectoryBrowser>;
