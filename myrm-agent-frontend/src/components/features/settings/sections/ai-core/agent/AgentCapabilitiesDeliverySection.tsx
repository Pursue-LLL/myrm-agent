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
        <div>
          <h4 className="text-sm font-medium text-foreground">{t('agent.cronPostRunVerify')}</h4>
          <p className="text-xs text-muted-foreground mt-0.5">{t('agent.cronPostRunVerifyDesc')}</p>
        </div>
        <Switch
          checked={editor.cronPostRunVerify}
          onCheckedChange={(checked) => editor.setCronPostRunVerify(checked)}
        />
      </div>
    </div>
  );
}
