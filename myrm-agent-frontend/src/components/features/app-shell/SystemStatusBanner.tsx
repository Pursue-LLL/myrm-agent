'use client';

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { AlertTriangle, Database, X } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { apiRequest } from '@/lib/api';

export default function SystemStatusBanner() {
  const [degraded, setDegraded] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [isResetting, setIsResetting] = useState(false);

  useEffect(() => {
    const checkStatus = async () => {
      try {
        const data = await apiRequest<{ system_status?: any }>('/health');
        const status = data.system_status;
        if (status) {
          if (status.database_recovered) {
            toast.success('数据库已自动修复', {
              description: '检测到本地数据库异常，已自动为您恢复数据。',
              icon: <Database className="w-4 h-4" />,
              duration: 5000,
            });
          }
          if (status.database_degraded) {
            setDegraded(true);
          }
        }
      } catch (e) {
        console.error('Failed to check system status', e);
      }
    };
    checkStatus();
  }, []);

  const handleReset = async () => {
    if (!confirm('确定要重置数据库吗？这将清空所有本地数据并重新初始化系统。')) {
      return;
    }

    setIsResetting(true);
    try {
      await apiRequest('/health/database/reset', {
        method: 'POST',
      });

      toast.success('数据库重置成功', {
        description: '系统已恢复正常，即将刷新页面。',
      });
      setTimeout(() => {
        window.location.reload();
      }, 1500);
    } catch (e: any) {
      console.error(e);
      toast.error('重置失败', {
        description: e.message || '网络请求异常',
      });
      setIsResetting(false);
    }
  };

  if (!degraded || dismissed) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-destructive text-destructive-foreground px-4 py-3 pt-[max(0.75rem,env(safe-area-inset-top))] shadow-md flex items-center justify-between animate-in slide-in-from-top">
      <div className="flex items-center gap-3">
        <AlertTriangle className="w-5 h-5 flex-shrink-0" />
        <div className="text-sm">
          <span className="font-bold mr-2">本地数据库严重损坏且无法恢复。</span>
          当前运行在临时安全模式，您的新对话将不会被保存。
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Button variant="secondary" size="sm" className="h-8 text-xs" onClick={handleReset} disabled={isResetting}>
          {isResetting ? '重置中...' : '立即重置数据库'}
        </Button>
        <button
          onClick={() => setDismissed(true)}
          className="p-1 hover:bg-black/10 rounded-full transition-colors"
          aria-label="Dismiss"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
