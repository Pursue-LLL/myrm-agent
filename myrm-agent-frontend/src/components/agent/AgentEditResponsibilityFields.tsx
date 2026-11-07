'use client';

/**
 * [INPUT] ./agentEditFormModel::AgentExtraFields (POS: 非 react-hook-form 字段模型), react-textarea-autosize (POS: 自适应高度文本域)
 * [OUTPUT] AgentEditResponsibilityFields: 责任范围、负责人与验收清单三项责任属性
 * [POS] 智能体创建 / 编辑表单的责任区段；仅用于健康检查，不会发送给模型。
 */

import { useTranslations } from 'next-intl';
import TextareaAutosize from 'react-textarea-autosize';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import type { AgentExtraFields } from '@/components/agent/agentEditFormModel';

const TEXTAREA_CLASS =
  'flex w-full rounded-lg border border-input bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none';

interface AgentEditResponsibilityFieldsProps {
  value: Pick<AgentExtraFields, 'responsibilityScope' | 'ownerLabel' | 'acceptanceCriteriaText'>;
  onChange: (patch: Partial<AgentExtraFields>) => void;
}

export function AgentEditResponsibilityFields({ value, onChange }: AgentEditResponsibilityFieldsProps) {
  const t = useTranslations('Agent');
  const { responsibilityScope, ownerLabel, acceptanceCriteriaText } = value;

  return (
    <div className="space-y-2 rounded-xl border border-border/60 bg-muted/20 p-4">
      <div>
        <Label>{t('form.responsibilityTitle')}</Label>
        <p className="text-xs text-muted-foreground mt-0.5">{t('form.responsibilityHint')}</p>
      </div>
      <div className="space-y-2">
        <Label htmlFor="responsibility_scope">{t('form.responsibilityScope')}</Label>
        <TextareaAutosize
          id="responsibility_scope"
          value={responsibilityScope}
          onChange={(e) => onChange({ responsibilityScope: e.target.value })}
          minRows={2}
          maxRows={6}
          maxLength={2000}
          className={TEXTAREA_CLASS}
          placeholder={t('form.responsibilityScopePlaceholder')}
        />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label htmlFor="owner_label">{t('form.ownerLabel')}</Label>
          <Input
            id="owner_label"
            value={ownerLabel}
            onChange={(e) => onChange({ ownerLabel: e.target.value })}
            maxLength={100}
            placeholder={t('form.ownerLabelPlaceholder')}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="acceptance_criteria">{t('form.acceptanceCriteria')}</Label>
          <TextareaAutosize
            id="acceptance_criteria"
            value={acceptanceCriteriaText}
            onChange={(e) => onChange({ acceptanceCriteriaText: e.target.value })}
            minRows={2}
            maxRows={6}
            className={TEXTAREA_CLASS}
            placeholder={t('form.acceptanceCriteriaPlaceholder')}
          />
        </div>
      </div>
    </div>
  );
}
