'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconLoader,
  IconPlus,
  IconCheck,
  IconX,
} from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { toast } from 'sonner';
import { getWeChatStatus, logoutWeChatChannel } from '@/services/channels';
import type { WeChatStatus } from '@/services/channels';
import { useChannelInstances } from '@/hooks/channels/useChannelInstances';
import { WeChatRiskDisclosureBanner } from './WeChatRiskDisclosureBanner';
import { WeChatAccountCard } from './WeChatAccountCard';

export interface WeChatConfigCardProps {
  onNavigateToWeCom?: () => void;
}

export function WeChatConfigCard({ onNavigateToWeCom }: WeChatConfigCardProps = {}) {
  const t = useTranslations('channels');
  const [primaryStatus, setPrimaryStatus] = useState<WeChatStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [showLabelInput, setShowLabelInput] = useState(false);
  const [newLabel, setNewLabel] = useState('');
  const labelInputRef = useRef<HTMLInputElement>(null);

  const { instances, extraInstances, adding, addInstance, removeInstance, renameInstance } = useChannelInstances({
    channelType: 'wechat',
    primaryName: 'wechat',
    i18nPrefix: 'wechat',
  });

  const primaryLabel = instances.find((i) => i.channelName === 'wechat')?.displayName ?? '';

  const fetchPrimaryStatus = useCallback((showLoading = false) => {
    if (showLoading) {
      setLoading(true);
    }
    return getWeChatStatus()
      .then(setPrimaryStatus)
      .catch(() => {
        // 轮询/刷新失败时保留上次状态：置 null 会卸载整个卡片区，正在进行的
        // 删除/重命名等异步操作在卸载组件上的 state 更新会被 React 丢弃。
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    void fetchPrimaryStatus(true);
  }, [fetchPrimaryStatus]);

  useEffect(() => {
    const needsPolling = primaryStatus !== null && (!primaryStatus.connected || primaryStatus.qr_code);
    if (!needsPolling) {
      return;
    }
    const timer = setInterval(() => void fetchPrimaryStatus(), 3_000);
    return () => clearInterval(timer);
  }, [primaryStatus, fetchPrimaryStatus]);

  const handlePrimaryRename = useCallback(
    (newName: string) => {
      void renameInstance('wechat', newName);
    },
    [renameInstance],
  );

  const handleAddInstance = useCallback(() => {
    void addInstance(newLabel.trim() || undefined).then((ok) => {
      if (ok) {
        setShowLabelInput(false);
        setNewLabel('');
      }
    });
  }, [addInstance, newLabel]);

  const handlePrimaryLogout = useCallback(async () => {
    try {
      await logoutWeChatChannel('wechat');
      setPrimaryStatus((prev) =>
        prev ? { ...prev, connected: false, qr_code: null, bot_id: null, status: 'stopped' } : prev,
      );
      toast.success(t('wechatInstanceRemoved'));
    } catch (error) {
      toast.error(t('wechatInstanceRemoveError'));
      // 向上抛出让 ConfirmDialog 捕获，保持对话框打开以便用户重试
      throw error;
    }
  }, [t]);

  const handleNavigateToWeCom = useCallback(() => {
    if (onNavigateToWeCom) {
      onNavigateToWeCom();
      return;
    }
    if (typeof document !== 'undefined') {
      const wecomBtn = document.querySelector<HTMLButtonElement>('[data-testid="channel-list-item-wecom"]');
      if (wecomBtn) {
        wecomBtn.click();
        return;
      }
    }
    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem('myrm-selected-channel', 'wecom');
      } catch {
        // quota exceeded
      }
    }
  }, [onNavigateToWeCom]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
        <IconLoader className="h-4 w-4 animate-spin" />
        <span>{t('wechatLoading')}</span>
      </div>
    );
  }

  if (!primaryStatus) {
    return <p className="text-sm text-muted-foreground py-4 text-center">{t('wechatNoChannel')}</p>;
  }

  return (
    <div className="space-y-3">
      <WeChatRiskDisclosureBanner onNavigateToWeCom={handleNavigateToWeCom} />

      <WeChatAccountCard
        label={primaryLabel || t('wechatDefaultLabel')}
        channelName="wechat"
        status={primaryStatus}
        onStatusChange={setPrimaryStatus}
        onDelete={handlePrimaryLogout}
        onLabelChange={handlePrimaryRename}
        onRefresh={() => fetchPrimaryStatus()}
        t={t}
      />

      {extraInstances.map((inst) => (
        <WeChatAccountCard
          key={inst.instanceId}
          label={inst.displayName || inst.channelName}
          channelName={inst.channelName}
          onDelete={() => removeInstance(inst.instanceId)}
          onLabelChange={(v) => void renameInstance(inst.channelName, v)}
          t={t}
        />
      ))}

      <div className="pt-1 space-y-2">
        {showLabelInput ? (
          <div className="flex items-center gap-2">
            <input
              ref={labelInputRef}
              type="text"
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  handleAddInstance();
                }
                if (e.key === 'Escape') {
                  setShowLabelInput(false);
                  setNewLabel('');
                }
              }}
              placeholder={t('wechatInstanceLabelPlaceholder')}
              className="flex-1 h-8 rounded-full border bg-background px-3 text-xs focus:outline-none focus:ring-1 focus:ring-ring"
              maxLength={50}
            />
            <Button
              variant="default"
              size="icon"
              className="h-8 w-8 shrink-0"
              onClick={handleAddInstance}
              disabled={adding}
            >
              {adding ? <IconLoader className="h-3.5 w-3.5 animate-spin" /> : <IconCheck className="h-3.5 w-3.5" />}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0"
              onClick={() => {
                setShowLabelInput(false);
                setNewLabel('');
              }}
            >
              <IconX className="h-3.5 w-3.5" />
            </Button>
          </div>
        ) : (
          <Button
            variant="outline"
            size="sm"
            className="w-full text-xs gap-1.5"
            onClick={() => {
              setShowLabelInput(true);
              setTimeout(() => labelInputRef.current?.focus(), 50);
            }}
          >
            <IconPlus className="h-3.5 w-3.5" />
            {t('wechatAddAccount')}
          </Button>
        )}
      </div>
    </div>
  );
}
