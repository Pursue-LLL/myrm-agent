'use client';
/* oxlint-disable jsx-a11y/prefer-tag-over-role */

/**
 * RuntimeConsoleDrawer Component.
 * Pure functional multi-surface run projection drawer.
 * Implements MateClaw parity: UI = Project(RunState, Events).
 * Supports Quad-Surface switching and Attempt level diagnostics with zero emojis.
 */

import React from 'react';
import { useTranslations } from 'next-intl';
import {
  Activity,
  CheckCircle,
  FileText,
  Lock,
  MessageSquare,
  PackageCheck,
  Shield,
  ShieldAlert,
  Terminal,
  X,
  Zap,
} from 'lucide-react';
import { SurfaceViewType } from './runtimeProjectionTypes';
import { useRunProjection } from './useRunProjection';
import { QuadSurfaceSwitcher } from './QuadSurfaceSwitcher';
import { AttemptWaterfallInspector } from './AttemptWaterfallInspector';

interface RuntimeConsoleDrawerProps {
  runId: string;
  isOpen: boolean;
  onClose: () => void;
  initialSurface?: SurfaceViewType;
}

export const RuntimeConsoleDrawer: React.FC<RuntimeConsoleDrawerProps> = ({
  runId,
  isOpen,
  onClose,
  initialSurface = 'runtime_console',
}) => {
  // Safe translation fallback
  let t = (key: string): string => key;
  try {
    const translator = useTranslations('runtimeConsole');
    t = (key: string) => translator(key);
  } catch {
    // Fallback in tests
  }

  const { snapshot, activeSurface, setSurface, isLoading } = useRunProjection(
    runId,
    initialSurface,
    isOpen
  );

  if (!isOpen) {
    return null;
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Runtime Console and State Projection Drawer"
      className="fixed inset-y-0 right-0 z-50 flex w-full max-w-2xl flex-col bg-slate-950 text-slate-100 shadow-2xl border-l border-slate-800 font-sans backdrop-blur-xl"
    >
      {/* Header */}
      <header className="flex h-16 items-center justify-between border-b border-slate-800 px-6 bg-slate-900/60">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 shrink-0">
            <Terminal className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-slate-100 truncate">
                {snapshot?.title || 'Runtime Execution State'}
              </h2>
              <span className="flex items-center gap-1 rounded bg-indigo-950/60 border border-indigo-700/50 px-1.5 py-0.5 text-[10px] text-indigo-300 font-mono">
                <Shield className="h-2.5 w-2.5" />
                MateClaw Parity
              </span>
            </div>
            <p className="text-xs text-slate-400 truncate">
              {t('mateclawParity')}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={onClose}
          aria-label={t('closeDrawer')}
          className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      {/* Surface Switcher Bar */}
      <div className="border-b border-slate-800 bg-slate-900/30 px-6 py-2.5 flex items-center justify-between">
        <QuadSurfaceSwitcher
          activeSurface={activeSurface}
          onSwitch={(surface) => {
            void setSurface(surface);
          }}
        />
        {snapshot?.status ? (
          <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-slate-800 text-indigo-300 border border-slate-700">
            Status: {snapshot.status}
          </span>
        ) : null}
      </div>

      {/* Main Surface Viewport (Pure Functional Projection) */}
      <main className="flex-1 overflow-y-auto p-6 space-y-4">
        {isLoading && !snapshot ? (
          <div className="flex h-48 items-center justify-center text-xs text-slate-400">
            Loading Run projection state...
          </div>
        ) : null}

        {/* 1. Runtime Console View */}
        {activeSurface === 'runtime_console' && snapshot ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Activity className="h-3.5 w-3.5 text-indigo-400" />
                <span>{t('attemptInspector.title')}</span>
              </h3>
              <span className="text-xs font-mono text-slate-400">
                Current Attempt: #{snapshot.current_attempt}
              </span>
            </div>
            <AttemptWaterfallInspector attempts={snapshot.attempts} />
          </div>
        ) : null}

        {/* 2. Deliverables Board View */}
        {activeSurface === 'deliverables' && snapshot ? (
          <div className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <PackageCheck className="h-3.5 w-3.5 text-emerald-400" />
              <span>{t('deliverablesSection.title')}</span>
            </h3>
            {snapshot.deliverables.length === 0 ? (
              <div className="p-6 text-center text-xs text-slate-400 bg-slate-900/30 rounded-lg border border-slate-800">
                {t('deliverablesSection.noDeliverables')}
              </div>
            ) : (
              snapshot.deliverables.map((item) => (
                <div
                  key={item.deliverable_id}
                  className="flex items-center justify-between p-3 rounded-lg bg-slate-900/40 border border-slate-800 hover:border-slate-700 transition-colors"
                >
                  <div className="flex items-center gap-2.5">
                    <FileText className="h-4 w-4 text-emerald-400 shrink-0" />
                    <div>
                      <div className="text-xs font-medium text-slate-200">{item.title}</div>
                      <div className="text-[10px] font-mono text-slate-400">{item.path_or_uri}</div>
                    </div>
                  </div>
                  <span className="flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                    <CheckCircle className="h-3 w-3" />
                    {item.status}
                  </span>
                </div>
              ))
            )}
          </div>
        ) : null}

        {/* 3. Audit Ledger View */}
        {activeSurface === 'audit' && snapshot ? (
          <div className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <ShieldAlert className="h-3.5 w-3.5 text-amber-400" />
              <span>{t('auditSection.title')}</span>
            </h3>
            {snapshot.audit_entries.length === 0 ? (
              <div className="p-6 text-center text-xs text-slate-400 bg-slate-900/30 rounded-lg border border-slate-800">
                {t('auditSection.noAudit')}
              </div>
            ) : (
              snapshot.audit_entries.map((entry) => (
                <div
                  key={entry.audit_id}
                  className="flex items-center justify-between p-3 rounded-lg bg-slate-900/40 border border-slate-800"
                >
                  <div className="flex items-center gap-2.5">
                    <Lock className="h-4 w-4 text-amber-400 shrink-0" />
                    <div>
                      <div className="text-xs font-medium text-slate-200">{entry.action}</div>
                      <div className="text-[10px] text-slate-400">Actor: {entry.actor}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 font-mono text-[10px]">
                    <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                      Risk: {entry.risk_level}
                    </span>
                    <span className="px-1.5 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800">
                      {entry.decision}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        ) : null}

        {/* 4. Chat View Projection */}
        {activeSurface === 'chat' && snapshot ? (
          <div className="p-6 rounded-lg bg-slate-900/40 border border-slate-800 text-center space-y-2">
            <MessageSquare className="h-8 w-8 text-indigo-400 mx-auto" />
            <h4 className="text-xs font-semibold text-slate-200">
              Interactive Dialogue Surface
            </h4>
            <p className="text-xs text-slate-400 max-w-sm mx-auto">
              Current Run state is actively projected into the Chat conversational stream. Switch surfaces anytime to inspect raw execution watermarks.
            </p>
          </div>
        ) : null}
      </main>

      {/* Footer Telemetry Watermark */}
      {snapshot ? (
        <footer className="flex items-center justify-between border-t border-slate-800 bg-slate-900/60 px-6 py-3 text-xs font-mono text-slate-400">
          <div className="flex items-center gap-4">
            <div>
              <span className="text-slate-400">{t('tokensTotal')}: </span>
              <span className="font-semibold text-slate-200">{snapshot.total_tokens}</span>
            </div>
            {snapshot.avg_tokens_per_sec > 0 ? (
              <div className="flex items-center gap-1 text-indigo-400">
                <Zap className="h-3.5 w-3.5" />
                <span>
                  {t('avgThroughput')}: {snapshot.avg_tokens_per_sec.toFixed(1)} tok/s
                </span>
              </div>
            ) : null}
          </div>
          <div>Run ID: {snapshot.run_id}</div>
        </footer>
      ) : null}
    </div>
  );
};
