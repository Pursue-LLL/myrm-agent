'use client';

/**
 * [INPUT] ./useCronCreateForm::CronCreateForm (POS: 表单状态与已连接渠道), ../CronDeliveryEditors::{IM_CHANNELS, needsDeliveryTarget} (POS: 渠道文案与收件人判定), @/store/useAgentStore (POS: 可绑定的 Agent), ../cron-utils::PILL_TOGGLE_CLASS (POS: 胶囊切换样式)
 * [OUTPUT] CronCreateTargetFields: 投递渠道（含收件人输入）与 Agent 绑定两个选择区
 * [POS] 自定义创建流程的“交给谁 / 发到哪”区块：投递渠道仅在存在已连接 IM 渠道时出现，除 chat 外的 IM 渠道需要填写收件人；Agent 绑定仅 Agent 类型且有 Agent 时出现。
 */

import { useLocale, useTranslations } from 'next-intl';
import { MessageCircle, Send } from 'lucide-react';
import { getBuiltinAgentName } from '@/components/agent/builtin-agent-i18n';
import ChannelIcon from '@/components/features/settings/sections/integration/channels/ChannelIcon';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { ToggleGroup, ToggleGroupItem } from '@/components/primitives/toggle-group';
import useAgentStore from '@/store/useAgentStore';
import { IM_CHANNELS, needsDeliveryTarget } from '../CronDeliveryEditors';
import { PILL_TOGGLE_CLASS } from '../cron-utils';
import { DEFAULT_AGENT_ID } from './cronCreateModel';
import type { CronCreateForm } from './useCronCreateForm';

export function CronCreateTargetFields({ form }: { form: CronCreateForm }) {
  const t = useTranslations('cron');
  const locale = useLocale();
  const { agents } = useAgentStore();
  const { draft, patch, options } = form;
  const { uiMode, agentId, deliveryChannel, deliveryTarget } = draft;
  const { connectedChannels } = options;

  return (
    <>
      {/* Delivery Target */}
      {connectedChannels.length > 0 && (
        <div className="space-y-1.5">
          <Label className="text-xs">{t('deliveryLabel')}</Label>
          <ToggleGroup
            type="single"
            value={deliveryChannel}
            onValueChange={(v) => v && patch({ deliveryChannel: v })}
            className="flex-wrap justify-start"
            size="sm"
          >
            <ToggleGroupItem value="chat" className={PILL_TOGGLE_CLASS}>
              <MessageCircle className="h-3.5 w-3.5" />
              {t('deliveryChat')}
            </ToggleGroupItem>
            {connectedChannels.map((ch) => (
              <ToggleGroupItem key={ch} value={ch} className={PILL_TOGGLE_CLASS}>
                <ChannelIcon channelId={ch} size={14} />
                {IM_CHANNELS[ch]?.label ?? ch}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          {needsDeliveryTarget(deliveryChannel) && (
            <div className="flex items-center gap-2">
              <Send className="h-3 w-3 text-muted-foreground shrink-0" />
              <Input
                placeholder={IM_CHANNELS[deliveryChannel]?.hint ?? ''}
                value={deliveryTarget}
                onChange={(e) => patch({ deliveryTarget: e.target.value })}
                className="h-7 text-xs flex-1"
              />
            </div>
          )}
        </div>
      )}

      {/* Agent Binding */}
      {uiMode === 'agent' && agents.length > 0 && (
        <div className="space-y-1.5">
          <Label className="text-xs">{t('createAgentLabel')}</Label>
          <Select value={agentId} onValueChange={(value) => patch({ agentId: value })}>
            <SelectTrigger className="h-8 text-sm">
              <SelectValue placeholder={t('createAgentDefault')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={DEFAULT_AGENT_ID}>{t('createAgentDefault')}</SelectItem>
              {agents.map((a) => (
                <SelectItem key={a.id} value={a.id}>
                  {getBuiltinAgentName(a.id, a.name, locale)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
    </>
  );
}
