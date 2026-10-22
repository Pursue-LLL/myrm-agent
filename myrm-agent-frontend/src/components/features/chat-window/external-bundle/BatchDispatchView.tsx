import React, { useState } from 'react';
import { BatchDispatchTask, ExternalBundleProfileSpec } from './types';

export interface BatchDispatchViewProps {
  bundles: ExternalBundleProfileSpec[];
  initialBundleId?: string;
  isDispatching: boolean;
  onDispatchBatch: (tasks: BatchDispatchTask[], workspaceRoot?: string) => Promise<void>;
}

export const BatchDispatchView: React.FC<BatchDispatchViewProps> = ({
  bundles,
  initialBundleId,
  isDispatching,
  onDispatchBatch,
}) => {
  const [tasks, setTasks] = useState<BatchDispatchTask[]>([
    {
      bundle_id: initialBundleId || (bundles[0]?.bundle_id ?? 'subagent-codex'),
      role_label: 'frontend-refactorer',
      task_prompt: 'Refactor UI components to remove deprecated CSS and add micro-animations.',
      target_subdir: 'frontend',
      timeout_seconds: 60,
    },
  ]);
  const [workspaceRoot, setWorkspaceRoot] = useState<string>('');

  const handleAddTask = () => {
    setTasks((prev) => [
      ...prev,
      {
        bundle_id: bundles[0]?.bundle_id ?? 'subagent-codex',
        role_label: `worker-${prev.length + 1}`,
        task_prompt: '',
        target_subdir: '',
        timeout_seconds: 60,
      },
    ]);
  };

  const handleRemoveTask = (index: number) => {
    if (tasks.length <= 1) {
      return;
    }
    setTasks((prev) => prev.filter((_, i) => i !== index));
  };

  const handleUpdateTask = <K extends keyof BatchDispatchTask>(
    index: number,
    field: K,
    value: BatchDispatchTask[K],
  ) => {
    setTasks((prev) => {
      const copy = [...prev];
      copy[index] = { ...copy[index], [field]: value };
      return copy;
    });
  };

  const handleApplyPreset = (presetType: 'pair' | 'audit_refactor') => {
    if (presetType === 'pair') {
      const codexBundle = bundles.find((b) => b.agent_type === 'codex') || bundles[0];
      setTasks([
        {
          bundle_id: codexBundle?.bundle_id || 'subagent-codex',
          role_label: 'frontend-dev',
          task_prompt: 'Generate unit tests for all UI views in frontend/components.',
          target_subdir: 'frontend',
          timeout_seconds: 60,
        },
        {
          bundle_id: codexBundle?.bundle_id || 'subagent-codex',
          role_label: 'backend-dev',
          task_prompt: 'Implement DTO validation and error handling for endpoints.',
          target_subdir: 'backend',
          timeout_seconds: 60,
        },
      ]);
    } else {
      const claudeBundle = bundles.find((b) => b.agent_type === 'claude_code') || bundles[0];
      const codexBundle = bundles.find((b) => b.agent_type === 'codex') || bundles[0];
      setTasks([
        {
          bundle_id: claudeBundle?.bundle_id || 'subagent-claude-code',
          role_label: 'security-reviewer',
          task_prompt: 'Scan codebase for path traversal and unescaped command interpolations.',
          target_subdir: '',
          timeout_seconds: 90,
        },
        {
          bundle_id: codexBundle?.bundle_id || 'subagent-codex',
          role_label: 'syntax-fixer',
          task_prompt: 'Fix all strict TypeScript compiler warnings and lint errors.',
          target_subdir: 'frontend',
          timeout_seconds: 60,
        },
      ]);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (tasks.length === 0 || isDispatching) {
      return;
    }
    onDispatchBatch(tasks, workspaceRoot.trim() ? workspaceRoot.trim() : undefined);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-foreground">Lock-Free Parallel Subagent Dispatch</h3>
          <p className="text-xs text-muted-foreground">
            Concurrently instantiate multiple isolated CLI subagent workers (e.g. 2 Codex + 1 Claude Code) without blocking mutual execution.
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] text-muted-foreground font-medium">Quick Presets:</span>
          <button
            type="button"
            onClick={() => handleApplyPreset('pair')}
            className="rounded bg-muted px-2 py-1 text-[11px] font-medium text-foreground hover:bg-muted/80 transition-colors"
          >
            Twin Codex Pair
          </button>
          <button
            type="button"
            onClick={() => handleApplyPreset('audit_refactor')}
            className="rounded bg-muted px-2 py-1 text-[11px] font-medium text-foreground hover:bg-muted/80 transition-colors"
          >
            Claude + Codex
          </button>
        </div>
      </div>

      <div className="space-y-3">
        {tasks.map((task, idx) => (
          <div
            key={idx}
            className="rounded-lg border border-border/50 bg-card/60 p-3.5 space-y-3 shadow-xs"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-bold text-foreground">
                Worker #{idx + 1}
              </span>
              {tasks.length > 1 && (
                <button
                  type="button"
                  onClick={() => handleRemoveTask(idx)}
                  className="text-xs text-destructive hover:underline"
                >
                  Remove
                </button>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
              <div>
                <label
                  htmlFor={`worker-${idx}-bundle`}
                  className="block text-[11px] font-medium text-muted-foreground mb-1"
                >
                  Subagent Bundle
                </label>
                <select
                  id={`worker-${idx}-bundle`}
                  value={task.bundle_id}
                  onChange={(e) => handleUpdateTask(idx, 'bundle_id', e.target.value)}
                  className="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-xs text-foreground focus:ring-1 focus:ring-primary"
                >
                  {bundles.map((b) => (
                    <option key={b.bundle_id} value={b.bundle_id}>
                      {b.display_name} ({b.binary_name})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label
                  htmlFor={`worker-${idx}-role`}
                  className="block text-[11px] font-medium text-muted-foreground mb-1"
                >
                  Role Label
                </label>
                <input
                  id={`worker-${idx}-role`}
                  type="text"
                  value={task.role_label}
                  onChange={(e) => handleUpdateTask(idx, 'role_label', e.target.value)}
                  placeholder="e.g. frontend-coder"
                  className="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-xs text-foreground focus:ring-1 focus:ring-primary"
                  required
                />
              </div>

              <div>
                <label
                  htmlFor={`worker-${idx}-subdir`}
                  className="block text-[11px] font-medium text-muted-foreground mb-1"
                >
                  Scope Subdirectory (Optional)
                </label>
                <input
                  id={`worker-${idx}-subdir`}
                  type="text"
                  value={task.target_subdir}
                  onChange={(e) => handleUpdateTask(idx, 'target_subdir', e.target.value)}
                  placeholder="e.g. frontend"
                  className="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-xs text-foreground focus:ring-1 focus:ring-primary"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor={`worker-${idx}-prompt`}
                className="block text-[11px] font-medium text-muted-foreground mb-1"
              >
                Task Prompt / Instruction
              </label>
              <textarea
                id={`worker-${idx}-prompt`}
                value={task.task_prompt}
                onChange={(e) => handleUpdateTask(idx, 'task_prompt', e.target.value)}
                placeholder="Specify the specific mission or task for this subagent instance..."
                rows={2}
                className="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-xs text-foreground focus:ring-1 focus:ring-primary"
                required
              />
            </div>
          </div>
        ))}
      </div>

      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-2">
        <button
          type="button"
          onClick={handleAddTask}
          disabled={tasks.length >= 6}
          className="rounded-md border border-dashed border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted/40 transition-colors"
        >
          + Add Parallel Worker ({tasks.length}/6)
        </button>

        <div className="flex items-center gap-2">
          <input
            type="text"
            value={workspaceRoot}
            onChange={(e) => setWorkspaceRoot(e.target.value)}
            placeholder="Custom workspace root (optional)"
            className="rounded-md border border-border bg-background px-2.5 py-1.5 text-xs text-foreground w-56"
          />
          <button
            type="submit"
            disabled={isDispatching}
            className="rounded-md bg-primary px-4 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 transition-colors shadow-sm disabled:opacity-50"
          >
            {isDispatching ? 'Launching Multi-Agent Batch...' : `Concurrently Dispatch (${tasks.length})`}
          </button>
        </div>
      </div>
    </form>
  );
};
