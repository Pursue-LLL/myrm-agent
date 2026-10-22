import React, { useState } from 'react';
import { BotProfile, OverlapCheckResult } from './types';

export interface AgentForgeFormViewProps {
  isProcessing: boolean;
  onCheckOverlap: (name: string, purpose: string) => Promise<OverlapCheckResult>;
  onCreateAgent: (spec: BotProfile, isSandbox: boolean, allowOverlap: boolean) => Promise<void>;
}

export const AgentForgeFormView: React.FC<AgentForgeFormViewProps> = ({
  isProcessing,
  onCheckOverlap,
  onCreateAgent,
}) => {
  const [naturalPrompt, setNaturalPrompt] = useState<string>('');
  const [name, setName] = useState<string>('daily-digest-bot');
  const [displayName, setDisplayName] = useState<string>('Daily Digest Bot');
  const [description, setDescription] = useState<string>('Compiles executive daily briefings from news feeds and notifications');
  const [systemPrompt, setSystemPrompt] = useState<string>('You synthesize morning news feeds into 3 high-impact executive bullets.');
  const [model, setModel] = useState<string>('gpt-5');
  const [tools, setTools] = useState<string[]>(['file_read', 'web_search']);
  const [skills, setSkills] = useState<string[]>(['data_analysis']);
  const [cronRoutine, setCronRoutine] = useState<string>('0 8 * * 1-5');
  const [isSandbox, setIsSandbox] = useState<boolean>(false);
  const [allowOverlap, setAllowOverlap] = useState<boolean>(false);
  const [overlapResult, setOverlapResult] = useState<OverlapCheckResult | null>(null);

  const availableTools = ['file_read', 'file_write', 'web_search', 'bash_exec', 'git_status'];
  const availableSkills = ['code_review', 'data_analysis', 'ast_lint'];

  const handleApplyPreset = (type: 'digest' | 'security' | 'finance') => {
    if (type === 'digest') {
      setName('daily-digest-bot');
      setDisplayName('Daily Digest Bot');
      setDescription('Compiles executive daily briefings from news feeds and notifications');
      setSystemPrompt('You synthesize morning news feeds into 3 high-impact executive bullets.');
      setModel('gpt-5');
      setTools(['file_read', 'web_search']);
      setSkills(['data_analysis']);
      setCronRoutine('0 8 * * 1-5');
    } else if (type === 'security') {
      setName('sec-auditor');
      setDisplayName('Security Auditor');
      setDescription('Audits codebases for hardcoded secrets, injection vectors, and dependency vulnerabilities');
      setSystemPrompt('You are a dedicated AppSec auditor. Verify AST lints and fail closed on credential leaks.');
      setModel('claude-3-7-sonnet');
      setTools(['file_read', 'bash_exec']);
      setSkills(['code_review', 'ast_lint']);
      setCronRoutine('');
    } else {
      setName('quarterly-analyst');
      setDisplayName('Quarterly Analyst');
      setDescription('Calculates valuation metrics and charts earnings trends across fiscal quarters');
      setSystemPrompt('Extract balance sheets, cashflow statements, and compute YoY EBITDA margin shifts.');
      setModel('deepseek-r1');
      setTools(['file_read', 'web_search']);
      setSkills(['data_analysis']);
      setCronRoutine('0 18 * * 5');
    }
    setOverlapResult(null);
  };

  const handleCheckOverlapClick = async () => {
    if (!name.trim() || !description.trim()) {
      return;
    }
    const res = await onCheckOverlap(name, description);
    setOverlapResult(res);
  };

  const handleToggleTool = (t: string) => {
    setTools((prev) => (prev.includes(t) ? prev.filter((item) => item !== t) : [...prev, t]));
  };

  const handleToggleSkill = (s: string) => {
    setSkills((prev) => (prev.includes(s) ? prev.filter((item) => item !== s) : [...prev, s]));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const spec: BotProfile = {
      name: name.trim().toLowerCase(),
      display_name: displayName.trim(),
      description: description.trim(),
      system_prompt: systemPrompt.trim(),
      model,
      tools,
      skills,
      mcp_servers: [],
      cron_routines: cronRoutine.trim() ? [cronRoutine.trim()] : [],
      role_type: 'specialist',
    };
    await onCreateAgent(spec, isSandbox, allowOverlap);
  };

  return (
    <div className="space-y-4">
      {/* Quick Prompt Bar */}
      <section aria-labelledby="natural-prompt-title" className="rounded-lg border border-border/50 bg-muted/20 p-3.5">
        <h3 id="natural-prompt-title" className="text-xs font-semibold text-foreground uppercase tracking-wider mb-2">
          One-Sentence Agent Blueprint
        </h3>
        <div className="flex gap-2">
          <input
            type="text"
            value={naturalPrompt}
            onChange={(e) => setNaturalPrompt(e.target.value)}
            placeholder="e.g. 帮我做一个每天分析财报并出图表的专属 Agent..."
            className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <button
            type="button"
            onClick={() => handleApplyPreset('finance')}
            className="rounded-md bg-secondary px-3 py-1.5 text-xs font-medium text-secondary-foreground hover:bg-secondary/80 transition-colors"
          >
            Auto Fill
          </button>
        </div>
        <div className="mt-2 flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <span>Quick presets:</span>
          <button
            type="button"
            onClick={() => handleApplyPreset('digest')}
            className="underline hover:text-foreground"
          >
            Daily Digest
          </button>
          <span>•</span>
          <button
            type="button"
            onClick={() => handleApplyPreset('security')}
            className="underline hover:text-foreground"
          >
            Sec Auditor
          </button>
          <span>•</span>
          <button
            type="button"
            onClick={() => handleApplyPreset('finance')}
            className="underline hover:text-foreground"
          >
            Financial Analyst
          </button>
        </div>
      </section>

      {/* Main Spec Form */}
      <form onSubmit={handleSubmit} className="space-y-3.5">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label htmlFor="agent-name-input" className="block text-xs font-medium text-foreground mb-1">
              Agent Name (Kebab-case) *
            </label>
            <input
              id="agent-name-input"
              type="text"
              required
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setOverlapResult(null);
              }}
              className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring font-mono"
            />
          </div>

          <div>
            <label htmlFor="display-name-input" className="block text-xs font-medium text-foreground mb-1">
              Display Name *
            </label>
            <input
              id="display-name-input"
              type="text"
              required
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <label htmlFor="agent-desc-input" className="text-xs font-medium text-foreground">
              Duty & Purpose Description *
            </label>
            <button
              type="button"
              disabled={isProcessing}
              onClick={handleCheckOverlapClick}
              className="text-[11px] text-indigo-500 hover:text-indigo-400 font-medium underline"
            >
              Analyze Duty Overlap
            </button>
          </div>
          <textarea
            id="agent-desc-input"
            rows={2}
            required
            value={description}
            onChange={(e) => {
              setDescription(e.target.value);
              setOverlapResult(null);
            }}
            className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>

        {/* Overlap Result Alert */}
        {overlapResult && (
          <output
            className={`block rounded-md p-2.5 text-xs border ${
              overlapResult.verdict === 'unique'
                ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-500'
                : 'bg-amber-500/10 border-amber-500/20 text-amber-500'
            }`}
          >
            <div className="font-semibold">
              {overlapResult.verdict === 'unique'
                ? '✅ Name and Duty are unique'
                : overlapResult.verdict === 'duplicate_name'
                ? '⚠️ Duplicate Name Detected'
                : '⚠️ Semantic Duty Overlap Detected'}
            </div>
            {overlapResult.recommendation && (
              <p className="mt-0.5 text-[11px] opacity-90">{overlapResult.recommendation}</p>
            )}
            {overlapResult.verdict === 'overlapping_duty' && (
              <label className="mt-2 flex items-center gap-1.5 text-[11px] text-foreground cursor-pointer">
                <input
                  type="checkbox"
                  checked={allowOverlap}
                  onChange={(e) => setAllowOverlap(e.target.checked)}
                  className="rounded border-input text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
                />
                <span>Acknowledge and force-allow overlap</span>
              </label>
            )}
          </output>
        )}

        <div>
          <label htmlFor="agent-prompt-input" className="block text-xs font-medium text-foreground mb-1">
            Core System Prompt
          </label>
          <textarea
            id="agent-prompt-input"
            rows={3}
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring font-mono"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label htmlFor="agent-model-select" className="block text-xs font-medium text-foreground mb-1">
              Backing Model *
            </label>
            <select
              id="agent-model-select"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="gpt-5">gpt-5 (Production Reasoning)</option>
              <option value="claude-3-7-sonnet">claude-3-7-sonnet (Hybrid Thinker)</option>
              <option value="deepseek-r1">deepseek-r1 (Math & Logic Solver)</option>
            </select>
          </div>

          <div>
            <label htmlFor="cron-routine-input" className="block text-xs font-medium text-foreground mb-1">
              Cron Routine (Optional)
            </label>
            <input
              id="cron-routine-input"
              type="text"
              value={cronRoutine}
              onChange={(e) => setCronRoutine(e.target.value)}
              placeholder="e.g. 0 9 * * 1-5"
              className="w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-ring font-mono"
            />
          </div>
        </div>

        {/* Tools and Skills */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
          <div>
            <span className="block text-xs font-medium text-foreground mb-1">Granted Tools</span>
            <div className="flex flex-wrap gap-1.5">
              {availableTools.map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => handleToggleTool(t)}
                  className={`rounded border px-2 py-0.5 text-[11px] font-mono transition-colors ${
                    tools.includes(t)
                      ? 'bg-indigo-500/10 border-indigo-500/30 text-indigo-500 font-semibold'
                      : 'bg-muted/40 border-border/40 text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {tools.includes(t) ? '✓ ' : '+ '}
                  {t}
                </button>
              ))}
            </div>
          </div>

          <div>
            <span className="block text-xs font-medium text-foreground mb-1">Bound Skills</span>
            <div className="flex flex-wrap gap-1.5">
              {availableSkills.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => handleToggleSkill(s)}
                  className={`rounded border px-2 py-0.5 text-[11px] font-mono transition-colors ${
                    skills.includes(s)
                      ? 'bg-purple-500/10 border-purple-500/30 text-purple-500 font-semibold'
                      : 'bg-muted/40 border-border/40 text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {skills.includes(s) ? '✓ ' : '+ '}
                  {s}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Safety Boundary Notice */}
        <div className="rounded-md border border-border/40 bg-muted/10 p-2.5 flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <span className="text-emerald-500">🛡️</span>
            <span className="text-muted-foreground text-[11px]">
              Anti-recursion guard active: Child agent cannot inherit meta-creation tools.
            </span>
          </div>
          <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={isSandbox}
              onChange={(e) => setIsSandbox(e.target.checked)}
              className="rounded border-input text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
            />
            <span>Sandbox Mode</span>
          </label>
        </div>

        <button
          type="submit"
          disabled={isProcessing}
          className="w-full rounded-md bg-primary py-2 px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 shadow-sm"
        >
          {isProcessing ? 'Verifying & Provisioning Pipeline...' : 'Verify & Provision Agent'}
        </button>
      </form>
    </div>
  );
};
