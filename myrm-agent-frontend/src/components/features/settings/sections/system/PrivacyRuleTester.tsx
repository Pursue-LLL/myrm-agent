'use client';

/**
 * [INPUT]
 *   useConfigStore (POS: 全局配置状态管理，读取表单里的处理方式与自定义规则)
 *   lib/api::fetchWithTimeout (POS: 前端统一请求入口)
 *   next-intl useTranslations
 * [OUTPUT]
 *   PrivacyRuleTester: 隐私规则"试一试"卡片，输入一句话，展示按当前设置模型会收到什么
 * [POS]
 *   隐私保护设置面板的规则试验台。判定交给后端 `POST /config/privacy-preview`（与对话回合同一套检测与处理），
 *   前端只负责展示，不再自己匹配，避免试验结果与实际行为不一致
 */

import { memo, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconBan, IconFlask, IconLoader } from '@/components/features/icons/PremiumIcons';
import { Input } from '@/components/primitives/input';
import { fetchWithTimeout } from '@/lib/api';
import useConfigStore from '@/store/useConfigStore';
import type { PIIAction } from '@/services/config/types';

type SensitivityLevel = 's1' | 's2' | 's3';

interface PrivacyPreview {
  level: SensitivityLevel;
  action: PIIAction | null;
  model_sees: string | null;
}

type PreviewState =
  | { status: 'idle' }
  | { status: 'checking'; previous: PrivacyPreview | null }
  | { status: 'done'; preview: PrivacyPreview }
  | { status: 'failed' };

const MAX_TEXT_CHARS = 4000;
const DEBOUNCE_MS = 400;
const REQUEST_TIMEOUT_MS = 8000;

const ACTION_LABEL_KEYS: Record<PIIAction, string> = {
  warn: 'actionWarn',
  pseudonymize: 'actionPseudonymize',
  redact: 'actionRedact',
  block: 'actionBlock',
};

const LEVEL_BADGE_CLASS: Record<Exclude<SensitivityLevel, 's1'>, string> = {
  s2: 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400 border-amber-200 dark:border-amber-800/50',
  s3: 'bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-400 border-red-200 dark:border-red-800/50',
};

const PrivacyRuleTester = memo(() => {
  const t = useTranslations('settings.securityPolicy.privacy');
  const s2Action = useConfigStore((state) => state.privacyS2Action);
  const s3Action = useConfigStore((state) => state.privacyS3Action);
  const keywordsS2 = useConfigStore((state) => state.privacyCustomKeywordsS2);
  const keywordsS3 = useConfigStore((state) => state.privacyCustomKeywordsS3);
  const patternsS2 = useConfigStore((state) => state.privacyCustomPatternsS2);
  const patternsS3 = useConfigStore((state) => state.privacyCustomPatternsS3);
  const deepScan = useConfigStore((state) => state.privacyDeepScan);

  const [text, setText] = useState('');
  const [state, setState] = useState<PreviewState>({ status: 'idle' });

  useEffect(() => {
    const trimmed = text.trim();
    if (!trimmed) {
      setState({ status: 'idle' });
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setState((current) => ({
        status: 'checking',
        previous: current.status === 'done' ? current.preview : current.status === 'checking' ? current.previous : null,
      }));
      try {
        const response = await fetchWithTimeout(
          '/config/privacy-preview',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            signal: controller.signal,
            body: JSON.stringify({
              text: trimmed,
              privacy_s2_action: s2Action,
              privacy_s3_action: s3Action,
              privacy_custom_keywords_s2: keywordsS2,
              privacy_custom_keywords_s3: keywordsS3,
              privacy_custom_patterns_s2: patternsS2,
              privacy_custom_patterns_s3: patternsS3,
            }),
          },
          REQUEST_TIMEOUT_MS,
        );
        if (!response.ok) {
          throw new Error(`preview failed: ${response.status}`);
        }
        const preview = (await response.json()) as PrivacyPreview;
        if (!controller.signal.aborted) {
          setState({ status: 'done', preview });
        }
      } catch {
        if (!controller.signal.aborted) {
          setState({ status: 'failed' });
        }
      }
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [text, s2Action, s3Action, keywordsS2, keywordsS3, patternsS2, patternsS3]);

  const checking = state.status === 'checking';
  const preview = state.status === 'done' ? state.preview : state.status === 'checking' ? state.previous : null;

  return (
    <div className="rounded-xl border border-border/60 bg-muted/30 p-3 space-y-2.5">
      <div className="flex items-center gap-2">
        <IconFlask className="h-3.5 w-3.5 text-primary" />
        <span className="text-sm font-medium text-foreground">{t('tester.title')}</span>
        {checking && (
          <output aria-label={t('tester.checking')}>
            <IconLoader className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
          </output>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{t('tester.description')}</p>
      <Input
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder={t('tester.placeholder')}
        maxLength={MAX_TEXT_CHARS}
        className="text-sm"
      />
      {deepScan && <p className="text-xs text-muted-foreground">{t('tester.deepScanNote')}</p>}

      {state.status === 'failed' && <p className="text-xs text-destructive">{t('tester.failed')}</p>}

      {preview && (
        <div className={`space-y-2 transition-opacity ${checking ? 'opacity-60' : ''}`}>
          {preview.level === 's1' || preview.action === null ? (
            <p className="text-xs text-muted-foreground">{t('tester.levelNone')}</p>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full border ${LEVEL_BADGE_CLASS[preview.level]}`}
                >
                  {t(preview.level === 's3' ? 'tester.levelS3' : 'tester.levelS2')}
                </span>
                <span className="text-xs text-muted-foreground">
                  {t('tester.action', { action: t(ACTION_LABEL_KEYS[preview.action]) })}
                </span>
              </div>
              {preview.model_sees === null ? (
                <p className="flex items-start gap-1.5 text-xs text-destructive">
                  <IconBan className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                  {t('tester.blocked')}
                </p>
              ) : (
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground">{t('tester.modelSees')}</p>
                  <p className="rounded-lg border border-border/60 bg-background p-2 font-mono text-xs text-foreground whitespace-pre-wrap break-words">
                    {preview.model_sees}
                  </p>
                  {preview.action === 'warn' && (
                    <p className="text-xs text-muted-foreground">{t('tester.unchanged')}</p>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
});
PrivacyRuleTester.displayName = 'PrivacyRuleTester';

export { PrivacyRuleTester };
