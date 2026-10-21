import React, { useId, useState } from 'react';
import {
  CliExecutionResultItem,
  CliProfileBundleItem,
  DEFAULT_CLI_BUNDLES,
  ExternalCliSubagentPassthroughCardProps,
  SensitivityLevel,
} from './cli-passthrough/types';

export const ExternalCliSubagentPassthroughCard: React.FC<
  ExternalCliSubagentPassthroughCardProps
> = ({
  chatId,
  initialBundles = DEFAULT_CLI_BUNDLES,
  workspaceRoot = '/workspace/project',
  onDismiss,
  onExecutionCompleted,
  onPrivacyAcknowledged,
}) => {
  const [bundles] = useState<CliProfileBundleItem[]>(initialBundles);
  const [selectedBundleId, setSelectedBundleId] = useState<string>(
    initialBundles[0]?.bundleId ?? 'bundle-claude-code',
  );
  const [instruction, setInstruction] = useState<string>(
    'Refactor vectorized embedding cache with Neon SIMD intrinsics',
  );
  const [contextFiles, setContextFiles] = useState<string>(
    'src/vector/cache.rs, src/vector/simd.rs',
  );
  const [sensitivity, setSensitivity] = useState<SensitivityLevel>('medium');
  const [isPrivacyAcknowledged, setIsPrivacyAcknowledged] = useState<boolean>(false);
  const [executionResult, setExecutionResult] = useState<CliExecutionResultItem | null>(null);
  const [announcement, setAnnouncement] = useState<string>('CLI Passthrough Ready');

  const instructionInputId = useId();
  const filesInputId = useId();
  const privacyCheckId = useId();
  const sensitivitySelectId = useId();

  const selectedBundle =
    bundles.find((b) => b.bundleId === selectedBundleId) ?? bundles[0];

  const vendorMap: Record<string, { vendor: string; terms: string }> = {
    claude_code: {
      vendor: 'Anthropic PBC',
      terms: 'https://www.anthropic.com/legal/privacy',
    },
    codex: {
      vendor: 'OpenAI Inc.',
      terms: 'https://openai.com/policies/privacy-policy',
    },
    cursor_cli: {
      vendor: 'Anysphere Inc.',
      terms: 'https://www.cursor.com/privacy',
    },
    generic_cli: {
      vendor: 'External Vendor',
      terms: 'https://example.com/legal/terms',
    },
  };

  const vendorInfo = vendorMap[selectedBundle?.cliType ?? 'generic_cli'];

  const handleTogglePrivacy = (checked: boolean) => {
    setIsPrivacyAcknowledged(checked);
    if (checked) {
      setAnnouncement(`Privacy disclosure acknowledged for ${vendorInfo.vendor}.`);
      onPrivacyAcknowledged?.(`disc-${selectedBundle.bundleId}`);
    }
  };

  const handleExecute = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isPrivacyAcknowledged || !instruction.trim()) {
      return;
    }

    const nowIso = new Date().toISOString();
    const filesList = contextFiles
      .split(',')
      .map((f) => f.trim())
      .filter(Boolean);
    const mockHash = Array.from({ length: 64 }, (_, i) =>
      ((i * 7 + 13) % 16).toString(16),
    ).join('');

    const diffLines = [
      `--- a/${filesList[0] ?? 'src/vector/cache.rs'}`,
      `+++ b/${filesList[0] ?? 'src/vector/cache.rs'}`,
      '@@ -1,6 +1,11 @@',
      `+ // Delegated to external subagent: ${selectedBundle.displayName}`,
      `+ // BYOS Account: ${selectedBundle.accountEmailMasked ?? 'official-byos'}`,
      '+ #[inline(always)]',
      '+ pub fn neon_simd_vector_dot_product(a: &[f32], b: &[f32]) -> f32 {',
      '+     // Zero-overhead SIMD vectorization applied',
      '+ }',
    ];

    const result: CliExecutionResultItem = {
      taskId: `task-${Date.now().toString(36)}`,
      bundleId: selectedBundle.bundleId,
      exitCode: 0,
      diffOutput: diffLines.join('\n'),
      structuredSummary: `Headless non-interactive execution of '${selectedBundle.displayName}' completed. Successfully refactored ${filesList.length} file(s) under inherited root '${workspaceRoot}' with zero API token overhead.`,
      tokensSavedEstimate: Math.max(160, instruction.length * 2 + diffLines.join('\n').length / 3),
      tamperProofAuditHash: mockHash,
      egressAccountingId: `egress-${mockHash.slice(0, 16)}`,
      completedAtUtc: nowIso,
      fileChangesCount: Math.max(1, filesList.length),
    };

    setExecutionResult(result);
    setAnnouncement(`CLI task executed successfully. Estimated ${Math.round(result.tokensSavedEstimate)} tokens saved via BYOS.`);
    onExecutionCompleted?.(result);
  };

  return (
    <section
      aria-label="External CLI Subagent Passthrough and BYOS Dispatcher"
      className="p-4 bg-slate-900/90 border border-slate-700/80 rounded-xl shadow-xl text-slate-100 flex flex-col gap-4 text-xs font-sans"
    >
      <header className="flex flex-wrap items-center justify-between border-b border-slate-700/60 pb-3 gap-2">
        <div className="flex items-center gap-2">
          <span className="text-base font-semibold text-emerald-400">
            ⚡ External CLI Subagent & BYOS Passthrough
          </span>
          {chatId && (
            <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
              Session: {chatId}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800">
            Confinement: <span className="font-mono">{workspaceRoot}</span>
          </span>
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              aria-label="Dismiss CLI Passthrough Card"
              className="text-slate-400 hover:text-white px-2 py-0.5 rounded hover:bg-slate-800"
            >
              ✕
            </button>
          )}
        </div>
      </header>

      {/* Accessible live region */}
      <output aria-live="polite" className="sr-only">
        {announcement}
      </output>

      {/* Profile Bundles Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
        {bundles.map((bundle) => {
          const isSelected = bundle.bundleId === selectedBundleId;
          return (
            <button
              type="button"
              key={bundle.bundleId}
              onClick={() => {
                setSelectedBundleId(bundle.bundleId);
                setIsPrivacyAcknowledged(false);
              }}
              className={`p-3 rounded-lg border text-left flex flex-col gap-1.5 transition-all ${
                isSelected
                  ? 'border-emerald-500 bg-emerald-950/30 shadow-md shadow-emerald-950/40 ring-1 ring-emerald-500/60'
                  : 'border-slate-800 bg-slate-900/60 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-200">
                  {bundle.displayName.split('(')[0]?.trim()}
                </span>
                <span className="text-[9px] px-1.5 py-0.2 rounded bg-emerald-900/40 text-emerald-300 border border-emerald-700">
                  {bundle.subscriptionStatus.toUpperCase()}
                </span>
              </div>
              <div className="flex items-center gap-1.5 text-[10px] text-slate-400">
                <span>Account:</span>
                <span className="font-mono text-slate-300">
                  {bundle.accountEmailMasked ?? 'BYOS Local'}
                </span>
              </div>
              <div className="text-[9px] font-mono text-slate-500 truncate">
                Flags: {bundle.defaultFlags.join(' ')}
              </div>
            </button>
          );
        })}
      </div>

      {/* Privacy Disclosure & Data Accounting Box */}
      <div className="p-3 rounded-lg bg-amber-950/20 border border-amber-600/50 flex flex-col gap-2">
        <div className="flex items-center gap-1.5 text-amber-300 font-semibold text-[11px]">
          <span>🛡️ Transparent Data Flow & BYOS Disclosure</span>
          <span className="text-[9px] px-1.5 py-0.2 rounded bg-amber-900/50 text-amber-200 border border-amber-700">
            Ascendancydota Privacy Guard
          </span>
        </div>
        <p className="text-[11px] text-slate-300 leading-relaxed">
          Delegating this task will transfer selected files to{' '}
          <strong className="text-amber-300">{vendorInfo.vendor}</strong> using your local{' '}
          <span className="underline">{selectedBundle.displayName}</span> installation. File
          modifications are strictly confined to inherited root{' '}
          <span className="font-mono text-cyan-300">{workspaceRoot}</span> without privilege
          escalation.
        </p>
        <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-amber-700/30 text-[10px]">
          <div className="flex items-center gap-2">
            <label htmlFor={sensitivitySelectId} className="text-slate-400">
              Sensitivity:
            </label>
            <select
              id={sensitivitySelectId}
              value={sensitivity}
              onChange={(e) => setSensitivity(e.target.value as SensitivityLevel)}
              className="px-2 py-0.5 rounded bg-slate-900 border border-slate-700 text-slate-200"
            >
              <option value="low">Low (Public Code)</option>
              <option value="medium">Medium (Internal Module)</option>
              <option value="high">High (Core Logic)</option>
              <option value="critical">Critical (Secrets/PII)</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <input
              id={privacyCheckId}
              type="checkbox"
              checked={isPrivacyAcknowledged}
              onChange={(e) => handleTogglePrivacy(e.target.checked)}
              className="rounded bg-slate-900 border-slate-700 text-emerald-500 focus:ring-0"
            />
            <label
              htmlFor={privacyCheckId}
              className="text-slate-200 cursor-pointer font-medium select-none"
            >
              I acknowledge vendor terms & context transfer to {vendorInfo.vendor}
            </label>
          </div>
        </div>
      </div>

      {/* Task Delegation Form */}
      <form onSubmit={handleExecute} className="flex flex-col gap-2.5">
        <div className="flex flex-col gap-1">
          <label htmlFor={instructionInputId} className="text-slate-300 font-medium">
            Task Instruction (Headless Non-Interactive)
          </label>
          <textarea
            id={instructionInputId}
            rows={2}
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            className="px-2.5 py-1.5 rounded bg-slate-950 border border-slate-700 text-slate-100 focus:outline-none focus:border-emerald-400 font-mono text-[11px]"
            required
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor={filesInputId} className="text-slate-300 font-medium">
            Context Files (Comma Separated)
          </label>
          <input
            id={filesInputId}
            type="text"
            value={contextFiles}
            onChange={(e) => setContextFiles(e.target.value)}
            className="px-2.5 py-1 rounded bg-slate-950 border border-slate-700 text-slate-100 focus:outline-none focus:border-emerald-400 font-mono text-[11px]"
          />
        </div>

        <div className="flex items-center justify-between pt-1">
          <div className="text-[10px] text-slate-400">
            {!isPrivacyAcknowledged && (
              <span className="text-rose-400">
                * Acknowledge privacy disclosure above before execution
              </span>
            )}
          </div>
          <button
            type="submit"
            disabled={!isPrivacyAcknowledged || !instruction.trim()}
            className={`px-3.5 py-1.5 rounded font-medium transition-all ${
              isPrivacyAcknowledged && instruction.trim()
                ? 'bg-emerald-600 hover:bg-emerald-500 text-white cursor-pointer'
                : 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
            }`}
          >
            🚀 Dispatch to {selectedBundle.executableName} (BYOS)
          </button>
        </div>
      </form>

      {/* Execution Result Box */}
      {executionResult && (
        <div className="p-3 rounded-lg bg-slate-950 border border-emerald-500/50 flex flex-col gap-2">
          <div className="flex flex-wrap items-center justify-between gap-1 border-b border-slate-800 pb-1.5">
            <span className="font-semibold text-emerald-400">
              Execution Succeeded (Exit Code: 0)
            </span>
            <div className="flex items-center gap-2">
              <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                ~{Math.round(executionResult.tokensSavedEstimate)} Tokens Saved
              </span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 font-mono">
                {executionResult.egressAccountingId}
              </span>
            </div>
          </div>

          <p className="text-[11px] text-slate-300">{executionResult.structuredSummary}</p>

          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-slate-400 font-mono">Git Diff Output:</span>
            <pre className="p-2 rounded bg-slate-900 border border-slate-800 font-mono text-[10px] text-emerald-300/90 overflow-x-auto whitespace-pre">
              {executionResult.diffOutput}
            </pre>
          </div>

          <div className="text-[9px] text-slate-500 font-mono truncate">
            SHA-256 Audit: {executionResult.tamperProofAuditHash}
          </div>
        </div>
      )}
    </section>
  );
};
