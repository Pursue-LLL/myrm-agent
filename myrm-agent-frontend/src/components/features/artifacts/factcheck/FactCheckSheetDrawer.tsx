'use client';
/* oxlint-disable jsx-a11y/prefer-tag-over-role */

/**
 * FactCheckSheetDrawer Component.
 * Right-side drawer for placeholder data management and verified facts auditing.
 * Adheres to WorkBuddy fact verification paradigm with zero emojis.
 */

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  AlertCircle,
  Check,
  CheckCircle2,
  ExternalLink,
  ListChecks,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-react';
import {
  FactCheckDrawerTab,
  PlaceholderItem,
  VerifiedFactItem,
} from './factCheckTypes';

interface FactCheckSheetDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  placeholders: PlaceholderItem[];
  verifiedFacts: VerifiedFactItem[];
  onReplacePlaceholder: (placeholderId: string, realValue: string) => void;
  onReplaceAllAndFinalize: (replacements: Record<string, string>) => void;
  activePlaceholderId?: string;
}

export const FactCheckSheetDrawer: React.FC<FactCheckSheetDrawerProps> = ({
  isOpen,
  onClose,
  placeholders,
  verifiedFacts,
  onReplacePlaceholder,
  onReplaceAllAndFinalize,
  activePlaceholderId,
}) => {
  let t = (key: string, values?: Record<string, string | number>): string => {
    if (key === 'bannerWarning' && values?.count !== undefined) {
      return `本篇草案包含 ${values.count} 处待实测占位数据`;
    }
    return key;
  };

  try {
    const translation = useTranslations('factCheck');
    t = (key: string, values?: Record<string, string | number>): string =>
      translation(key, values);
  } catch {
    // Fallback in test suites
  }

  const [activeTab, setActiveTab] = useState<FactCheckDrawerTab>('placeholders');
  const [inputs, setInputs] = useState<Record<string, string>>({});

  const handleInputChange = (id: string, value: string): void => {
    setInputs((prev) => ({ ...prev, [id]: value }));
  };

  const handleApplySingle = (item: PlaceholderItem): void => {
    const val = inputs[item.id] || item.placeholderKey;
    if (val && val.trim()) {
      onReplacePlaceholder(item.id, val.trim());
    }
  };

  const handleApplyAll = (): void => {
    const fullReplacements: Record<string, string> = {};
    placeholders.forEach((p) => {
      const val = inputs[p.id];
      if (val && val.trim()) {
        fullReplacements[p.id] = val.trim();
      }
    });
    onReplaceAllAndFinalize(fullReplacements);
  };

  const pendingCount = placeholders.filter((p) => p.status === 'pending').length;

  if (!isOpen) {
    return null;
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="fact-check-drawer-title"
      className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm"
    >
      <div className="relative w-full max-w-lg h-full bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col overflow-hidden animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <h2 id="fact-check-drawer-title" className="text-base font-semibold text-slate-100">
                {t('drawerTitle')}
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">{t('drawerSubtitle')}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('close')}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="flex border-b border-slate-800 bg-slate-950/20 px-6">
          <button
            type="button"
            onClick={() => {
              setActiveTab('placeholders');
            }}
            className={`flex items-center gap-2 py-3 border-b-2 text-xs font-medium transition-colors mr-6 ${
              activeTab === 'placeholders'
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <AlertCircle className="w-4 h-4" />
            <span>{t('tabPlaceholders')}</span>
            {pendingCount > 0 && (
              <span className="px-1.5 py-0.2 rounded-full bg-amber-500/20 text-amber-300 text-[10px] font-mono font-bold">
                {pendingCount}
              </span>
            )}
          </button>

          <button
            type="button"
            onClick={() => {
              setActiveTab('verified');
            }}
            className={`flex items-center gap-2 py-3 border-b-2 text-xs font-medium transition-colors ${
              activeTab === 'verified'
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <CheckCircle2 className="w-4 h-4" />
            <span>{t('tabVerified')}</span>
            {verifiedFacts.length > 0 && (
              <span className="px-1.5 py-0.2 rounded-full bg-emerald-500/20 text-emerald-300 text-[10px] font-mono font-bold">
                {verifiedFacts.length}
              </span>
            )}
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {activeTab === 'placeholders' && (
            <div className="space-y-4">
              {placeholders.length === 0 ? (
                <div className="text-center py-12 text-slate-500 text-xs">
                  <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-emerald-500/60" />
                  <p>{t('emptyPending')}</p>
                </div>
              ) : (
                placeholders.map((item) => {
                  const isPending = item.status === 'pending';
                  const isTarget = item.id === activePlaceholderId;

                  return (
                    <div
                      key={item.id}
                      className={`p-4 rounded-xl border transition-all ${
                        isTarget
                          ? 'bg-indigo-950/20 border-indigo-500/60 ring-1 ring-indigo-500/30'
                          : isPending
                          ? 'bg-slate-950/40 border-slate-800'
                          : 'bg-emerald-950/10 border-emerald-900/30'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-mono text-xs font-semibold text-amber-300 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
                          {item.originalText}
                        </span>
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                            isPending
                              ? 'bg-amber-500/20 text-amber-300'
                              : 'bg-emerald-500/20 text-emerald-300'
                          }`}
                        >
                          {isPending ? t('placeholderTag') : t('applied')}
                        </span>
                      </div>

                      {/* Snippet Context */}
                      <p className="text-xs text-slate-400 bg-slate-900/80 p-2.5 rounded-lg border border-slate-800/80 font-mono text-[11px] leading-relaxed mb-3">
                        <span className="text-slate-500 block mb-0.5">
                          {t('contextLabel')}:
                        </span>
                        {item.contextSnippet}
                      </p>

                      {/* Replacement input */}
                      {isPending ? (
                        <div className="flex items-center gap-2">
                          <input
                            type="text"
                            aria-label={`Real value for ${item.placeholderKey}`}
                            placeholder={t('inputRealValuePlaceholder')}
                            value={inputs[item.id] ?? ''}
                            onChange={(e) => {
                              handleInputChange(item.id, e.target.value);
                            }}
                            className="flex-1 px-3 py-1.5 rounded-lg bg-slate-950/80 border border-slate-800 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500"
                          />
                          <button
                            type="button"
                            onClick={() => {
                              handleApplySingle(item);
                            }}
                            className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-medium text-white transition-colors"
                          >
                            {t('applyBtn')}
                          </button>
                        </div>
                      ) : (
                        <div className="text-xs text-emerald-400 flex items-center gap-1.5">
                          <Check className="w-3.5 h-3.5" />
                          <span>已替换为: {item.replacedValue}</span>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          )}

          {activeTab === 'verified' && (
            <div className="space-y-3">
              {verifiedFacts.length === 0 ? (
                <div className="text-center py-12 text-slate-500 text-xs">
                  <ListChecks className="w-8 h-8 mx-auto mb-2 text-slate-600" />
                  <p>{t('emptyVerified')}</p>
                </div>
              ) : (
                verifiedFacts.map((fact) => (
                  <div
                    key={fact.id}
                    className="p-4 rounded-xl bg-slate-950/40 border border-slate-800 space-y-2 text-xs"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="font-medium text-slate-200 leading-snug">
                        {fact.factStatement}
                      </span>
                      <span className="shrink-0 px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 text-[10px] font-medium">
                        {t('verifiedTag')}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1 border-t border-slate-800/60">
                      <span className="font-mono text-emerald-400">
                        核实值: {fact.verifiedValue}
                      </span>
                      {fact.sourceUrl ? (
                        <a
                          href={fact.sourceUrl}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="flex items-center gap-1 text-indigo-400 hover:text-indigo-300 transition-colors"
                        >
                          <span>{fact.sourceName}</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      ) : (
                        <span className="text-slate-500">{fact.sourceName}</span>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        {activeTab === 'placeholders' && pendingCount > 0 && (
          <div className="p-4 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between">
            <span className="text-xs text-slate-400">
              剩余 {pendingCount} 处待替换
            </span>
            <button
              type="button"
              onClick={handleApplyAll}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-xs font-medium text-white shadow-lg transition-all"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>{t('replaceAllBtn')}</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
