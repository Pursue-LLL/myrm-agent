'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { CATEGORY_MAP, type RiskRule } from './risk-rules-types';

interface RiskRuleEditorProps {
  rule: Partial<RiskRule>;
  isCreating: boolean;
  onChange: (rule: Partial<RiskRule>) => void;
  onSave: () => void;
  onCancel: () => void;
}

/** Form for a new rule or an existing one; the id is fixed once a rule exists, the pattern of a built-in rule always. */
function RiskRuleEditor({ rule, isCreating, onChange, onSave, onCancel }: RiskRuleEditorProps) {
  const t = useTranslations('settings.securityPolicy.riskRules');

  return (
    <div className="border border-primary/30 rounded-lg p-4 mb-4 space-y-3 bg-card">
      <h3 className="font-medium text-sm">{isCreating ? t('createRule') : t('editRule')}</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Input
          placeholder={t('ruleId')}
          value={rule.rule_id || ''}
          onChange={(e) => onChange({ ...rule, rule_id: e.target.value })}
          disabled={!isCreating}
        />
        <Input
          placeholder={t('displayName')}
          value={rule.display_name || ''}
          onChange={(e) => onChange({ ...rule, display_name: e.target.value })}
        />
      </div>
      <Input
        placeholder={t('pattern')}
        value={rule.pattern || ''}
        onChange={(e) => onChange({ ...rule, pattern: e.target.value })}
        className="font-mono text-sm"
        disabled={!isCreating && rule.is_builtin === true}
      />
      {!isCreating && rule.is_builtin && (
        <p className="text-xs text-muted-foreground">{t('builtinCannotEditPattern')}</p>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Select value={rule.severity || 'medium'} onValueChange={(v) => onChange({ ...rule, severity: v })}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="low">{t('severityLow')}</SelectItem>
            <SelectItem value="medium">{t('severityMedium')}</SelectItem>
            <SelectItem value="high">{t('severityHigh')}</SelectItem>
          </SelectContent>
        </Select>
        <Select value={rule.category || 'custom'} onValueChange={(v) => onChange({ ...rule, category: v })}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(CATEGORY_MAP).map(([key, labelKey]) => (
              <SelectItem key={key} value={key}>
                {t(labelKey)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex gap-2">
        <Button size="sm" onClick={onSave}>
          {t('saveRule')}
        </Button>
        <Button variant="outline" size="sm" onClick={onCancel}>
          {t('cancel')}
        </Button>
      </div>
    </div>
  );
}

export default memo(RiskRuleEditor);
