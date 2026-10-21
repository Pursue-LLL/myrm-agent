'use client';

/**
 * [INPUT]
 *   useConfigStore (POS: 全局配置状态管理，读取表单里的处理方式与自定义规则)
 *   lib/api::fetchWithTimeout (POS: 前端统一请求入口)
 *   next-intl useTranslations
 * [OUTPUT]
 *   PrivacyRuleTester: 隐私规则"试一试"卡片，输入一句话，展示按当前设置模型会收到什么；有自定义模式时，
 *   无论是否输入句子，都列出写法有误、无法生效的模式
 * [POS]
 *   隐私保护设置面板的规则试验台。判定交给后端 `POST /config/privacy-preview`（与对话回合同一套检测与处理），
 *   前端只负责展示、不做本地匹配或校验，试验结果与「哪些模式无效」因此都与实际行为一致
 */

import { memo, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconAlertTriangle, IconBan, IconFlask, IconLoader } from '@/components/features/icons/PremiumIcons';
import { Input } from '@/components/primitives/input';
import { fetchWithTimeout } from '@/lib/api';
import useConfigStore from '@/store/useConfigStore';
import type { PIIAction } from '@/services/config/types';

type SensitivityLevel = 's1' | 's2' | 's3';

interface PrivacyPreview {
  level: SensitivityLevel;
  action: PIIAction | null;
  model_sees: string | null;
  ineffective_patterns: string[];
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

const IneffectivePatternsNotice = memo(({ patterns }: { patterns: string[] }) => {
  const t = useTranslations('settings.securityPolicy.privacy');
  return (
    <output className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-2.5 dark:border-amber-800/50 dark:bg-amber-950/30">
      <IconAlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
      <span className="min-w-0 space-y-1.5">
        <span className="block text-xs font-medium text-amber-700 dark:text-amber-400">
          {t('tester.ineffectiveTitle')}
        </span>
        <span className="flex flex-wrap gap-1.5">
          {patterns.map((pattern) => (
            <code
              key={pattern}
              className="max-w-full break-all rounded-md border border-amber-200 bg-background px-1.5 py-0.5 font-mono text-xs text-foreground dark:border-amber-800/50"
            >
              {pattern}
            </code>
          ))}
        </span>
        <span className="block text-xs text-amber-700/90 dark:text-amber-400/90">{t('tester.ineffectiveHint')}</span>
      </span>
    </output>
  );
});
IneffectivePatternsNotice.displayName = 'IneffectivePatternsNotice';

const SentenceVerdict = memo(({ preview }: { preview: PrivacyPreview }) => {
  const t = useTranslations('settings.securityPolicy.privacy');
  if (preview.level === 's1' || preview.action === null) {
    return <p className="text-xs text-muted-foreground">{t('tester.levelNone')}</p>;
  }
  return (
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
          {preview.action === 'warn' && <p className="text-xs text-muted-foreground">{t('tester.unchanged')}</p>}
        </div>
      )}
    </>
  );
});
SentenceVerdict.displayName = 'SentenceVerdict';

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
  const hasPatterns = patternsS2.length + patternsS3.length > 0;

  useEffect(() => {
    const trimmed = text.trim();
    if (!trimmed && !hasPatterns) {
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
  }, [text, hasPatterns, s2Action, s3Action, keywordsS2, keywordsS3, patternsS2, patternsS3]);

  const checking = state.status === 'checking';
  const preview = state.status === 'done' ? state.preview : state.status === 'checking' ? state.previous : null;
  const hasText = text.trim() !== '';

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
          {preview.ineffective_patterns.length > 0 && (
            <IneffectivePatternsNotice patterns={preview.ineffective_patterns} />
          )}
          {hasText && <SentenceVerdict preview={preview} />}
        </div>
      )}
    </div>
  );
});
PrivacyRuleTester.displayName = 'PrivacyRuleTester';

export { PrivacyRuleTester };
