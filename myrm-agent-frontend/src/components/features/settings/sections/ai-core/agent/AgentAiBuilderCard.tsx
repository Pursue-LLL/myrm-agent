'use client';

/**
 * [INPUT]
 * @/lib/utils/imeUtils::isImeComposing (POS: 输入法组合态判定)
 *
 * [OUTPUT]
 * AgentAiBuilderCard: 新建智能体时的“一句话生成配置”卡片
 *
 * [POS]
 * AI 生成配置的展示层；意图文本与生成状态由 useAgentAiBuild 持有并经 props 传入，卡片本身无状态。
 */

import { Loader2, Sparkles, Wand2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Textarea } from '@/components/primitives/textarea';
import { isImeComposing } from '@/lib/utils/imeUtils';

interface AgentAiBuilderCardProps {
  intent: string;
  generating: boolean;
  onIntentChange: (intent: string) => void;
  onBuild: (intent: string) => Promise<void>;
}

export function AgentAiBuilderCard({ intent, generating, onIntentChange, onBuild }: AgentAiBuilderCardProps) {
  const t = useTranslations('agent.aiBuilder');

  return (
    <div className="rounded-2xl border border-primary/20 bg-gradient-to-r from-primary/5 to-violet-500/5 p-5">
      <div className="flex items-center gap-2 mb-3">
        <Wand2 className="w-5 h-5 text-primary" />
        <h3 className="text-sm font-semibold text-foreground">{t('title')}</h3>
      </div>
      <p className="text-xs text-muted-foreground mb-3">{t('subtitle')}</p>
      <div className="flex flex-col sm:flex-row gap-2">
        <Textarea
          value={intent}
          onChange={(e) => onIntentChange(e.target.value)}
          placeholder={t('placeholder')}
          className="min-h-[60px] max-h-[100px] resize-none text-sm flex-1"
          disabled={generating}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !isImeComposing(e)) {
              e.preventDefault();
              void onBuild(intent);
            }
          }}
        />
        <Button
          size="sm"
          className="shrink-0 self-end gap-1.5 sm:self-end"
          onClick={() => void onBuild(intent)}
          disabled={!intent.trim() || generating}
        >
          {generating ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              {t('generating')}
            </>
          ) : (
            <>
              <Sparkles className="w-3.5 h-3.5" />
              {t('apply')}
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
