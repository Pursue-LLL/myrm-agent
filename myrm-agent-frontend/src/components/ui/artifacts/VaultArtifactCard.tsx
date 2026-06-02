import React, { useEffect, useState } from 'react';
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

export const getVaultMeta = async (objId: string): Promise<VaultObjectMeta> => {
  return apiRequest<VaultObjectMeta>(`/vault/${objId}/meta`, {
    method: 'GET',
  });
};

const formatBytes = (bytes: number) => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

const getFileIcon = (contentType: string) => {
  if (contentType.includes('json')) return <FileJson className="w-6 h-6 text-yellow-500" />;
  if (contentType.includes('csv')) return <Database className="w-6 h-6 text-green-500" />;
  if (contentType.includes('markdown') || contentType.includes('text'))
    return <FileText className="w-6 h-6 text-blue-500" />;
  if (contentType.includes('javascript') || contentType.includes('python'))
    return <FileCode className="w-6 h-6 text-purple-500" />;
  return <File className="w-6 h-6 text-gray-500" />;
};

export default function VaultArtifactCard({ id }: { id: string }) {
  const [meta, setMeta] = useState<VaultObjectMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;
    const fetchMeta = async () => {
      try {
        const data = await getVaultMeta(id);
        if (mounted) setMeta(data);
      } catch (err: any) {
        if (mounted) setError(err.message || '加载 Artifact 失败');
      } finally {
        if (mounted) setLoading(false);
      }
    };
    fetchMeta();
    return () => {
      mounted = false;
    };
  }, [id]);

  const handleDownload = () => {
    // Navigate to the direct download URL or open in new tab
    const url = getApiUrl(`/vault/${id}/content`);
    const link = document.createElement('a');
    link.href = url;
    // For proper auth with downloading, token logic might be needed if API is protected,
    // but usually GET requests for static resources are either cookie-based or use a short-lived token in query param.
    // For this prototype, we'll assume it's directly accessible or uses cookies.
    link.setAttribute('download', meta?.filename || `artifact-${id}`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (loading) {
    return (
      <div className="flex items-center gap-3 p-4 my-2 border rounded-xl bg-gray-50/50 dark:bg-gray-800/50 dark:border-gray-700 max-w-sm">
        <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
        <span className="text-sm text-gray-500 dark:text-gray-400">正在检索沙箱大文件...</span>
      </div>
    );
  }

  if (error || !meta) {
    return (
      <div className="p-4 my-2 border border-red-200 bg-red-50 rounded-xl dark:bg-red-900/20 dark:border-red-800 max-w-sm">
        <span className="text-sm text-red-600 dark:text-red-400">
          无法加载金库文件 (vault://{id.substring(0, 8)}...): {error}
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

      <div className="mt-3 pt-3 border-t dark:border-gray-800 flex items-center justify-between">
        <div className="text-[10px] text-gray-400 font-mono tracking-tight">vault://{id.substring(0, 13)}</div>
        <button
          onClick={handleDownload}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-primary hover:text-primary/80 hover:bg-primary/5 rounded-full transition-colors"
        >
          <Download className="w-3.5 h-3.5" />
          下载完整文件
        </button>
      </div>
    </div>
  );
}
