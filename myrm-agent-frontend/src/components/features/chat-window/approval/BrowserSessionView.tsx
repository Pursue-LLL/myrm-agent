'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: toolApproval 文案)
 * - @/lib/approval/browserSession::BrowserSessionAction (POS: 浏览器会话审批的动作)
 *
 * [OUTPUT]
 * - BrowserSessionView: 浏览器登录状态（保存 / 恢复 / 列出 / 删除）审批卡的上下文展示
 *
 * [POS]
 * 动作标题、说明与存放位置都来自 locales，随界面语言显示；不出现加密算法、存储路径等技术细节。
 */

import { Globe, Lock, ShieldAlert, Terminal } from 'lucide-react';
import { useTranslations } from 'next-intl';

import type { BrowserSessionAction } from '@/lib/approval/browserSession';

interface BrowserSessionViewProps {
  action: BrowserSessionAction;
  domain: string;
}

export default function BrowserSessionView({ action, domain }: BrowserSessionViewProps) {
  const t = useTranslations('toolApproval');

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Lock className="h-4 w-4 shrink-0 text-warning" />
        <span className="text-sm font-medium">{t('browserSession.title')}</span>
      </div>

      <div className="space-y-2 rounded-md bg-muted/50 p-3 text-xs">
        <div className="flex items-center gap-2">
          <Globe className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="shrink-0 font-medium">{t('browserSession.domain')}:</span>
          <span className="min-w-0 break-all font-mono text-foreground">
            {domain || t('browserSession.allDomains')}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Terminal className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="shrink-0 font-medium">{t('browserSession.action')}:</span>
          <span className="min-w-0 text-foreground">{t(`browserSession.actions.${action}.label`)}</span>
        </div>
      </div>

      <div className="rounded-md border border-primary/20 bg-primary/5 p-3 text-xs">
        <div className="flex items-start gap-2">
          <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
          <div className="min-w-0 space-y-1">
            <p className="text-foreground">{t(`browserSession.actions.${action}.desc`)}</p>
            <p className="text-[11px] text-muted-foreground">{t('browserSession.storageInfo')}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
