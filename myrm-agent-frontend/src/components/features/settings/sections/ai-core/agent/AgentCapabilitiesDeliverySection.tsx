'use client';

import { useTranslations } from 'next-intl';
import { Switch } from '@/components/primitives/switch';
import type { AgentCapabilitiesTabProps } from './AgentCapabilitiesTab';

type SectionProps = {
  editor: AgentCapabilitiesTabProps['editor'];
  t: ReturnType<typeof useTranslations>;
};

export function DeliveryAssuranceSection({ editor, t }: SectionProps) {
  return (
    <div className="rounded-xl bg-card/60 border border-border/50 p-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h4 className="text-sm font-medium text-foreground">{t('agent.deliveryAssurance')}</h4>
          <p className="text-xs text-muted-foreground mt-0.5">{t('agent.deliveryAssuranceDesc')}</p>
        </div>
      </div>
      <div className="flex items-center justify-between gap-4 pt-3 mt-3 border-t border-border/30">
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-medium text-foreground">{t('agent.cronPostRunVerify')}</h4>
          <p className="text-xs text-muted-foreground mt-0.5">{t('agent.cronPostRunVerifyDesc')}</p>
          <p className="text-[11px] text-muted-foreground/80 mt-1.5 leading-relaxed">{t('agent.cronPostRunVerifyHint')}</p>
        </div>
        <Switch
          checked={editor.cronPostRunVerify}
          onCheckedChange={(checked) => editor.setCronPostRunVerify(checked)}
          className="shrink-0"
        />
      </div>
    </div>
  );
}
