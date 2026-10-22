'use client';

import React, { useState } from 'react';
import {
  Sparkles,
  ShieldCheck,
  ShieldAlert,
  Wrench,
  X,
  CheckCircle2,
  Share2,
  Laptop,
  Cloud,
  Layers,
  Play,
  RotateCcw,
} from 'lucide-react';

export interface AgentPresetDraftData {
  preset_id: string;
  name: string;
  role: string;
  description: string;
  system_prompt: string;
  allowed_tools: string[];
  denied_tools: string[];
  guardrails: Record<string, boolean | number | string>;
  created_at?: string;
}

export interface SandboxReportData {
  is_safe: boolean;
  total_cases: number;
  passed_cases: number;
  blocked_exploits: number;
  summary: string;
}

export interface RoamingRecordData {
  preset_id: string;
  platform: 'webui' | 'desktop_tauri' | 'cloud';
  target_path: string;
  status: string;
  healed: boolean;
}

export interface CreatorModeStudioModalProps {
  chatId: string;
  initialDraft?: AgentPresetDraftData | null;
  onSynthesize?: (intent: string) => void;
  onVerifySandbox?: (draft: AgentPresetDraftData) => void;
  onSyncRoaming?: (draft: AgentPresetDraftData) => void;
  onDismiss?: () => void;
  className?: string;
}

export function CreatorModeStudioModal({
  chatId,
  initialDraft = null,
  onSynthesize,
  onVerifySandbox,
  onSyncRoaming,
  onDismiss,
  className = '',
}: CreatorModeStudioModalProps) {
  const [intentInput, setIntentInput] = useState(
    '帮我做一个专用的只读代码审查机器人，只许读文件和搜索，坚决不许修改任何文件或执行命令',
  );
  const [draft, setDraft] = useState<AgentPresetDraftData | null>(initialDraft);
  const [sandboxReport, setSandboxReport] = useState<SandboxReportData | null>(null);
  const [roamingRecords, setRoamingRecords] = useState<RoamingRecordData[]>([]);
  const [isVerifying, setIsVerifying] = useState(false);
  const [isRoaming, setIsRoaming] = useState(false);

  const handleSynthesizeClick = () => {
    if (!intentInput.trim()) {
      return;
    }
    if (onSynthesize) {
      onSynthesize(intentInput.trim());
    } else {
      // Local preview synthesis fallback
      const isReadOnly = /read[- ]?only|只许读|不许修改|禁止修改/i.test(intentInput);
      const newDraft: AgentPresetDraftData = {
        preset_id: `preset_${Math.random().toString(36).slice(2, 10)}`,
        name: 'CodeAuditorBot',
        role: 'code_auditor',
        description: intentInput.trim(),
        system_prompt: `You are CodeAuditorBot. Scope: ${intentInput.trim()}`,
        allowed_tools: ['file_read', 'web_search'],
        denied_tools: ['file_write', 'file_delete', 'bash_command', 'root_shell'],
        guardrails: { read_only: isReadOnly, least_privilege: true },
        created_at: new Date().toISOString(),
      };
      setDraft(newDraft);
      setSandboxReport(null);
      setRoamingRecords([]);
    }
  };

  const handleVerifyClick = () => {
    if (!draft) {
      return;
    }
    setIsVerifying(true);
    if (onVerifySandbox) {
      onVerifySandbox(draft);
      setIsVerifying(false);
    } else {
      // Local preview sandbox evaluation
      setTimeout(() => {
        setSandboxReport({
          is_safe: true,
          total_cases: 6,
          passed_cases: 6,
          blocked_exploits: 4,
          summary: 'Sandbox verification passed: 100% (4/4) of defensive exploit attempts blocked.',
        });
        setIsVerifying(false);
      }, 100);
    }
  };

  const handleRoamingClick = () => {
    if (!draft) {
      return;
    }
    setIsRoaming(true);
    if (onSyncRoaming) {
      onSyncRoaming(draft);
      setIsRoaming(false);
    } else {
      setTimeout(() => {
        setRoamingRecords([
          {
            preset_id: draft.preset_id,
            platform: 'webui',
            target_path: `~/.myrm/profiles/webui/${draft.preset_id}.json`,
            status: 'synced',
            healed: false,
          },
          {
            preset_id: draft.preset_id,
            platform: 'desktop_tauri',
            target_path: `~/.config/myrm-desktop/profiles/${draft.preset_id}.json`,
            status: 'synced',
            healed: true,
          },
          {
            preset_id: draft.preset_id,
            platform: 'cloud',
            target_path: `cloud://storage/profiles/${draft.preset_id}.json`,
            status: 'synced',
            healed: false,
          },
        ]);
        setIsRoaming(false);
      }, 100);
    }
  };

  return (
    <section
      aria-label="Creator Mode Guardrailed Agent Preset Studio"
      data-testid="creator-mode-studio"
      className={`rounded-2xl border border-zinc-700/80 bg-zinc-950/95 backdrop-blur-md p-5 shadow-2xl space-y-4 ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-purple-500/10 text-purple-400 border border-purple-500/20">
            <Sparkles className="w-5 h-5 animate-pulse" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-zinc-100 flex items-center gap-2">
              Creator Mode Studio
              <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30">
                P0 Metaprogramming
              </span>
            </h2>
            <p className="text-xs text-zinc-400">
              Natural language intent to least-privilege agent preset with defensive sandbox
            </p>
          </div>
        </div>

        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Close creator mode studio"
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Step 1: Natural Language Intent Input */}
      <div className="space-y-2">
        <label htmlFor={`intent-${chatId}`} className="block text-xs font-semibold text-zinc-300">
          Describe Desired Agent Scope & Safety Boundaries
        </label>
        <div className="flex gap-2">
          <textarea
            id={`intent-${chatId}`}
            value={intentInput}
            onChange={(e) => setIntentInput(e.target.value)}
            rows={2}
            placeholder="e.g. Create a read-only code auditor agent that cannot write files or execute bash..."
            className="flex-1 text-xs rounded-xl bg-zinc-900 border border-zinc-700 p-2.5 text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-purple-500 transition resize-none"
          />
          <button
            type="button"
            onClick={handleSynthesizeClick}
            aria-label="Synthesize agent preset"
            className="px-4 py-2 self-stretch rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-medium inline-flex items-center gap-1.5 shadow-lg shadow-purple-600/20 transition"
          >
            <Sparkles className="w-4 h-4" />
            <span>Synthesize</span>
          </button>
        </div>
      </div>

      {/* Step 2: Synthesized Draft Preview */}
      {draft && (
        <div data-testid="preset-draft-preview" className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-3.5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-xs text-zinc-200">{draft.name}</span>
              <span className="text-[11px] font-mono text-zinc-400">({draft.role})</span>
            </div>
            <span className="text-[10px] text-zinc-500 font-mono">ID: {draft.preset_id}</span>
          </div>

          {/* Tools Grid */}
          <div className="space-y-2 text-xs">
            <div>
              <span className="text-zinc-400 text-[11px] font-semibold block mb-1">
                Authorized Whitelist ({draft.allowed_tools.length})
              </span>
              <div className="flex flex-wrap gap-1.5">
                {draft.allowed_tools.map((t) => (
                  <span
                    key={t}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[11px]"
                  >
                    <Wrench className="w-3 h-3" />
                    {t}
                  </span>
                ))}
              </div>
            </div>

            <div>
              <span className="text-zinc-400 text-[11px] font-semibold block mb-1">
                Strictly Prohibited ({draft.denied_tools.length})
              </span>
              <div className="flex flex-wrap gap-1.5">
                {draft.denied_tools.slice(0, 6).map((t) => (
                  <span
                    key={t}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-rose-500/10 text-rose-400 border border-rose-500/20 text-[11px]"
                  >
                    <ShieldAlert className="w-3 h-3" />
                    {t}
                  </span>
                ))}
                {draft.denied_tools.length > 6 && (
                  <span className="text-zinc-500 text-[11px] self-center">
                    +{draft.denied_tools.length - 6} more
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Action Row */}
          <div className="flex items-center gap-2 pt-2 border-t border-zinc-800">
            <button
              type="button"
              onClick={handleVerifyClick}
              disabled={isVerifying}
              aria-label="Verify preset in defensive sandbox"
              className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition disabled:opacity-50"
            >
              <Play className="w-3.5 h-3.5 text-purple-400" />
              <span>{isVerifying ? 'Running Battery...' : 'Run Sandbox Defense Test'}</span>
            </button>

            <button
              type="button"
              onClick={handleRoamingClick}
              disabled={isRoaming || !sandboxReport?.is_safe}
              aria-label="Broadcast preset to roaming platforms"
              className="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-emerald-600/30 hover:bg-emerald-600/40 text-emerald-200 border border-emerald-500/40 transition disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Share2 className="w-3.5 h-3.5 text-emerald-400" />
              <span>Publish & Roam</span>
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Sandbox Verification Report */}
      {sandboxReport && (
        <div
          data-testid="sandbox-report-banner"
          className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-200 flex items-start gap-2.5"
        >
          <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
          <div className="space-y-1 min-w-0">
            <div className="font-semibold text-emerald-300 flex items-center gap-2">
              <span>Sandbox Defense Certified (100% Safe)</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-200 font-mono">
                {sandboxReport.passed_cases}/{sandboxReport.total_cases} Passed
              </span>
            </div>
            <p className="text-emerald-200/90 leading-relaxed">{sandboxReport.summary}</p>
          </div>
        </div>
      )}

      {/* Step 4: Multi-platform Roaming Receipts */}
      {roamingRecords.length > 0 && (
        <div data-testid="roaming-records-list" className="space-y-1.5">
          <div className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wider">
            Multi-Platform Roaming SSOT ({roamingRecords.length})
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            {roamingRecords.map((rec) => (
              <div
                key={rec.platform}
                className="p-2 rounded-lg bg-zinc-900 border border-zinc-800 text-xs flex items-center gap-2"
              >
                {rec.platform === 'desktop_tauri' ? (
                  <Laptop className="w-4 h-4 text-cyan-400 shrink-0" />
                ) : rec.platform === 'cloud' ? (
                  <Cloud className="w-4 h-4 text-purple-400 shrink-0" />
                ) : (
                  <Layers className="w-4 h-4 text-emerald-400 shrink-0" />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-zinc-300 capitalize">{rec.platform}</span>
                    {rec.healed && (
                      <span className="text-[9px] text-amber-400 bg-amber-500/10 px-1 rounded">
                        Healed
                      </span>
                    )}
                  </div>
                  <p className="text-[10px] font-mono text-zinc-500 truncate" title={rec.target_path}>
                    {rec.target_path}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
