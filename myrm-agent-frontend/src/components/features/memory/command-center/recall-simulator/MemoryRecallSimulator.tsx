'use client';
/* oxlint-disable jsx-a11y/prefer-tag-over-role */

/**
 * MemoryRecallSimulator Component.
 * Interactive memory recall sandbox and secondary governance playground.
 * Benchmarking EvoX Darwinian Agent memory recall testing and in-place governance.
 * Zero-emoji compliant.
 */

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Activity,
  AlertTriangle,
  BrainCircuit,
  Clock,
  Compass,
  Database,
  Filter,
  Layers,
  Search,
  Sparkles,
  X,
} from 'lucide-react';
import { RecallCandidate, RecallSimulateResponse } from './recallSimulatorTypes';
import { RecallSimulatorService } from './recallSimulatorService';
import { MemorySecondaryGovernanceToolbar } from './MemorySecondaryGovernanceToolbar';

interface MemoryRecallSimulatorProps {
  isOpen: boolean;
  onClose: () => void;
  initialQuery?: string;
}

export const MemoryRecallSimulator: React.FC<MemoryRecallSimulatorProps> = ({
  isOpen,
  onClose,
  initialQuery = '排查 Linux 内核死锁与自旋锁',
}) => {
  let t = (key: string): string => key;
  try {
    const translation = useTranslations('memoryRecall');
    t = (key: string): string => translation(key);
  } catch {
    // Fallback in test suites
  }

  const [query, setQuery] = useState<string>(initialQuery);
  const [domainFilter, setDomainFilter] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [result, setResult] = useState<RecallSimulateResponse | null>(null);

  const handleSimulate = async (): Promise<void> => {
    if (!query.trim()) {
      return;
    }

    setIsLoading(true);
    try {
      const data = await RecallSimulatorService.simulateRecall({
        query: query.trim(),
        top_k: 5,
        domain_filter: domainFilter.trim() || null,
        recall_types: ['bm25', 'vector', 'causal_gene'],
      });
      setResult(data);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCandidateGovernanceUpdate = async (
    candidateId: string,
    updated: Partial<RecallCandidate>,
    mergedIntoId?: string
  ): Promise<void> => {
    await RecallSimulatorService.updateGovernance({
      memory_id: candidateId,
      confidence: updated.confidence,
      is_negative_trap: updated.is_negative_trap,
      status: updated.status,
      merged_into_id: mergedIntoId,
    });

    if (result) {
      setResult({
        ...result,
        candidates: result.candidates.map((c) => {
          if (c.memory_id === candidateId) {
            return {
              ...c,
              ...updated,
            };
          }
          return c;
        }),
      });
    }
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="recall-simulator-title"
      className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm"
    >
      <div className="relative w-full max-w-3xl h-full bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col overflow-hidden animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400">
              <BrainCircuit className="w-5 h-5" />
            </div>
            <div>
              <h2 id="recall-simulator-title" className="text-base font-semibold text-slate-100 flex items-center gap-2">
                <span>{t('drawerTitle')}</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 font-medium">
                  EvoX Darwinian
                </span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">{t('drawerSubtitle')}</p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Query Input Sandbox */}
        <div className="p-6 border-b border-slate-800 bg-slate-950/30 space-y-3">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    handleSimulate();
                  }
                }}
                placeholder={t('queryInputPlaceholder')}
                className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all font-sans"
              />
            </div>

            <div className="relative w-36 hidden sm:block">
              <Filter className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                value={domainFilter}
                onChange={(e) => {
                  setDomainFilter(e.target.value);
                }}
                placeholder="Domain Tag"
                className="w-full pl-8 pr-3 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-300 placeholder-slate-500 focus:outline-none focus:border-indigo-500 text-[11px]"
              />
            </div>

            <button
              type="button"
              onClick={handleSimulate}
              disabled={isLoading || !query.trim()}
              className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium shadow-lg shadow-indigo-600/20 transition-all active:scale-95 shrink-0"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>{isLoading ? t('simulatingBtn') : t('simulateBtn')}</span>
            </button>
          </div>

          {/* Quick Metrics Bar */}
          {result && (
            <div className="flex items-center gap-4 text-xs pt-1">
              <span className="flex items-center gap-1 text-slate-400">
                <Database className="w-3.5 h-3.5 text-indigo-400" />
                <span>{t('totalMatched')}:</span>
                <strong className="text-slate-200 font-mono">{result.total_matched}</strong>
              </span>

              <span className="flex items-center gap-1 text-slate-400">
                <Clock className="w-3.5 h-3.5 text-emerald-400" />
                <span>{t('latency')}:</span>
                <strong className="text-slate-200 font-mono">{result.execution_latency_ms} ms</strong>
              </span>
            </div>
          )}
        </div>

        {/* Candidate Memory Cards Stream */}
        <div className="flex-1 p-6 overflow-y-auto space-y-4 bg-slate-950/20">
          {!result ? (
            <div className="text-center py-20 text-slate-500 space-y-2">
              <Compass className="w-10 h-10 mx-auto text-slate-600" />
              <p className="text-xs">输入任意业务查询并点击「模拟召回」开始多路命中分析</p>
            </div>
          ) : result.candidates.length === 0 ? (
            <div className="text-center py-20 text-slate-500 space-y-2">
              <AlertTriangle className="w-10 h-10 mx-auto text-amber-500/50" />
              <p className="text-xs">{t('emptyResults')}</p>
            </div>
          ) : (
            result.candidates.map((cand) => (
              <div
                key={cand.memory_id}
                className={`p-4 rounded-2xl bg-slate-900 border transition-all space-y-3.5 shadow-sm ${
                  cand.is_negative_trap
                    ? 'border-rose-500/40 hover:border-rose-500/60 ring-1 ring-rose-500/20'
                    : 'border-slate-800 hover:border-slate-700'
                }`}
              >
                {/* Candidate Header */}
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-slate-100 font-mono">
                        {cand.memory_id}
                      </span>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-800 text-slate-300 border border-slate-700/80">
                        {cand.recall_type.toUpperCase()}
                      </span>
                      {cand.is_negative_trap && (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-rose-500/15 border border-rose-500/30 text-rose-300">
                          {t('mustAvoidTrap')}
                        </span>
                      )}
                    </div>
                    <p className="text-xs font-medium text-slate-200">{cand.summary}</p>
                  </div>

                  {/* RRF Score Badge */}
                  <div className="text-right shrink-0">
                    <span className="text-[10px] text-slate-400 block">{t('rrfScore')}</span>
                    <span className="font-mono font-bold text-sm text-indigo-400">
                      {(cand.scores.rrf_score * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>

                {/* Attribution & Content */}
                <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 space-y-2 text-xs">
                  <div className="flex items-center gap-1.5 text-indigo-300 text-[11px] font-medium">
                    <Sparkles className="w-3.5 h-3.5 shrink-0" />
                    <span>{cand.hit_reason}</span>
                  </div>
                  <p className="text-slate-300 leading-relaxed font-sans text-xs">
                    {cand.content}
                  </p>
                </div>

                {/* Multi-Channel Score Breakdown */}
                <div className="grid grid-cols-3 gap-2 p-2.5 rounded-xl bg-slate-950/40 border border-slate-800/60 text-[11px]">
                  <div>
                    <span className="text-slate-500 flex items-center gap-1 mb-0.5">
                      <Layers className="w-3 h-3 text-sky-400" />
                      {t('bm25Score')}
                    </span>
                    <span className="font-mono font-semibold text-slate-300">
                      {cand.scores.bm25_score.toFixed(1)}
                    </span>
                  </div>

                  <div>
                    <span className="text-slate-500 flex items-center gap-1 mb-0.5">
                      <Activity className="w-3 h-3 text-indigo-400" />
                      {t('vectorSim')}
                    </span>
                    <span className="font-mono font-semibold text-slate-300">
                      {(cand.scores.vector_similarity * 100).toFixed(1)}%
                    </span>
                  </div>

                  <div>
                    <span className="text-slate-500 flex items-center gap-1 mb-0.5">
                      <BrainCircuit className="w-3 h-3 text-purple-400" />
                      {t('causalAffinity')}
                    </span>
                    <span className="font-mono font-semibold text-slate-300">
                      {(cand.scores.causal_relevance * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>

                {/* In-Place Secondary Governance Toolbar */}
                <MemorySecondaryGovernanceToolbar
                  candidate={cand}
                  onUpdate={(updated, mergedIntoId) =>
                    handleCandidateGovernanceUpdate(cand.memory_id, updated, mergedIntoId)
                  }
                />
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
