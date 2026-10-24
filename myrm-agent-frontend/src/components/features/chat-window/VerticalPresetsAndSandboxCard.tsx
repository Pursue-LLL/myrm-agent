import React, { useId, useState } from 'react';
import {
  AgentFlowStepItem,
  AgentFlowTraceItem,
  INITIAL_VERTICAL_PRESETS,
  SubBotTestResultItem,
  VerticalRoleCategory,
  VerticalRolePresetItem,
  VerticalPresetsAndSandboxCardProps,
} from './vertical-presets/types';

export const VerticalPresetsAndSandboxCard: React.FC<VerticalPresetsAndSandboxCardProps> = ({
  sessionId = 'sess-default',
  initialPresets = INITIAL_VERTICAL_PRESETS,
  onDismiss,
  onRunSandboxTest,
}) => {
  const [presets] = useState<VerticalRolePresetItem[]>(initialPresets);
  const [selectedCategory, setSelectedCategory] = useState<VerticalRoleCategory | 'all'>('all');
  const [activeRoleId, setActiveRoleId] = useState<string>(initialPresets[0]?.roleId ?? 'life_admin');

  const [testPrompt, setTestPrompt] = useState<string>('Test persona behavior in sandbox environment.');
  const [mockInputKey, setMockInputKey] = useState<string>('sample_key');
  const [mockInputValue, setMockInputValue] = useState<string>('sample_value');
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [latestResult, setLatestResult] = useState<SubBotTestResultItem | null>(null);

  const [agentTrace, setAgentTrace] = useState<AgentFlowTraceItem>({
    traceId: 'trace-demo-01',
    sessionId,
    rootAgentId: 'chief_of_staff',
    steps: [
      {
        stepId: 'step-101',
        sourceAgentId: 'chief_of_staff',
        targetAgentId: 'clipper',
        action: 'dispatch_research',
        payloadSummary: 'Extract competitor tech stack specs',
        resultSummary: 'Digest generated',
        durationMs: 85.0,
        timestamp: Date.now() - 5000,
      },
      {
        stepId: 'step-102',
        sourceAgentId: 'clipper',
        targetAgentId: 'sales_team',
        action: 'forward_leads',
        payloadSummary: 'Deliver qualified account summaries',
        resultSummary: 'Enriched in CRM',
        durationMs: 110.0,
        timestamp: Date.now() - 2000,
      },
    ],
    totalDurationMs: 195.0,
    isLoopDetected: false,
  });

  const categoryFilterId = useId();
  const testPromptId = useId();
  const mockKeyId = useId();
  const mockValId = useId();

  const filteredPresets = presets.filter(
    (p) => selectedCategory === 'all' || p.category === selectedCategory,
  );

  const activePreset = presets.find((p) => p.roleId === activeRoleId) ?? presets[0];

  const handleRunSandbox = () => {
    if (!activePreset) {
      return;
    }
    setIsRunning(true);
    const startTime = performance.now();

    setTimeout(() => {
      const elapsed = Math.round((performance.now() - startTime) + 35);
      const mockResult: SubBotTestResultItem = {
        testId: `test-${Math.random().toString(36).substring(2, 7)}`,
        roleId: activePreset.roleId,
        success: true,
        outputText: `[Sandbox Telemetry]: ${activePreset.displayName} executed successfully with prompt: "${testPrompt}".`,
        toolCallsMade: activePreset.recommendedTools.slice(0, 2),
        executionTimeMs: elapsed,
        logs: [
          `Sandbox container initialized for role [${activePreset.roleId}].`,
          `Applied persona reasoning tier: ${activePreset.reasoningEffort}.`,
          `Injected mock parameter: { "${mockInputKey}": "${mockInputValue}" }.`,
          `Execution completed cleanly in ${elapsed}ms.`,
        ],
        errorMessage: null,
      };

      setLatestResult(mockResult);
      setIsRunning(false);
      onRunSandboxTest?.(mockResult);

      const nextStep: AgentFlowStepItem = {
        stepId: `step-${Date.now().toString(36)}`,
        sourceAgentId: 'sandbox_runner',
        targetAgentId: activePreset.roleId,
        action: 'unit_test_probe',
        payloadSummary: testPrompt.slice(0, 35),
        resultSummary: 'Passed',
        durationMs: elapsed,
        timestamp: Date.now(),
      };

      setAgentTrace((prev) => ({
        ...prev,
        steps: [...prev.steps, nextStep],
        totalDurationMs: prev.totalDurationMs + elapsed,
      }));
    }, 400);
  };

  const handleSimulateLoop = () => {
    const loopStep1: AgentFlowStepItem = {
      stepId: `step-loop-${Date.now()}-1`,
      sourceAgentId: 'chief_of_staff',
      targetAgentId: 'clipper',
      action: 'ping',
      payloadSummary: 'ping message',
      durationMs: 12,
      timestamp: Date.now(),
    };
    const loopStep2: AgentFlowStepItem = {
      stepId: `step-loop-${Date.now()}-2`,
      sourceAgentId: 'clipper',
      targetAgentId: 'chief_of_staff',
      action: 'pong',
      payloadSummary: 'pong reply',
      durationMs: 15,
      timestamp: Date.now() + 1,
    };
    setAgentTrace((prev) => ({
      ...prev,
      steps: [...prev.steps, loopStep1, loopStep2],
      totalDurationMs: prev.totalDurationMs + 27,
      isLoopDetected: true,
    }));
  };

  return (
    <section
      aria-label="Five Vertical Role Persona Presets & Sub-Bot Sandbox Tester"
      className="p-4 bg-slate-900/90 border border-slate-700/80 rounded-xl shadow-xl text-slate-100 flex flex-col gap-4 text-xs font-sans"
    >
      <header className="flex items-center justify-between border-b border-slate-700/60 pb-3">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-emerald-400 ring-4 ring-emerald-500/20" />
          <h2 className="font-semibold text-sm text-slate-100 tracking-wide">
            Vertical Role Presets & Sub-Bot Sandbox
          </h2>
          <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-300 border border-slate-700">
            Session: {sessionId}
          </span>
        </div>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Close vertical presets card"
            className="text-slate-400 hover:text-slate-200 transition-colors p-1"
          >
            ✕
          </button>
        )}
      </header>

      {/* Filter and Presets List */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <label htmlFor={categoryFilterId} className="font-medium text-slate-300">
            Filter by Category:
          </label>
          <select
            id={categoryFilterId}
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value as VerticalRoleCategory | 'all')}
            className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="all">All Categories ({presets.length})</option>
            <option value="life_admin">Life Admin</option>
            <option value="office_manager">Office Manager</option>
            <option value="clipper">Clipper</option>
            <option value="chief_of_staff">Chief of Staff</option>
            <option value="sales_team">Sales Team</option>
          </select>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
          {filteredPresets.map((preset) => {
            const isSelected = preset.roleId === activeRoleId;
            return (
              <button
                key={preset.roleId}
                type="button"
                onClick={() => setActiveRoleId(preset.roleId)}
                className={`p-2.5 text-left rounded-lg border transition-all ${
                  isSelected
                    ? 'border-blue-500/80 bg-blue-950/40 shadow-sm shadow-blue-500/10'
                    : 'border-slate-800 bg-slate-800/40 hover:border-slate-700 hover:bg-slate-800/80'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-slate-200">{preset.displayName}</span>
                  <span className="text-[10px] uppercase font-mono px-1.5 py-0.2 rounded bg-slate-700/60 text-slate-300">
                    {preset.reasoningEffort} tier
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 line-clamp-2">{preset.description}</p>
              </button>
            );
          })}
        </div>
      </div>

      {/* Selected Role Persona Detail */}
      {activePreset && (
        <div className="p-3 bg-slate-800/60 border border-slate-700/50 rounded-lg flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-slate-200 text-xs">
              Role Config: {activePreset.displayName} ({activePreset.roleId})
            </h3>
            <span className="text-slate-400 text-[11px]">
              Skills: {activePreset.recommendedSkills.join(', ')}
            </span>
          </div>
          <div className="text-[11px] text-slate-300 bg-slate-900/60 p-2 rounded border border-slate-800">
            <span className="text-slate-400">Prompt: </span>
            {activePreset.personaPrompt}
          </div>
          <div className="flex flex-wrap gap-1 items-center">
            <span className="text-slate-400">Recommended Tools:</span>
            {activePreset.recommendedTools.map((tool) => (
              <span
                key={tool}
                className="px-1.5 py-0.5 rounded bg-slate-700/50 text-[10px] font-mono text-slate-300 border border-slate-600/40"
              >
                {tool}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Isolated Sandbox Tester Console */}
      <div className="p-3 bg-slate-800/40 border border-slate-700/70 rounded-lg flex flex-col gap-2.5">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-slate-200">Sub-Bot Sandbox Tester</h3>
          <span className="text-[10px] text-slate-400">Zero-Side-Effect Isolation</span>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor={testPromptId} className="text-slate-300 font-medium">
            Test Prompt:
          </label>
          <textarea
            id={testPromptId}
            rows={2}
            value={testPrompt}
            onChange={(e) => setTestPrompt(e.target.value)}
            className="w-full bg-slate-900 border border-slate-700 rounded p-1.5 text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div className="flex flex-col gap-1">
            <label htmlFor={mockKeyId} className="text-slate-300 font-medium">
              Mock Input Key:
            </label>
            <input
              id={mockKeyId}
              type="text"
              value={mockInputKey}
              onChange={(e) => setMockInputKey(e.target.value)}
              className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor={mockValId} className="text-slate-300 font-medium">
              Mock Input Value:
            </label>
            <input
              id={mockValId}
              type="text"
              value={mockInputValue}
              onChange={(e) => setMockInputValue(e.target.value)}
              className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200"
            />
          </div>
        </div>

        <div className="flex items-center gap-2 pt-1">
          <button
            type="button"
            onClick={handleRunSandbox}
            disabled={isRunning}
            className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-medium rounded transition-colors"
          >
            {isRunning ? 'Running Test...' : 'Run Sandbox Test'}
          </button>
          <button
            type="button"
            onClick={handleSimulateLoop}
            className="px-2.5 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded text-[11px] transition-colors"
          >
            Simulate Agent Loop
          </button>
        </div>

        {latestResult && (
          <output
            aria-live="polite"
            className="mt-2 p-2 bg-slate-900/90 border border-slate-700/80 rounded flex flex-col gap-1"
          >
            <div className="flex items-center justify-between font-mono text-[11px]">
              <span className={latestResult.success ? 'text-emerald-400' : 'text-red-400'}>
                {latestResult.success ? '✔ TEST PASSED' : '✖ TEST FAILED'}
              </span>
              <span className="text-slate-400">{latestResult.executionTimeMs} ms</span>
            </div>
            <p className="text-slate-200 text-[11px]">{latestResult.outputText}</p>
            {latestResult.logs.length > 0 && (
              <div className="font-mono text-[10px] text-slate-400 bg-slate-950 p-1.5 rounded border border-slate-800">
                {latestResult.logs.map((log) => (
                  <div key={log}>{log}</div>
                ))}
              </div>
            )}
          </output>
        )}
      </div>

      {/* Agent Communication Flow & Loop Detection Waterfall */}
      <div className="p-3 bg-slate-800/30 border border-slate-700/40 rounded-lg flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-slate-200">Agent Communication Chain Trace</h3>
          {agentTrace.isLoopDetected ? (
            <span className="px-2 py-0.5 rounded bg-red-950/80 border border-red-500/80 text-red-300 text-[10px] font-medium animate-pulse">
              ⚠ Loop / Deadlock Detected
            </span>
          ) : (
            <span className="px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-500/50 text-emerald-300 text-[10px]">
              Chain Normal ({agentTrace.steps.length} steps)
            </span>
          )}
        </div>

        <div className="flex flex-col gap-1.5 max-h-40 overflow-y-auto">
          {agentTrace.steps.map((step) => (
            <div
              key={step.stepId}
              className="p-1.5 bg-slate-900/60 border border-slate-800 rounded flex items-center justify-between text-[11px]"
            >
              <div className="flex items-center gap-1.5">
                <span className="font-mono text-blue-400">{step.sourceAgentId}</span>
                <span className="text-slate-500">→</span>
                <span className="font-mono text-purple-400">{step.targetAgentId}</span>
                <span className="text-slate-400 font-mono text-[10px]">[{step.action}]</span>
                <span className="text-slate-300 truncate max-w-[150px]">{step.payloadSummary}</span>
              </div>
              <span className="text-[10px] text-slate-400 font-mono">{step.durationMs}ms</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
