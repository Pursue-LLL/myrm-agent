'use client';

/**
 * [INPUT] @/services/channels::ChannelIssue, installChannelDependencies (POS: 渠道问题与依赖安装接口), ./issueMessages (POS: 问题与修复提示的文案匹配)
 * [OUTPUT] ChannelIssueBanner: 渠道问题横幅，按严重度着色；修复提示是 `uv sync` 时提供一键安装与复制命令，其余提示按模式表翻译
 * [POS] 渠道设置页的诊断提示条，由 ChannelsSection 渲染在渠道配置之前。
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconAlertTriangle, IconXCircle, IconAlertCircle } from '@/components/features/icons/PremiumIcons';
import { installChannelDependencies, type ChannelIssue } from '@/services/channels';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { ISSUE_FIX_PATTERNS, ISSUE_MESSAGE_PATTERNS, resolveIssueKey, type IssuePattern } from './issueMessages';

// ─── Sub-components ──────────────────────────────────────────────────

const SEVERITY_STYLES: Record<string, { bg: string; border: string; icon: typeof IconXCircle }> = {
  error: { bg: 'bg-destructive/10', border: 'border-destructive/30', icon: IconXCircle },
  warning: { bg: 'bg-yellow-500/10', border: 'border-yellow-500/30', icon: IconAlertTriangle },
  info: { bg: 'bg-blue-500/10', border: 'border-blue-500/30', icon: IconAlertCircle },
};

function useIssueTranslator() {
  const t = useTranslations('channels.issues');
  return useCallback(
    (text: string, patterns: IssuePattern[]) => {
      const resolved = resolveIssueKey(text, patterns);
      if (!resolved) {
        return text;
      }
      return resolved.rest === null ? t(resolved.key) : `${t(resolved.key)} ${resolved.rest}`;
    },
    [t],
  );
}

const UV_INSTALL_COMMAND = /^uv sync\b/;

function ChannelIssueFix({
  fix,
  channelName,
  onInstalled,
}: {
  fix: string;
  channelName: string;
  onInstalled: () => void;
}) {
  const t = useTranslations('channels.issues');
  const translate = useIssueTranslator();
  const [copied, setCopied] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [installError, setInstallError] = useState<string | null>(null);
  const copiedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (copiedTimerRef.current !== null) {
        clearTimeout(copiedTimerRef.current);
      }
    };
  }, []);

  const handleCopy = useCallback(async () => {
    const ok = await writeToClipboard(fix, true);
    if (ok) {
      setCopied(true);
      if (copiedTimerRef.current !== null) {
        clearTimeout(copiedTimerRef.current);
      }
      copiedTimerRef.current = setTimeout(() => setCopied(false), 2000);
    }
  }, [fix]);

  const handleInstall = useCallback(async () => {
    setInstalling(true);
    setInstallError(null);
    try {
      const result = await installChannelDependencies(channelName);
      if (!result.registered) {
        setInstallError(result.message || t('installDependenciesRegisterFailed'));
        return;
      }
      onInstalled();
    } catch (err) {
      setInstallError(err instanceof Error ? err.message : t('installDependenciesFailed'));
    } finally {
      setInstalling(false);
    }
  }, [channelName, onInstalled, t]);

  if (UV_INSTALL_COMMAND.test(fix)) {
    return (
      <div className="mt-1.5 space-y-1.5">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <button
            type="button"
            onClick={() => void handleInstall()}
            disabled={installing}
            className="shrink-0 rounded-lg border border-primary/40 bg-primary/10 px-3 py-1.5 text-xs font-medium hover:bg-primary/20 disabled:opacity-60"
          >
            {installing ? t('installingDependencies') : t('installDependencies')}
          </button>
          <button
            type="button"
            onClick={() => void handleCopy()}
            className="shrink-0 rounded-lg border px-3 py-1.5 text-xs hover:bg-accent"
          >
            {copied ? t('copiedInstallCommand') : t('copyInstallCommand')}
          </button>
        </div>
        {installError ? <p className="text-destructive-text text-xs">{installError}</p> : null}
        <p className="text-muted-foreground text-xs">{t('fixRunUvSync')}</p>
        <code className="block min-w-0 break-all rounded-md border border-border/60 bg-background/80 px-2 py-1.5 font-mono text-xs">
          {fix}
        </code>
      </div>
    );
  }

  return <p className="mt-0.5 text-muted-foreground text-xs">{translate(fix, ISSUE_FIX_PATTERNS)}</p>;
}

export function ChannelIssueBanner({
  issues,
  channelName,
  onInstalled,
}: {
  issues: ChannelIssue[];
  channelName: string;
  onInstalled: () => void;
}) {
  const translate = useIssueTranslator();
  if (!issues.length) {
    return null;
  }
  return (
    <div className="space-y-2">
      {issues.map((issue, i) => {
        const style = SEVERITY_STYLES[issue.severity] ?? SEVERITY_STYLES.info;
        const Icon = style.icon;
        return (
          <div
            key={`${issue.kind}-${i}`}
            className={`flex items-start gap-2 rounded-lg border px-3 py-2.5 ${style.bg} ${style.border}`}
          >
            <Icon className="h-4 w-4 mt-0.5 shrink-0 text-current opacity-70" />
            <div className="min-w-0 flex-1 text-sm">
              <span className="font-medium">{translate(issue.message, ISSUE_MESSAGE_PATTERNS)}</span>
              {issue.fix ? (
                <ChannelIssueFix fix={issue.fix} channelName={channelName} onInstalled={onInstalled} />
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}
