'use client';

/**
 * [INPUT] ./DescribedSelectItem (POS: 带说明行的下拉选项), ./agentEditFormModel::AgentExtraFields (POS: 非 react-hook-form 字段模型)
 * [OUTPUT] AgentEditSessionPolicy: 会话重置策略开关与模式（持久 / 每日 / 空闲）及其参数
 * [POS] 智能体创建 / 编辑表单的会话策略区段；关闭开关时提交 null，沿用全局会话重置策略。
 */

import { useTranslations } from 'next-intl';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Switch } from '@/components/primitives/switch';
import type { AgentSessionPolicy, SessionResetMode } from '@/services/agent';
import { DescribedSelectItem } from '@/components/agent/DescribedSelectItem';
import type { AgentExtraFields } from '@/components/agent/agentEditFormModel';

interface AgentEditSessionPolicyProps {
  value: Pick<AgentExtraFields, 'sessionPolicyEnabled' | 'sessionPolicy'>;
  onChange: (patch: Partial<AgentExtraFields>) => void;
}

export function AgentEditSessionPolicy({ value, onChange }: AgentEditSessionPolicyProps) {
  const t = useTranslations('Agent');
  const { sessionPolicyEnabled, sessionPolicy } = value;
  const updatePolicy = (patch: Partial<AgentSessionPolicy>) =>
    onChange({ sessionPolicy: { ...sessionPolicy, ...patch } });

  return (
    <div className="space-y-3 rounded-lg border border-border/60 p-4">
      <div className="flex items-center justify-between">
        <Label className="text-sm font-medium">{t('form.sessionPolicy.title')}</Label>
        <Switch
          checked={sessionPolicyEnabled}
          onCheckedChange={(enabled) => onChange({ sessionPolicyEnabled: enabled })}
        />
      </div>
      <p className="text-xs text-muted-foreground">{t('form.sessionPolicy.description')}</p>

      {sessionPolicyEnabled && (
        <div className="space-y-3 pt-2">
          <div className="space-y-1.5">
            <Label className="text-xs">{t('form.sessionPolicy.mode')}</Label>
            <Select value={sessionPolicy.mode} onValueChange={(v) => updatePolicy({ mode: v as SessionResetMode })}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <DescribedSelectItem
                  value="persistent"
                  label={t('form.sessionPolicy.modePersistent')}
                  description={t('form.sessionPolicy.modePersistentDesc')}
                />
                <DescribedSelectItem
                  value="daily"
                  label={t('form.sessionPolicy.modeDaily')}
                  description={t('form.sessionPolicy.modeDailyDesc')}
                />
                <DescribedSelectItem
                  value="idle"
                  label={t('form.sessionPolicy.modeIdle')}
                  description={t('form.sessionPolicy.modeIdleDesc')}
                />
              </SelectContent>
            </Select>
          </div>

          {sessionPolicy.mode === 'daily' && (
            <div className="space-y-1.5">
              <Label className="text-xs">{t('form.sessionPolicy.dailyResetHour')}</Label>
              <Select
                value={String(sessionPolicy.daily_reset_hour)}
                onValueChange={(v) => updatePolicy({ daily_reset_hour: Number(v) })}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Array.from({ length: 24 }, (_, i) => (
                    <SelectItem key={i} value={String(i)}>
                      {String(i).padStart(2, '0')}:00 UTC
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {sessionPolicy.mode === 'idle' && (
            <div className="space-y-1.5">
              <Label className="text-xs">{t('form.sessionPolicy.idleMinutes')}</Label>
              <Input
                type="number"
                min={1}
                max={10080}
                value={sessionPolicy.idle_minutes}
                onChange={(e) =>
                  updatePolicy({ idle_minutes: Math.max(1, Math.min(10080, Number(e.target.value) || 1)) })
                }
              />
              <p className="text-xs text-muted-foreground">{t('form.sessionPolicy.idleMinutesHint')}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
