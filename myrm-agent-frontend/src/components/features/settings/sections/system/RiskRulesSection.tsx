'use client';

import { memo, useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconPlus,
  IconShield,
  IconFlask,
  IconRefresh,
  IconLoader,
  IconCheckCircle,
  IconSearch,
  IconDownload,
  IconUpload,
} from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { toast } from '@/lib/utils/toast';
import { apiRequest } from '@/lib/api';
import SettingsSection from '../SettingsSection';
import RiskRulesTestPanel from './RiskRulesTestPanel';
import RiskRulesHitsPanel from './RiskRulesHitsPanel';
import RiskRuleEditor from './RiskRuleEditor';
import RiskRuleRow from './RiskRuleRow';
import { useRiskRulesTransfer } from './useRiskRulesTransfer';
import { CATEGORY_MAP, type RiskRule } from './risk-rules-types';

const NEW_RULE: Partial<RiskRule> = {
  rule_id: '',
  display_name: '',
  pattern: '',
  severity: 'medium',
  category: 'custom',
  description: '',
  sort_order: 0,
};

function RiskRulesSection() {
  const t = useTranslations('settings.securityPolicy.riskRules');

  const getRuleName = useCallback(
    (rule: RiskRule) => {
      const key = `rules.${rule.rule_id}.name` as Parameters<typeof t>[0];
      return rule.is_builtin && t.has(key) ? t(key) : rule.display_name;
    },
    [t],
  );

  const getRuleDesc = useCallback(
    (rule: RiskRule) => {
      const key = `rules.${rule.rule_id}.desc` as Parameters<typeof t>[0];
      return rule.is_builtin && t.has(key) ? t(key) : rule.description;
    },
    [t],
  );

  const [rules, setRules] = useState<RiskRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [editingRule, setEditingRule] = useState<Partial<RiskRule> | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [testOpen, setTestOpen] = useState(false);
  const [hitsOpen, setHitsOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const closeEditor = useCallback(() => {
    setEditingRule(null);
    setIsCreating(false);
  }, []);

  const loadRules = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (categoryFilter !== 'all') {
        params.set('category', categoryFilter);
      }
      const data = await apiRequest<RiskRule[]>(`/risk/rules?${params}`);
      setRules(Array.isArray(data) ? data : []);
    } catch {
      toast.error(t('loadError'));
    } finally {
      setLoading(false);
    }
  }, [categoryFilter, t]);

  useEffect(() => {
    loadRules();
  }, [loadRules]);

  const { handleExport, handleImport } = useRiskRulesTransfer(rules, loadRules);

  const handleToggle = useCallback(
    async (ruleId: string, enabled: boolean) => {
      try {
        await apiRequest(`/risk/rules/${ruleId}`, {
          method: 'PATCH',
          body: JSON.stringify({ is_enabled: enabled }),
        });
        setRules((prev) => prev.map((r) => (r.rule_id === ruleId ? { ...r, is_enabled: enabled } : r)));
        toast.success(t('toggleSuccess'));
      } catch {
        toast.error(t('actionError'));
      }
    },
    [t],
  );

  const handleBatchToggle = useCallback(
    async (enabled: boolean) => {
      const ids = rules.map((r) => r.rule_id);
      if (ids.length === 0) {
        return;
      }
      try {
        await apiRequest('/risk/rules/batch-toggle', {
          method: 'POST',
          body: JSON.stringify({ rule_ids: ids, is_enabled: enabled }),
        });
        setRules((prev) => prev.map((r) => ({ ...r, is_enabled: enabled })));
        toast.success(t('toggleSuccess'));
      } catch {
        toast.error(t('actionError'));
      }
    },
    [rules, t],
  );

  const confirmDelete = useCallback(async () => {
    if (!deleteTarget) {
      return;
    }
    try {
      await apiRequest(`/risk/rules/${deleteTarget}`, { method: 'DELETE' });
      setRules((prev) => prev.filter((r) => r.rule_id !== deleteTarget));
      toast.success(t('deleteSuccess'));
    } catch {
      toast.error(t('actionError'));
    } finally {
      setDeleteTarget(null);
    }
  }, [deleteTarget, t]);

  const handleSave = useCallback(async () => {
    if (!editingRule) {
      return;
    }
    try {
      if (isCreating) {
        await apiRequest('/risk/rules', { method: 'POST', body: JSON.stringify(editingRule) });
        toast.success(t('createSuccess'));
      } else {
        const { rule_id, ...updates } = editingRule;
        await apiRequest(`/risk/rules/${rule_id}`, {
          method: 'PATCH',
          body: JSON.stringify(updates),
        });
        toast.success(t('saveSuccess'));
      }
      closeEditor();
      loadRules();
    } catch {
      toast.error(t('actionError'));
    }
  }, [closeEditor, editingRule, isCreating, loadRules, t]);

  const handleEdit = useCallback((rule: RiskRule) => {
    setEditingRule({ ...rule });
    setIsCreating(false);
  }, []);

  const handleDuplicate = useCallback(
    (rule: RiskRule) => {
      setEditingRule({
        rule_id: `${rule.rule_id}_copy`,
        display_name: t('duplicatedName', { name: getRuleName(rule) }),
        pattern: rule.pattern,
        severity: rule.severity,
        category: rule.category,
        description: rule.description,
        sort_order: rule.sort_order,
      });
      setIsCreating(true);
    },
    [getRuleName, t],
  );

  const filteredRules = useMemo(() => {
    if (!searchQuery.trim()) {
      return rules;
    }
    const q = searchQuery.toLowerCase();
    return rules.filter((r) => {
      const name = getRuleName(r).toLowerCase();
      const desc = (getRuleDesc(r) ?? '').toLowerCase();
      return name.includes(q) || desc.includes(q) || r.rule_id.includes(q);
    });
  }, [rules, searchQuery, getRuleName, getRuleDesc]);

  const enabledCount = rules.filter((r) => r.is_enabled).length;

  return (
    <SettingsSection title={t('title')} description={t('description')}>
      {/* Search */}
      <div className="relative mb-3">
        <IconSearch className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <Input
          placeholder={t('searchPlaceholder')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-9 h-9"
        />
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <Select value={categoryFilter} onValueChange={setCategoryFilter}>
          <SelectTrigger className="w-40 h-9">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('allCategories')}</SelectItem>
            {Object.entries(CATEGORY_MAP).map(([key, labelKey]) => (
              <SelectItem key={key} value={key}>
                {t(labelKey)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={() => handleBatchToggle(true)}>
          <IconShield className="w-4 h-4 mr-1" /> {t('enableAll')}
        </Button>
        <Button variant="outline" size="sm" onClick={() => handleBatchToggle(false)}>
          <IconShield className="w-4 h-4 mr-1" /> {t('disableAll')}
        </Button>
        <div className="flex-1" />
        <Button variant="outline" size="sm" onClick={() => setTestOpen(!testOpen)}>
          <IconFlask className="w-4 h-4 mr-1" /> {t('testRule')}
        </Button>
        <Button variant="outline" size="sm" onClick={() => setHitsOpen(!hitsOpen)}>
          <IconCheckCircle className="w-4 h-4 mr-1" /> {t('hits')}
        </Button>
        <Button variant="outline" size="sm" onClick={handleExport} title={t('exportRules')}>
          <IconDownload className="w-4 h-4" />
        </Button>
        <Button variant="outline" size="sm" onClick={handleImport} title={t('importRules')}>
          <IconUpload className="w-4 h-4" />
        </Button>
        <Button
          size="sm"
          onClick={() => {
            setEditingRule(NEW_RULE);
            setIsCreating(true);
          }}
        >
          <IconPlus className="w-4 h-4 mr-1" /> {t('addRule')}
        </Button>
        <Button variant="ghost" size="sm" onClick={loadRules}>
          <IconRefresh className="w-4 h-4" />
        </Button>
      </div>

      {/* Stats */}
      <div className="text-sm text-muted-foreground mb-4">
        {t('totalRules', { count: rules.length })} · {enabledCount} {t('enabled')}
        {searchQuery && ` · ${t('searchResults', { count: filteredRules.length })}`}
      </div>

      {testOpen && <RiskRulesTestPanel />}
      {hitsOpen && <RiskRulesHitsPanel />}

      {editingRule && (
        <RiskRuleEditor
          rule={editingRule}
          isCreating={isCreating}
          onChange={setEditingRule}
          onSave={handleSave}
          onCancel={closeEditor}
        />
      )}

      {/* Rules List */}
      {loading ? (
        <div className="flex justify-center py-8">
          <IconLoader className="w-6 h-6 animate-spin" />
        </div>
      ) : filteredRules.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">
          {searchQuery ? t('searchNoResults') : t('noRules')}
        </div>
      ) : (
        <div className="space-y-2">
          {filteredRules.map((rule) => (
            <RiskRuleRow
              key={rule.rule_id}
              rule={rule}
              name={getRuleName(rule)}
              description={getRuleDesc(rule)}
              onToggle={handleToggle}
              onEdit={handleEdit}
              onDuplicate={handleDuplicate}
              onDelete={setDeleteTarget}
            />
          ))}
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) {
            setDeleteTarget(null);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('deleteRule')}</AlertDialogTitle>
            <AlertDialogDescription>{t('deleteConfirm')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete}>{t('deleteRule')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </SettingsSection>
  );
}

export default memo(RiskRulesSection);
