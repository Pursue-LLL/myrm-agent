'use client';

/**
 * Assembler Sandbox Dry-Run Playground Component.
 *
 * [INPUT] blueprint: AssemblyBlueprint, onDryRun: (prompt: string) => Promise<SandboxDryRunResult | null>
 * [OUTPUT] AssemblerDryRunPlayground: In-situ sandbox execution tester with predicted tool calls & resolved prompt preview.
 * [POS] src/components/features/agent-assembler/AssemblerDryRunPlayground.tsx
 */

import { memo, useState } from 'react';
import {
  Play,
  Terminal,
  Loader2,
  CheckCircle2,
  Clock,
  Coins,
  Wrench,
  FileCode2,
  ChevronDown,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { AssemblyBlueprint, SandboxDryRunResult } from './assemblerTypes';

export interface AssemblerDryRunPlaygroundProps {
  blueprint: AssemblyBlueprint;
  onDryRun: (prompt: string) => Promise<SandboxDryRunResult | null>;
  className?: string;
}

export const AssemblerDryRunPlayground = memo(function AssemblerDryRunPlayground({
  blueprint,
  onDryRun,
  className,
}: AssemblerDryRunPlaygroundProps) {
  const t = useTranslations('agentAssembler');
  const [prompt, setPrompt] = useState('Analyze repository security policies and list tools.');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SandboxDryRunResult | null>(null);
  const [showResolvedPrompt, setShowResolvedPrompt] = useState(false);

  const handleExecute = async () => {
    if (!prompt.trim() || loading) {
      return;
    }
    setLoading(true);
    try {
      const res = await onDryRun(prompt);
      setResult(res);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className={cn(
        'flex flex-col h-full rounded-xl border border-border bg-card/60 backdrop-blur-sm overflow-hidden',
        className,
      )}
      data-testid="assembler-dry-run-playground"
    >
      {/* Header */}
      <div className="p-3 border-b border-border/60 bg-muted/20 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-primary" />
          <span className="font-semibold text-xs text-foreground">
            {t('playgroundTitle') || 'Sandbox Testbed & Dry-Run'}
          </span>
        </div>
        <span className="text-[10px] text-muted-foreground font-mono">
          {blueprint.name || 'Current Blueprint'}
        </span>
      </div>

      {/* Input Form */}
      <div className="p-3 border-b border-border/40 bg-muted/10 flex flex-col gap-2">
        <label className="text-[11px] font-medium text-muted-foreground">
          {t('testPromptLabel') || 'Test Instruction Prompt'}
        </label>
        <textarea
          rows={3}
          value={prompt}
          onChange={(e) => {
            setPrompt(e.target.value);
          }}
          placeholder={t('testPromptPlaceholder') || 'Enter a test instruction to observe assembled agent decisions...'}
          className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-border/80 bg-background/80 focus:outline-none focus:ring-1 focus:ring-primary/50 text-foreground placeholder:text-muted-foreground resize-none leading-relaxed"
        />

        <div className="flex items-center justify-end">
          <button
            type="button"
            onClick={handleExecute}
            disabled={loading || !prompt.trim()}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all shadow-xs select-none',
              loading || !prompt.trim()
                ? 'bg-muted text-muted-foreground cursor-not-allowed'
                : 'bg-primary text-primary-foreground hover:opacity-90 active:scale-95',
            )}
          >
            {loading ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>{t('simulating') || 'Simulating...'}</span>
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5 fill-current" />
                <span>{t('runDryRun') || 'Run Dry-Run'}</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Execution Results View */}
      <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-3">
        {result ? (
          <>
            {/* Stats Badge Bar */}
            <div className="flex items-center gap-3 p-2 rounded-lg bg-muted/30 border border-border/60 text-[11px] font-mono">
              <div className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 className="h-3.5 w-3.5" />
                <span>Ready</span>
              </div>
              <div className="flex items-center gap-1 text-muted-foreground">
                <Clock className="h-3.5 w-3.5" />
                <span>{result.latency_ms}ms</span>
              </div>
              <div className="flex items-center gap-1 text-muted-foreground">
                <Coins className="h-3.5 w-3.5" />
                <span>~{result.tokens_used} tok</span>
              </div>
            </div>

            {/* Predicted Tools */}
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <Wrench className="h-3.5 w-3.5 text-sky-500" />
                <span>{t('predictedTools') || 'Predicted Activated Tools'}</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {result.predicted_tool_calls.length > 0 ? (
                  result.predicted_tool_calls.map((tool) => (
                    <span
                      key={tool}
                      className="px-2 py-0.5 rounded-md bg-sky-500/10 border border-sky-500/20 text-sky-600 dark:text-sky-400 text-[11px] font-mono"
                    >
                      {tool}
                    </span>
                  ))
                ) : (
                  <span className="text-[11px] text-muted-foreground italic">
                    {t('noToolsTriggered') || 'No tools triggered (direct cognitive text output)'}
                  </span>
                )}
              </div>
            </div>

            {/* Simulated Response */}
            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-muted-foreground">
                {t('simulatedOutput') || 'Simulation Output'}
              </span>
              <pre className="p-2.5 rounded-lg bg-muted/40 border border-border/60 font-mono text-[11px] text-foreground leading-relaxed whitespace-pre-wrap break-words">
                {result.simulated_response}
              </pre>
            </div>

            {/* Resolved System Prompt Accordion */}
            <div className="flex flex-col rounded-lg border border-border/60 bg-muted/20 overflow-hidden">
              <button
                type="button"
                onClick={() => {
                  setShowResolvedPrompt((prev) => !prev);
                }}
                className="flex items-center justify-between p-2 text-xs font-medium text-muted-foreground hover:bg-muted/40 transition-colors"
              >
                <div className="flex items-center gap-1.5">
                  <FileCode2 className="h-3.5 w-3.5 text-purple-500" />
                  <span>{t('resolvedSystemPrompt') || 'Resolved Injected System Prompt'}</span>
                </div>
                <ChevronDown
                  className={cn(
                    'h-3.5 w-3.5 transition-transform duration-150',
                    showResolvedPrompt && 'rotate-180',
                  )}
                />
              </button>
              {showResolvedPrompt && (
                <div className="p-2.5 pt-0 border-t border-border/40 font-mono text-[10px] text-muted-foreground whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
                  {result.resolved_system_prompt}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
            <Terminal className="h-7 w-7 opacity-30 mb-2" />
            <span className="text-xs">
              {t('emptyDryRunHint') || 'Trigger a test dry-run to observe live sandbox behavior.'}
            </span>
          </div>
        )}
      </div>
    </div>
  );
});
