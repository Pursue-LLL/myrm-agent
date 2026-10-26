import React, { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { apiRequest, getApiUrl } from '@/lib/api';
import { Download, FileText, Loader2, FileJson, FileCode, File, Database } from 'lucide-react';

export interface VaultObjectMeta {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at: number;
  description?: string;
}

/** Query suffix naming the chat whose workspace holds the object (objects no artifact points at have no other owner). */
const chatQuery = (chatId?: string): string => (chatId ? `chat_id=${encodeURIComponent(chatId)}` : '');

export const getVaultMeta = async (objId: string, chatId?: string): Promise<VaultObjectMeta> => {
  const query = chatQuery(chatId);
  return apiRequest<VaultObjectMeta>(`/files/vault/${objId}/meta${query ? `?${query}` : ''}`, {
    method: 'GET',
  });
};

export const getVaultDownloadUrl = (objId: string, chatId?: string): string => {
  const query = ['download=1', chatQuery(chatId)].filter(Boolean).join('&');
  return getApiUrl(`/files/vault/${objId}/content?${query}`);
};

const formatBytes = (bytes: number) => {
  if (bytes === 0) {
    return '0 B';
  }
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

const getFileIcon = (contentType: string) => {
  if (contentType.includes('json')) {
    return <FileJson className="w-6 h-6 text-yellow-500" />;
  }
  if (contentType.includes('csv')) {
    return <Database className="w-6 h-6 text-green-500" />;
  }
  if (contentType.includes('markdown') || contentType.includes('text')) {
    return <FileText className="w-6 h-6 text-blue-500" />;
  }
  if (contentType.includes('javascript') || contentType.includes('python')) {
    return <FileCode className="w-6 h-6 text-purple-500" />;
  }
  return <File className="w-6 h-6 text-gray-500" />;
};

export default function VaultArtifactCard({ id, chatId }: { id: string; chatId?: string }) {
  const t = useTranslations('artifacts.vaultCard');
  const [meta, setMeta] = useState<VaultObjectMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;
    const fetchMeta = async () => {
      try {
        const data = await getVaultMeta(id, chatId);
        if (mounted) {
          setMeta(data);
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : t('loadFailed'));
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };
    fetchMeta();
    return () => {
      mounted = false;
    };
  }, [id, chatId, t]);

  const handleDownload = () => {
    const link = document.createElement('a');
    link.href = getVaultDownloadUrl(id, chatId);
    link.setAttribute('download', meta?.filename || `artifact-${id}`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (loading) {
    return (
      <div className="flex items-center gap-3 p-4 my-2 border rounded-xl bg-gray-50/50 dark:bg-gray-800/50 dark:border-gray-700 max-w-sm">
        <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
        <span className="text-sm text-gray-500 dark:text-gray-400">{t('loading')}</span>
      </div>
    );
  }

  if (error || !meta) {
    return (
      <div className="p-4 my-2 border border-red-200 bg-red-50 rounded-xl dark:bg-red-900/20 dark:border-red-800 max-w-sm">
        <span className="text-sm text-red-600 dark:text-red-400">
          {t('unavailable')}: {error}
        </span>
      </div>
    );
  }

  return (
    <div className="group relative flex flex-col p-4 my-3 border rounded-xl bg-white dark:bg-gray-900 dark:border-gray-700 transition-shadow hover:shadow-md max-w-md w-full">
      <div className="flex items-start gap-4">
        <div className="p-2.5 bg-gray-100 dark:bg-gray-800 rounded-lg">{getFileIcon(meta.content_type)}</div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <h4 className="font-medium text-sm text-gray-900 dark:text-gray-100 truncate" title={meta.filename}>
              {meta.filename}
            </h4>
          </div>

          <div className="flex items-center gap-2 mt-1.5 text-xs text-gray-500 dark:text-gray-400">
            <span className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 font-mono">
              {meta.content_type.split(';')[0]}
            </span>
            <span>•</span>
            <span>{formatBytes(meta.size_bytes)}</span>
          </div>

          {meta.description && (
            <p className="mt-2 text-xs text-gray-600 dark:text-gray-300 line-clamp-2 leading-relaxed">
              {meta.description}
            </p>
          )}
        </div>
      </div>

      <div className="mt-3 pt-3 border-t dark:border-gray-800 flex items-center justify-end">
        <button
          onClick={handleDownload}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-primary hover:text-primary/80 hover:bg-primary/5 rounded-full transition-colors"
        >
          <Download className="w-3.5 h-3.5" />
          {t('downloadFull')}
        </button>
      </div>
    </div>
  );
}
