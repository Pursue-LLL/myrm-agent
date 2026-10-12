'use client';

/**
 * [INPUT]
 * @/services/memory/procedureExperience::RegisterProcedureMemoryRequest
 *
 * [OUTPUT]
 * ProcedureRegisterForm: Subcomponent providing the 8-field procedure registration form.
 *
 * [POS]
 * Subcomponent for Item 104 (ProcedureShapedExperienceProtocolAndFixedCountDualNodeRetrievalSuite).
 * Strict typing applied: No `any` types allowed. Single file < 200 lines.
 */

import React, { useState } from 'react';
import { Button } from '@/components/primitives/button';
import { Sparkles, X } from 'lucide-react';
import type { RegisterProcedureMemoryRequest } from '@/services/memory/procedureExperience';

interface ProcedureRegisterFormProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (req: RegisterProcedureMemoryRequest) => Promise<void>;
  isLoading: boolean;
}

export function ProcedureRegisterForm({
  isOpen,
  onClose,
  onSubmit,
  isLoading,
}: ProcedureRegisterFormProps): React.JSX.Element | null {
  const [name, setName] = useState<string>('');
  const [intent, setIntent] = useState<string>('');
  const [preconditions, setPreconditions] = useState<string>('');
  const [boundary, setBoundary] = useState<string>('');
  const [steps, setSteps] = useState<string>('');
  const [antiPatterns, setAntiPatterns] = useState<string>('');
  const [applicability, setApplicability] = useState<string>('');
  const [negativeApplicability, setNegativeApplicability] = useState<string>('');

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!name.trim() || !intent.trim()) return;

    await onSubmit({
      name: name.trim(),
      operation_intent: intent.trim(),
      preconditions: preconditions.split('\n').map((s) => s.trim()).filter(Boolean),
      immutable_boundary: boundary.split('\n').map((s) => s.trim()).filter(Boolean),
      procedure_steps: steps.split('\n').map((s) => s.trim()).filter(Boolean),
      write_field_provenance: { audit_provenance: '由用户显式策展注册派生' },
      anti_patterns: antiPatterns.split('\n').map((s) => s.trim()).filter(Boolean),
      applicability: applicability.split('\n').map((s) => s.trim()).filter(Boolean),
      negative_applicability: negativeApplicability.split('\n').map((s) => s.trim()).filter(Boolean),
      confidence: 1.0,
    });

    onClose();
    setName('');
    setIntent('');
    setPreconditions('');
    setBoundary('');
    setSteps('');
    setAntiPatterns('');
    setApplicability('');
    setNegativeApplicability('');
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-border-subtle bg-surface p-4 space-y-3 shadow-xs"
    >
      <div className="flex items-center justify-between">
        <span className="font-semibold text-text-primary text-xs flex items-center gap-1.5">
          <Sparkles className="h-4 w-4 text-primary" />
          注册八字段过程形态经验
        </span>
        <button
          type="button"
          onClick={onClose}
          className="text-text-secondary hover:text-text-primary focus:outline-none focus:ring-2 focus:ring-primary rounded"
          aria-label="关闭录入表单"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label htmlFor="proc-name" className="block text-xs font-medium text-text-secondary mb-1">
            过程经验名称
          </label>
          <input
            id="proc-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="例如: 生产发布门禁流水线规范"
            className="w-full rounded-md border border-border-subtle bg-surface-subtle px-3 py-1.5 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
            required
          />
        </div>

        <div>
          <label htmlFor="proc-intent" className="block text-xs font-medium text-text-secondary mb-1">
            核心操作意图 (operation_intent)
          </label>
          <input
            id="proc-intent"
            type="text"
            value={intent}
            onChange={(e) => setIntent(e.target.value)}
            placeholder="在代码提交合并前执行严格质量与 a11y 检查"
            className="w-full rounded-md border border-border-subtle bg-surface-subtle px-3 py-1.5 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
            required
          />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label htmlFor="proc-pre" className="block text-xs font-medium text-text-secondary mb-1">
            前置条件 (每行一条)
          </label>
          <textarea
            id="proc-pre"
            value={preconditions}
            onChange={(e) => setPreconditions(e.target.value)}
            rows={2}
            placeholder="工作区无破坏性未暂存代码"
            className="w-full rounded-md border border-border-subtle bg-surface-subtle p-2 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
            required
          />
        </div>

        <div>
          <label htmlFor="proc-boundary" className="block text-xs font-medium text-text-secondary mb-1">
            不可变边界 (每行一条)
          </label>
          <textarea
            id="proc-boundary"
            value={boundary}
            onChange={(e) => setBoundary(e.target.value)}
            rows={2}
            placeholder="禁止强推主分支"
            className="w-full rounded-md border border-border-subtle bg-surface-subtle p-2 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
            required
          />
        </div>

        <div>
          <label htmlFor="proc-anti" className="block text-xs font-medium text-text-secondary mb-1">
            反模式与避坑 (每行一条)
          </label>
          <textarea
            id="proc-anti"
            value={antiPatterns}
            onChange={(e) => setAntiPatterns(e.target.value)}
            rows={2}
            placeholder="严禁使用 any 类型注解"
            className="w-full rounded-md border border-border-subtle bg-surface-subtle p-2 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
            required
          />
        </div>
      </div>

      <div>
        <label htmlFor="proc-steps" className="block text-xs font-medium text-text-secondary mb-1">
          分步执行流程 (每行一条原子步骤)
        </label>
        <textarea
          id="proc-steps"
          value={steps}
          onChange={(e) => setSteps(e.target.value)}
          rows={3}
          placeholder="1. 执行 bun run lint&#10;2. 执行 check-a11y-ratchet.mjs&#10;3. 执行 pytest 回归"
          className="w-full rounded-md border border-border-subtle bg-surface-subtle p-2 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
          required
        />
      </div>

      <div className="flex justify-end gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onClose}
          className="focus:outline-none focus:ring-2 focus:ring-primary"
        >
          取消
        </Button>
        <Button
          type="submit"
          size="sm"
          disabled={isLoading || !name.trim() || !intent.trim()}
          className="bg-primary text-primary-foreground hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary"
        >
          确认注册
        </Button>
      </div>
    </form>
  );
}
