'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import useChatStore from '@/store/useChatStore';
import useSkillStore from '@/store/skill/useSkillStore';
import { useShallow } from 'zustand/react/shallow';
import {
  buildAgentSkillsSettingsHref,
  containsWeixinArticleUrl,
  isWechatArticleFormatterActive,
  WECHAT_ARTICLE_FORMATTER_SKILL,
} from './wechatComposerHintUtils';

const EMPTY_SKILL_IDS: string[] = [];

interface WechatArticleComposerHintProps {
  inputMessage: string;
  className?: string;
}

export function WechatArticleComposerHint({ inputMessage, className }: WechatArticleComposerHintProps) {
  const t = useTranslations('chat.wechatArticleHint');
  const [dismissed, setDismissed] = useState(false);

  const { agentId, selectedSkillIds, sessionSkillOverrides } = useChatStore(
    useShallow((state) => ({
      agentId: state.agentConfig?.agentId ?? null,
      selectedSkillIds: state.agentConfig?.selectedSkillIds ?? EMPTY_SKILL_IDS,
      sessionSkillOverrides: state.sessionSkillOverrides,
    })),
  );

  const { marketSkills, localSkills } = useSkillStore(
    useShallow((state) => ({
      marketSkills: state.marketSkills,
      localSkills: state.localSkills,
    })),
  );

  const formatterSkillIds = useMemo(() => {
    const all = [...marketSkills, ...localSkills];
    return all.filter((skill) => skill.name === WECHAT_ARTICLE_FORMATTER_SKILL).map((skill) => skill.id);
  }, [localSkills, marketSkills]);

  const formatterReady = useMemo(
    () =>
      isWechatArticleFormatterActive({
        selectedSkillIds,
        sessionSkillOverrides,
        formatterSkillIds,
      }),
    [formatterSkillIds, selectedSkillIds, sessionSkillOverrides],
  );

  const visible = containsWeixinArticleUrl(inputMessage) && !dismissed;

  if (!visible) {
    return null;
  }

  const settingsHref = buildAgentSkillsSettingsHref(agentId);

  return (
    <div
      className={cn(
        'mb-2 flex items-start gap-2 rounded-md border border-primary/25 bg-primary/5 px-3 py-2 text-xs text-foreground',
        className,
      )}
      data-testid="wechat-article-composer-hint"
    >
      <div className="min-w-0 flex-1 space-y-1">
        <p className="font-medium text-foreground">{formatterReady ? t('readyTitle') : t('title')}</p>
        <p className="text-muted-foreground leading-snug">
          {formatterReady ? t('readyDescription') : t('description')}
        </p>
        {!formatterReady ? (
          <Link href={settingsHref} className="inline-flex font-medium text-primary underline-offset-4 hover:underline">
            {t('openSkills')}
          </Link>
        ) : null}
      </div>
      <button
        type="button"
        className="shrink-0 rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
        aria-label={t('dismiss')}
        onClick={() => setDismissed(true)}
      >
        <X size={14} />
      </button>
    </div>
  );
}
