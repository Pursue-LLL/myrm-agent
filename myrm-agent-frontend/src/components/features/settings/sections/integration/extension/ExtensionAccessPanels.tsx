'use client';

/**
 * [INPUT] @/services/extension::ExtensionStatus, ExtensionTab (POS: 扩展状态 DTO)
 * [OUTPUT] ExtensionDomainsPanel: 授权域名与全部放行开关; ExtensionTabsPanel: 可用标签页及暂停 / 恢复，未连接或无标签页时不渲染
 * [POS] ExtensionBridgeSection 的访问控制区块，纯展示，编辑动作由 useExtensionBridge 提供。
 */

import { memo, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { Globe, Trash2, ExternalLink } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Input } from '@/components/primitives/input';
import { Switch } from '@/components/primitives/switch';
import { cn } from '@/lib/utils';
import { type ExtensionStatus, type ExtensionTab } from '@/services/extension';

interface ExtensionDomainsPanelProps {
  status: ExtensionStatus;
  saving: boolean;
  domainInput: string;
  onDomainInputChange: (value: string) => void;
  onAddDomain: () => void;
  onRemoveDomain: (domain: string) => void;
  onAllowAllChange: (checked: boolean) => void;
}

export const ExtensionDomainsPanel = memo(
  ({
    status,
    saving,
    domainInput,
    onDomainInputChange,
    onAddDomain,
    onRemoveDomain,
    onAllowAllChange,
  }: ExtensionDomainsPanelProps) => {
    const t = useTranslations('settings');

    return (
      <div className="space-y-3">
        <h4 className="text-sm font-medium flex items-center gap-2">
          <Globe className="h-4 w-4" />
          {t('extension.authorizedDomains')}
        </h4>
        <p className="text-xs text-muted-foreground">{t('extension.domainsHint')}</p>

        <div className="flex items-center justify-between gap-3 rounded-lg border border-border/50 bg-background/50 p-3">
          <div className="space-y-0.5">
            <p className="text-sm font-medium">{t('extension.allowAllEligibleTabs')}</p>
            <p className="text-xs text-muted-foreground">{t('extension.allowAllEligibleTabsHint')}</p>
          </div>
          <Switch
            checked={status.allow_all_eligible_tabs}
            onCheckedChange={(checked) => void onAllowAllChange(checked)}
            disabled={saving}
          />
        </div>

        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            value={domainInput}
            onChange={(e) => onDomainInputChange(e.target.value)}
            placeholder={t('extension.domainPlaceholder')}
            className="flex-1 min-w-0"
            onKeyDown={(e) => e.key === 'Enter' && onAddDomain()}
          />
          <Button size="sm" onClick={onAddDomain} disabled={saving || !domainInput.trim()}>
            {t('extension.addDomain')}
          </Button>
        </div>

        {status.authorized_domains.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2">
            {status.authorized_domains.map((domain) => (
              <Badge key={domain} variant="secondary" className="flex items-center gap-1 px-2 py-1">
                <Globe className="h-3 w-3" />
                {domain}
                <button
                  type="button"
                  onClick={() => onRemoveDomain(domain)}
                  className="ml-1 hover:text-destructive-text transition-colors"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </Badge>
            ))}
          </div>
        )}
      </div>
    );
  },
);
ExtensionDomainsPanel.displayName = 'ExtensionDomainsPanel';

interface ExtensionTabsPanelProps {
  status: ExtensionStatus;
  saving: boolean;
  onToggleTabPause: (tabId: number) => void;
}

export const ExtensionTabsPanel = memo(({ status, saving, onToggleTabPause }: ExtensionTabsPanelProps) => {
  const t = useTranslations('settings');
  const pausedTabIdSet = useMemo(() => new Set(status.paused_tab_ids), [status.paused_tab_ids]);

  if (!(status.connected && status.available_tabs.length > 0)) {
    return null;
  }

  return (
    <div className="space-y-2">
      <h4 className="text-sm font-medium flex items-center gap-2">
        <ExternalLink className="h-4 w-4" />
        {t('extension.availableTabs')}
      </h4>
      {status.allow_all_eligible_tabs && <p className="text-xs text-muted-foreground">{t('extension.tabPauseHint')}</p>}
      <div className="space-y-1 max-h-48 overflow-y-auto">
        {status.available_tabs.map((tab: ExtensionTab) => {
          const isPaused = pausedTabIdSet.has(tab.tab_id);
          return (
            <div
              key={tab.tab_id}
              className={cn(
                'flex flex-col gap-2 sm:flex-row sm:items-center text-xs p-2 rounded border border-border/40',
                isPaused ? 'bg-muted/50 opacity-80' : 'bg-muted/30',
              )}
            >
              <div className="flex items-center gap-2 min-w-0 flex-1">
                <span className="text-primary font-mono shrink-0">{tab.domain}</span>
                <span className="text-muted-foreground truncate flex-1">{tab.title}</span>
                {tab.active && (
                  <Badge variant="outline" className="text-[10px] shrink-0">
                    {t('extension.tabActive')}
                  </Badge>
                )}
                {isPaused && (
                  <Badge variant="secondary" className="text-[10px] shrink-0">
                    {t('extension.tabPaused')}
                  </Badge>
                )}
              </div>
              <Button
                variant={isPaused ? 'secondary' : 'outline'}
                size="sm"
                className="shrink-0 h-7 text-xs"
                disabled={saving}
                onClick={() => void onToggleTabPause(tab.tab_id)}
              >
                {isPaused ? t('extension.tabResume') : t('extension.tabPause')}
              </Button>
            </div>
          );
        })}
      </div>
    </div>
  );
});
ExtensionTabsPanel.displayName = 'ExtensionTabsPanel';
