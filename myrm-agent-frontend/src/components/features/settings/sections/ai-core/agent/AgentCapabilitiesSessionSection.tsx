'use client';

import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Input } from '@/components/primitives/input';
import { Switch } from '@/components/primitives/switch';
import type { AgentCapabilitiesTabProps } from './AgentCapabilitiesTab';

type SectionProps = {
  editor: AgentCapabilitiesTabProps['editor'];
  t: ReturnType<typeof useTranslations>;
};

export function SessionPolicySection({ editor, t }: SectionProps) {
  return (
    <div className="rounded-xl bg-card/60 border border-border/50 p-4 space-y-3">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h4 className="text-sm font-medium text-foreground">{t('agent.cronPostRunVerify')}</h4>
          <p className="text-xs text-muted-foreground mt-0.5">{t('agent.cronPostRunVerifyDesc')}</p>
        </div>
        <Switch
          checked={editor.cronPostRunVerify}
          onCheckedChange={(checked) => editor.setCronPostRunVerify(checked)}
        />
      </div>

      <div className="flex items-center justify-between pt-2 border-t border-border/30">
        <div>
          <h4 className="text-sm font-medium text-foreground">{t('agent.sessionPolicy')}</h4>
          <p className="text-xs text-muted-foreground mt-0.5">{t('agent.sessionPolicyDesc')}</p>
        </div>
        <Switch
          checked={editor.sessionPolicy !== null}
          onCheckedChange={(checked) => {
            editor.setSessionPolicy(checked ? { mode: 'daily', daily_reset_hour: 4, idle_minutes: 120 } : null);
          }}
        />
      </div>
      {editor.sessionPolicy && (
        <div className="space-y-3 pt-2 border-t border-border/30">
          <div>
            <label className="text-xs font-medium text-muted-foreground">{t('agent.sessionPolicyMode')}</label>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-1.5">
              {(['persistent', 'daily', 'idle'] as const).map((mode) => (
                <button key={mode} type="button"
                  className={cn(
                    'rounded-lg border px-3 py-2 text-xs transition-all',
                    editor.sessionPolicy?.mode === mode
                      ? 'border-primary bg-primary/10 text-primary font-medium'
                      : 'border-border/50 bg-card/30 text-muted-foreground hover:border-primary/30',
                  )}
                  onClick={() => editor.setSessionPolicy({ ...editor.sessionPolicy!, mode })}>
                  <span className="block font-medium">{t(`agent.sessionPolicy${mode.charAt(0).toUpperCase() + mode.slice(1)}` as 'agent.sessionPolicyPersistent')}</span>
                  <span className="block text-[10px] mt-0.5 opacity-70">{t(`agent.sessionPolicy${mode.charAt(0).toUpperCase() + mode.slice(1)}Desc` as 'agent.sessionPolicyPersistentDesc')}</span>
                </button>
              ))}
            </div>
          </div>
          {editor.sessionPolicy.mode === 'daily' && (
            <div>
              <label className="text-xs font-medium text-muted-foreground">{t('agent.sessionPolicyResetHour')}</label>
              <Input type="number" min={0} max={23}
                value={editor.sessionPolicy.daily_reset_hour}
                onChange={(e) => editor.setSessionPolicy({ ...editor.sessionPolicy!, daily_reset_hour: Math.max(0, Math.min(23, parseInt(e.target.value, 10) || 0)) })}
                className="w-full mt-1" />
            </div>
          )}
          {editor.sessionPolicy.mode === 'idle' && (
            <div>
              <label className="text-xs font-medium text-muted-foreground">{t('agent.sessionPolicyIdleMinutes')}</label>
              <Input type="number" min={1} max={10080}
                value={editor.sessionPolicy.idle_minutes}
                onChange={(e) => editor.setSessionPolicy({ ...editor.sessionPolicy!, idle_minutes: Math.max(1, Math.min(10080, parseInt(e.target.value, 10) || 120)) })}
                className="w-full mt-1" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
