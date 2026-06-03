'use client';

import { memo, useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconPlus,
  IconTrash,
  IconEdit,
  IconShield,
  IconFlask,
  IconCopy,
  IconRefresh,
  IconLoader,
  IconCheckCircle,
  IconSearch,
  IconDownload,
  IconUpload,
} from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Switch } from '@/components/primitives/switch';
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
import SettingsSection from './SettingsSection';
import RiskRulesTestPanel from './RiskRulesTestPanel';
import RiskRulesHitsPanel from './RiskRulesHitsPanel';
import { CATEGORY_MAP, SEVERITY_COLORS, ACTION_COLORS, type RiskRule } from './risk-rules-types';

function RiskRulesSection() {
  const t = useTranslations('settings.securityPolicy.riskRules');

  const getRuleName = useCallback(
    (rule: RiskRule) => {
      const key = `rules.${rule.rule_id}.name` as Parameters<typeof t>[0];
      return t.has(key) ? t(key) : rule.display_name;
    },
    [t],
  );

  const getRuleDesc = useCallback(
    (rule: RiskRule) => {
      const key = `rules.${rule.rule_id}.desc` as Parameters<typeof t>[0];
      return t.has(key) ? t(key) : rule.description;
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

  const loadRules = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (categoryFilter !== 'all') params.set('category', categoryFilter);
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
        toast.error(t('loadError'));
      }
    },
    [t],
  );

  const handleBatchToggle = useCallback(
    async (enabled: boolean) => {
      const ids = rules.map((r) => r.rule_id);
      if (ids.length === 0) return;
      try {
        await apiRequest('/risk/rules/batch-toggle', {
          method: 'POST',
          body: JSON.stringify({ rule_ids: ids, is_enabled: enabled }),
        });
        setRules((prev) => prev.map((r) => ({ ...r, is_enabled: enabled })));
        toast.success(t('toggleSuccess'));
      } catch {
        toast.error(t('loadError'));
      }
    },
    [rules, t],
  );

  const confirmDelete = useCallback(async () => {
    if (!deleteTarget) return;
    try {
      await apiRequest(`/risk/rules/${deleteTarget}`, { method: 'DELETE' });
      setRules((prev) => prev.filter((r) => r.rule_id !== deleteTarget));
      toast.success(t('deleteSuccess'));
    } catch {
      toast.error(t('loadError'));
    } finally {
      setDeleteTarget(null);
    }
  }, [deleteTarget, t]);

  const handleSave = useCallback(async () => {
    if (!editingRule) return;
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
      setEditingRule(null);
      setIsCreating(false);
      loadRules();
    } catch {
      toast.error(t('loadError'));
    }
  }, [editingRule, isCreating, loadRules, t]);

  const handleExport = useCallback(() => {
    const customRules = rules.filter((r) => !r.is_builtin);
    if (customRules.length === 0) {
      toast.error(t('noCustomRulesToExport'));
      return;
    }
    const exportData = customRules.map(
      ({ rule_id, display_name, description, pattern, severity, action, category, sort_order }) => ({
        rule_id,
        display_name,
        description,
        pattern,
        severity,
        action,
        category,
        sort_order,
      }),
    );
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `risk-rules-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [rules, t]);

  const handleImport = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      try {
        const text = await file.text();
        const parsed = JSON.parse(text) as Array<Record<string, unknown>>;
        if (!Array.isArray(parsed)) throw new Error('Invalid format');
        const validRules = parsed.filter((r) => r.rule_id && r.pattern);
        if (validRules.length === 0) {
          toast.error(t('importError'));
          return;
        }
        const result = await apiRequest<{ imported: number; skipped: string[] }>('/risk/rules/batch-import', {
          method: 'POST',
          body: JSON.stringify({ rules: validRules }),
        });
        toast.success(t('importSuccess', { count: result.imported }));
        loadRules();
      } catch {
        toast.error(t('importError'));
      }
    };
    input.click();
  }, [loadRules, t]);

  const filteredRules = useMemo(() => {
    if (!searchQuery.trim()) return rules;
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
            setEditingRule({
              rule_id: '',
              display_name: '',
              pattern: '',
              severity: 'medium',
              action: 'block',
              category: 'custom',
              description: '',
              sort_order: 0,
            });
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

      {/* Edit/Create Form */}
      {editingRule && (
        <div className="border border-primary/30 rounded-lg p-4 mb-4 space-y-3 bg-card">
          <h3 className="font-medium text-sm">{isCreating ? t('createRule') : t('editRule')}</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input
              placeholder={t('ruleId')}
              value={editingRule.rule_id || ''}
              onChange={(e) => setEditingRule({ ...editingRule, rule_id: e.target.value })}
              disabled={!isCreating}
            />
            <Input
              placeholder={t('displayName')}
              value={editingRule.display_name || ''}
              onChange={(e) => setEditingRule({ ...editingRule, display_name: e.target.value })}
            />
          </div>
          <Input
            placeholder={t('pattern')}
            value={editingRule.pattern || ''}
            onChange={(e) => setEditingRule({ ...editingRule, pattern: e.target.value })}
            className="font-mono text-sm"
            disabled={!isCreating && editingRule.is_builtin === true}
          />
          {!isCreating && editingRule.is_builtin && (
            <p className="text-xs text-muted-foreground">{t('builtinCannotEditPattern')}</p>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Select
              value={editingRule.severity || 'medium'}
              onValueChange={(v) => setEditingRule({ ...editingRule, severity: v })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="low">{t('severityLow')}</SelectItem>
                <SelectItem value="medium">{t('severityMedium')}</SelectItem>
                <SelectItem value="high">{t('severityHigh')}</SelectItem>
              </SelectContent>
            </Select>
            <Select
              value={editingRule.action || 'block'}
              onValueChange={(v) => setEditingRule({ ...editingRule, action: v })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="allow">{t('actionAllow')}</SelectItem>
                <SelectItem value="block">{t('actionBlock')}</SelectItem>
              </SelectContent>
            </Select>
            <Select
              value={editingRule.category || 'custom'}
              onValueChange={(v) => setEditingRule({ ...editingRule, category: v })}
            >
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
            <Button size="sm" onClick={handleSave}>
              {t('saveRule')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setEditingRule(null);
                setIsCreating(false);
              }}
            >
              {t('cancel')}
            </Button>
          </div>
        </div>
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
            <div
              key={rule.rule_id}
              className="flex items-center gap-3 p-3 border border-border rounded-lg hover:bg-accent/50 transition-colors"
            >
              <Switch checked={rule.is_enabled} onCheckedChange={(checked) => handleToggle(rule.rule_id, checked)} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm truncate">{getRuleName(rule)}</span>
                  {rule.is_builtin && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-600 dark:text-blue-400 font-medium">
                      {t('builtin')}
                    </span>
                  )}
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${SEVERITY_COLORS[rule.severity] || ''}`}
                  >
                    {t(
                      `severity${rule.severity.charAt(0).toUpperCase() + rule.severity.slice(1)}` as
                        | 'severityLow'
                        | 'severityMedium'
                        | 'severityHigh',
                    )}
                  </span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${ACTION_COLORS[rule.action] || ''}`}>
                    {t(
                      `action${rule.action.charAt(0).toUpperCase() + rule.action.slice(1)}` as
                        | 'actionAllow'
                        | 'actionBlock',
                    )}
                  </span>
                  <span className="text-[10px] text-muted-foreground">
                    {t(CATEGORY_MAP[rule.category] || 'categoryCustom')}
                  </span>
                </div>
                {(rule.description || getRuleDesc(rule)) && (
                  <p className="text-xs text-muted-foreground mt-0.5 truncate">{getRuleDesc(rule)}</p>
                )}
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0"
                  onClick={() => {
                    setEditingRule({ ...rule });
                    setIsCreating(false);
                  }}
                >
                  <IconEdit className="w-3.5 h-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0"
                  title={t('duplicateRule')}
                  onClick={() => {
                    setEditingRule({
                      rule_id: `${rule.rule_id}_copy`,
                      display_name: `${getRuleName(rule)} (Copy)`,
                      pattern: rule.pattern,
                      severity: rule.severity,
                      action: rule.action,
                      category: rule.category,
                      description: rule.description,
                      sort_order: rule.sort_order,
                    });
                    setIsCreating(true);
                  }}
                >
                  <IconCopy className="w-3.5 h-3.5" />
                </Button>
                {!rule.is_builtin && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0 text-destructive"
                    onClick={() => setDeleteTarget(rule.rule_id)}
                  >
                    <IconTrash className="w-3.5 h-3.5" />
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
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
