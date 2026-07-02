'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { BarChart3, Settings2 } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import SettingsSection from '../SettingsSection';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Progress } from '@/components/primitives/progress';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import {
  type OrgUsageSummary,
  type BudgetSettings,
  getOrgUsageSummary,
  getOrgBudget,
  setOrgBudget,
} from '@/services/enterprise-admin';
import { getMyOrg } from '@/services/enterprise-org';

const CATEGORY_COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4'];

const EnterpriseUsageTab = memo(() => {
  const t = useTranslations('settings.enterprise.usage');
  const [summary, setSummary] = useState<OrgUsageSummary | null>(null);
  const [budget, setBudget] = useState<BudgetSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [showBudgetDialog, setShowBudgetDialog] = useState(false);
  const [budgetInput, setBudgetInput] = useState('');
  const [thresholdInput, setThresholdInput] = useState('80');
  const [orgId, setOrgId] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const org = await getMyOrg();
      setOrgId(org.id);
      const [usageData, budgetData] = await Promise.all([
        getOrgUsageSummary(org.id),
        getOrgBudget(org.id),
      ]);
      setSummary(usageData);
      setBudget(budgetData);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to load usage data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSaveBudget = useCallback(async () => {
    if (!orgId) return;
    try {
      const budgetWu = budgetInput ? Number(budgetInput) : null;
      const threshold = Number(thresholdInput) / 100;
      const result = await setOrgBudget(orgId, budgetWu, threshold);
      setBudget(result);
      setShowBudgetDialog(false);
      toast.success(t('budgetSaved'));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to save budget');
    }
  }, [orgId, budgetInput, thresholdInput, t]);

  const usagePercent = summary?.usage_ratio != null ? Math.round(summary.usage_ratio * 100) : null;

  if (loading && !summary) {
    return (
      <SettingsSection title={t('title')} description={t('description')}>
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-muted rounded w-1/2" />
          <div className="h-48 bg-muted rounded" />
        </div>
      </SettingsSection>
    );
  }

  return (
    <div className="space-y-6">
      {/* Budget & Overview */}
      <SettingsSection
        title={
          <span className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5" />
            {t('title')}
          </span>
        }
        description={t('description')}
        action={
          <Button size="sm" variant="outline" onClick={() => {
            setBudgetInput(budget?.budget_wu_monthly != null ? String(budget.budget_wu_monthly) : '');
            setThresholdInput(budget ? String(Math.round(budget.alert_threshold * 100)) : '80');
            setShowBudgetDialog(true);
          }}>
            <Settings2 className="h-3.5 w-3.5 mr-1" />
            {t('configureBudget')}
          </Button>
        }
      >
        {summary && (
          <div className="space-y-4">
            {/* Budget Progress */}
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>{t('monthlyUsage', { month: summary.month })}</span>
                <span className="font-mono font-bold">
                  {summary.total_wu.toLocaleString()} WU
                  {summary.budget_wu_monthly != null && (
                    <span className="text-muted-foreground font-normal">
                      {' '}/ {summary.budget_wu_monthly.toLocaleString()} WU
                    </span>
                  )}
                </span>
              </div>
              {usagePercent != null && (
                <Progress
                  value={Math.min(usagePercent, 100)}
                  className={`h-3 ${usagePercent > 90 ? '[&>div]:bg-red-500' : usagePercent > 70 ? '[&>div]:bg-amber-500' : ''}`}
                />
              )}
              {usagePercent != null && usagePercent > 80 && (
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  {t('budgetWarning', { percent: usagePercent })}
                </p>
              )}
            </div>

            {/* Member Usage Ranking */}
            {summary.members.length > 0 && (
              <div>
                <div className="text-xs font-medium text-muted-foreground mb-2">{t('memberRanking')}</div>
                <div className="h-40">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={summary.members.slice(0, 10)} layout="vertical" margin={{ left: 60 }}>
                      <XAxis type="number" tick={{ fontSize: 10 }} />
                      <YAxis type="category" dataKey="display_name" tick={{ fontSize: 10 }} width={55} />
                      <Tooltip formatter={(v: number) => [`${v.toLocaleString()} WU`, 'Usage']} />
                      <Bar dataKey="wu_used" fill="#3b82f6" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* Category Distribution */}
            {summary.by_category.length > 0 && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="h-36">
                  <div className="text-xs font-medium text-muted-foreground mb-2">{t('categoryDistribution')}</div>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={summary.by_category}
                        dataKey="wu_used"
                        nameKey="category"
                        cx="50%"
                        cy="50%"
                        outerRadius={50}
                        label={({ category, percent }) => `${category} ${(percent * 100).toFixed(0)}%`}
                        labelLine={false}
                      >
                        {summary.by_category.map((_, i) => (
                          <Cell key={i} fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="space-y-1">
                  <div className="text-xs font-medium text-muted-foreground mb-2">{t('categoryBreakdown')}</div>
                  {summary.by_category.map((cat, i) => (
                    <div key={cat.category} className="flex justify-between text-xs py-1 border-b border-border/30">
                      <span className="flex items-center gap-1.5">
                        <span
                          className="w-2 h-2 rounded-full shrink-0"
                          style={{ backgroundColor: CATEGORY_COLORS[i % CATEGORY_COLORS.length] }}
                        />
                        {cat.category}
                      </span>
                      <span className="font-mono">{cat.wu_used.toLocaleString()} WU</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </SettingsSection>

      {/* Budget Dialog */}
      <Dialog open={showBudgetDialog} onOpenChange={setShowBudgetDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('configureBudget')}</DialogTitle>
            <DialogDescription>{t('budgetDialogDesc')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>{t('monthlyBudgetWu')}</Label>
              <Input
                type="number"
                value={budgetInput}
                onChange={(e) => setBudgetInput(e.target.value)}
                placeholder={t('noBudgetLimit')}
              />
            </div>
            <div className="space-y-2">
              <Label>{t('alertThreshold')}</Label>
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  min={1}
                  max={100}
                  value={thresholdInput}
                  onChange={(e) => setThresholdInput(e.target.value)}
                  className="w-20"
                />
                <span className="text-sm text-muted-foreground">%</span>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowBudgetDialog(false)}>
              {t('cancel')}
            </Button>
            <Button onClick={handleSaveBudget}>{t('save')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
});

EnterpriseUsageTab.displayName = 'EnterpriseUsageTab';

export default EnterpriseUsageTab;
