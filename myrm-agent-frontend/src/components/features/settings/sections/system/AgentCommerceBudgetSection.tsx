'use client';

/**
 * [INPUT]
 * @/services/commerceBudget::getCommerceBudgetStatus, updateCommerceBudgetConfig, setEmergencySpendingFreeze, getSpendingLedger
 * lucide-react::ShieldCheck, AlertOctagon, Save, Plus, Trash2, Lock, Unlock, History, CheckCircle2, Clock
 *
 * [OUTPUT]
 * AgentCommerceBudgetSection: 智能体自主微支付与白名单消费保险箱设置面板
 *
 * [POS]
 * System settings section for autonomous agent spending limits, emergency freezes, and ledger inspection.
 */

import React, { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  ShieldCheck,
  AlertOctagon,
  Save,
  Plus,
  Trash2,
  Lock,
  Unlock,
  History,
  CheckCircle2,
  Clock,
} from 'lucide-react';
import SettingsSection from '../SettingsSection';
import { cn } from '@/lib/utils/classnameUtils';
import { SpendReceiptBadge } from '@/components/features/commerce/SpendReceiptBadge';
import {
  getCommerceBudgetStatus,
  updateCommerceBudgetConfig,
  setEmergencySpendingFreeze,
  getSpendingLedger,
  type CommerceBudgetStatus,
  type SpendingLedgerEntry,
} from '@/services/commerceBudget';

export const AgentCommerceBudgetSection = memo(() => {
  const t = useTranslations('settings.commerceBudget');
  const [status, setStatus] = useState<CommerceBudgetStatus | null>(null);
  const [ledger, setLedger] = useState<SpendingLedgerEntry[]>([]);
  const [dailyCapUsd, setDailyCapUsd] = useState<string>('10.00');
  const [perActionCapUsd, setPerActionCapUsd] = useState<string>('2.00');
  const [merchants, setMerchants] = useState<string[]>([]);
  const [newMerchant, setNewMerchant] = useState<string>('');
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [saveSuccess, setSaveSuccess] = useState<boolean>(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [s, l] = await Promise.all([
        getCommerceBudgetStatus(),
        getSpendingLedger({ limit: 10 }).catch(() => []),
      ]);
      setStatus(s);
      setLedger(l);
      setDailyCapUsd((s.daily_cap_cents / 100).toFixed(2));
      setPerActionCapUsd((s.per_action_cap_cents / 100).toFixed(2));
      setMerchants(s.allowed_merchants);
    } catch {
      // Keep existing state on load failure
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleToggleFreeze = async () => {
    if (!status) {
      return;
    }
    try {
      const nextStatus = await setEmergencySpendingFreeze(!status.is_frozen);
      setStatus(nextStatus);
    } catch {
      // Toggle failure handled silently
    }
  };

  const handleAddMerchant = () => {
    const trimmed = newMerchant.trim().toLowerCase();
    if (trimmed && !merchants.includes(trimmed)) {
      setMerchants([...merchants, trimmed]);
      setNewMerchant('');
    }
  };

  const handleRemoveMerchant = (domain: string) => {
    setMerchants(merchants.filter((m) => m !== domain));
  };

  const handleSaveConfig = async () => {
    setIsSaving(true);
    setSaveSuccess(false);
    try {
      const dailyCents = Math.round(parseFloat(dailyCapUsd) * 100) || 1000;
      const perActionCents = Math.round(parseFloat(perActionCapUsd) * 100) || 200;
      const nextStatus = await updateCommerceBudgetConfig({
        daily_cap_cents: Math.max(10, dailyCents),
        per_action_cap_cents: Math.max(10, perActionCents),
        allowed_merchants: merchants,
      });
      setStatus(nextStatus);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } finally {
      setIsSaving(false);
    }
  };

  const spentRatio = status
    ? Math.min(
        100,
        Math.round(
          ((status.daily_spent_cents + status.active_reserved_cents) /
            Math.max(1, status.daily_cap_cents)) *
            100
        )
      )
    : 0;

  return (
    <SettingsSection
      id="agent-commerce-budget"
      title={
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-emerald-500" />
          <span>{t('title')}</span>
        </div>
      }
      description={t('description')}
      action={
        <button
          onClick={handleToggleFreeze}
          disabled={!status}
          className={cn(
            'inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all cursor-pointer',
            status?.is_frozen
              ? 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/30 hover:bg-red-500/20'
              : 'bg-secondary text-foreground border-border hover:bg-accent'
          )}
        >
          {status?.is_frozen ? (
            <>
              <Lock className="w-3.5 h-3.5 text-red-500" />
              <span>{t('frozenStatus')}</span>
            </>
          ) : (
            <>
              <Unlock className="w-3.5 h-3.5 text-emerald-500" />
              <span>{t('emergencyFreeze')}</span>
            </>
          )}
        </button>
      }
    >
      {/* Spend Progress Bar */}
      <div className="space-y-2 p-4 rounded-xl bg-card border border-border/50">
        <div className="flex justify-between items-center text-xs font-medium">
          <span className="text-muted-foreground">{t('todaySpent')}</span>
          <span className="font-semibold text-foreground">
            ${((status?.daily_spent_cents || 0) / 100).toFixed(2)} / $
            {((status?.daily_cap_cents || 1000) / 100).toFixed(2)} ({spentRatio}%)
          </span>
        </div>
        <div className="w-full h-2 rounded-full bg-secondary overflow-hidden">
          <div
            className={cn(
              'h-full transition-all duration-300',
              status?.is_frozen
                ? 'bg-red-500'
                : spentRatio > 80
                  ? 'bg-amber-500'
                  : 'bg-emerald-500'
            )}
            style={{ width: `${spentRatio}%` }}
          />
        </div>
        <div className="flex justify-between items-center text-[11px] text-muted-foreground pt-1">
          <span>
            {t('activeReserved')}: $
            {((status?.active_reserved_cents || 0) / 100).toFixed(2)}
          </span>
          <span>
            {t('remainingBudget')}: $
            {((status?.remaining_cents || 0) / 100).toFixed(2)}
          </span>
        </div>
      </div>

      {/* Limit Config Fields */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-foreground">{t('dailyCap')}</label>
          <div className="relative">
            <span className="absolute left-3 top-2.5 text-xs text-muted-foreground">$</span>
            <input
              type="number"
              step="0.5"
              value={dailyCapUsd}
              onChange={(e) => setDailyCapUsd(e.target.value)}
              className="w-full pl-7 pr-3 py-2 text-sm rounded-lg bg-background border border-border focus:ring-1 focus:ring-emerald-500 outline-none"
            />
          </div>
          <p className="text-[11px] text-muted-foreground">{t('dailyCapDesc')}</p>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-foreground">
            {t('perActionCap')}
          </label>
          <div className="relative">
            <span className="absolute left-3 top-2.5 text-xs text-muted-foreground">$</span>
            <input
              type="number"
              step="0.1"
              value={perActionCapUsd}
              onChange={(e) => setPerActionCapUsd(e.target.value)}
              className="w-full pl-7 pr-3 py-2 text-sm rounded-lg bg-background border border-border focus:ring-1 focus:ring-emerald-500 outline-none"
            />
          </div>
          <p className="text-[11px] text-muted-foreground">{t('perActionCapDesc')}</p>
        </div>
      </div>

      {/* Allowed Merchants Whitelist */}
      <div className="space-y-3">
        <div>
          <h3 className="text-xs font-semibold text-foreground">
            {t('allowedMerchants')}
          </h3>
          <p className="text-[11px] text-muted-foreground">
            {t('allowedMerchantsDesc')}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {merchants.map((domain) => (
            <span
              key={domain}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs bg-secondary text-foreground border border-border"
            >
              <span>{domain}</span>
              <button
                type="button"
                onClick={() => handleRemoveMerchant(domain)}
                className="text-muted-foreground hover:text-red-500 cursor-pointer"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>

        <div className="flex gap-2">
          <input
            type="text"
            placeholder={t('addMerchantPlaceholder')}
            value={newMerchant}
            onChange={(e) => setNewMerchant(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAddMerchant()}
            className="flex-1 px-3 py-1.5 text-xs rounded-lg bg-background border border-border focus:ring-1 focus:ring-emerald-500 outline-none"
          />
          <button
            type="button"
            onClick={handleAddMerchant}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-secondary hover:bg-accent text-foreground border border-border cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>{t('addMerchant')}</span>
          </button>
        </div>
      </div>

      {/* Save Button */}
      <div className="flex items-center justify-between pt-2">
        <div className="text-xs">
          {saveSuccess && (
            <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>{t('savedSuccess')}</span>
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={handleSaveConfig}
          disabled={isSaving}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-700 transition-colors cursor-pointer disabled:opacity-50"
        >
          <Save className="w-3.5 h-3.5" />
          <span>{isSaving ? '...' : t('save')}</span>
        </button>
      </div>

      {/* Spending Ledger Audit Trail */}
      <div className="space-y-3 pt-4 border-t border-border/50">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-muted-foreground" />
          <h3 className="text-xs font-semibold text-foreground">{t('ledgerTitle')}</h3>
        </div>

        {ledger.length === 0 ? (
          <p className="text-xs text-muted-foreground italic py-2">{t('noEntries')}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border/40 text-muted-foreground">
                  <th className="pb-2 font-medium">{t('merchant')}</th>
                  <th className="pb-2 font-medium">{t('amount')}</th>
                  <th className="pb-2 font-medium">{t('status')}</th>
                  <th className="pb-2 font-medium">{t('time')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/20">
                {ledger.map((item) => {
                  const isExpanded = expandedId === item.entry_id;
                  return (
                    <React.Fragment key={item.entry_id}>
                      <tr
                        onClick={() => setExpandedId(isExpanded ? null : item.entry_id)}
                        className="text-foreground hover:bg-muted/40 cursor-pointer transition-colors"
                      >
                        <td className="py-2 font-mono">{item.merchant_domain}</td>
                        <td className="py-2 font-semibold">
                          ${(item.amount_cents / 100).toFixed(2)}
                        </td>
                        <td className="py-2">
                          <SpendReceiptBadge
                            merchantDomain={item.merchant_domain}
                            amountCents={item.amount_cents}
                            currency={item.currency}
                            status={item.status}
                            hasEntryHash={Boolean(item.entry_hash)}
                          />
                        </td>
                        <td className="py-2 text-[11px] text-muted-foreground">
                          {item.created_at.slice(0, 16).replace('T', ' ')}
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr className="bg-muted/30">
                          <td colSpan={4} className="py-2 px-3 space-y-1 font-mono text-[11px] text-muted-foreground border-b border-border/20">
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-foreground">Entry Hash:</span>
                              <span className="truncate max-w-[420px] select-all">{item.entry_hash || 'Pending / N/A'}</span>
                            </div>
                            {item.idempotency_key ? (
                              <div className="flex items-center gap-2">
                                <span className="font-semibold text-foreground">Idempotency Key:</span>
                                <span className="truncate">{item.idempotency_key}</span>
                              </div>
                            ) : null}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </SettingsSection>
  );
});

AgentCommerceBudgetSection.displayName = 'AgentCommerceBudgetSection';
export default AgentCommerceBudgetSection;
