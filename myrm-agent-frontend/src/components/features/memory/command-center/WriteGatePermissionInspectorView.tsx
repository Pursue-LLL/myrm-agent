'use client';

/**
 * [INPUT]
 * @/services/memory/diskReconciliation::WriteGateCheckResultDTO, SetWriteGatePolicyRequestDTO, WriteGatePolicy
 *
 * [OUTPUT]
 * WriteGatePermissionInspectorView: Subview component rendering explicit memory write-gate permissions,
 * read-write path decoupling architecture indicators, policy toggles, and live permission probes.
 *
 * [POS]
 * Subcomponent for Item 94 (Disk Memory FTS Reconciliation Loop and Explicit Write Gate Suite).
 * Strict typing applied: No `any` types allowed. Single file < 350 lines.
 */

import React, { useState } from 'react';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { ShieldAlert, ShieldCheck, Lock, Unlock, Eye, HelpCircle } from 'lucide-react';
import type {
  WriteGateCheckResultDTO,
  SetWriteGatePolicyRequestDTO,
  WriteGatePolicy,
} from '@/services/memory/diskReconciliation';

interface WriteGatePermissionInspectorViewProps {
  currentGateResult: WriteGateCheckResultDTO | null;
  onCheckWriteGate: (sessionId?: string) => Promise<void>;
  onSetWriteGatePolicy: (request: SetWriteGatePolicyRequestDTO) => Promise<void>;
}

const POLICY_OPTIONS: Array<{
  value: WriteGatePolicy;
  label: string;
  desc: string;
  allowed: boolean;
}> = [
  {
    value: 'enabled',
    label: '显式开放 (ENABLED)',
    desc: '正常持久化写入模式，Agent 会话事实与对账更新均被允许。',
    allowed: true,
  },
  {
    value: 'read_only_session',
    label: '会话只读 (READ_ONLY_SESSION)',
    desc: '会话隔离只读保护，禁止写入持久记忆，防止意外副作用。',
    allowed: false,
  },
  {
    value: 'disabled_temporary',
    label: '临时停用 (DISABLED_TEMPORARY)',
    desc: '系统维护或排查期全局写阻断，保障现有磁盘数据绝对不可变。',
    allowed: false,
  },
  {
    value: 'disabled_config_fault',
    label: '配置故障降级 (DISABLED_CONFIG_FAULT)',
    desc: '环境或工作区配置异常时的安全熔断退化，严防盲写污染。',
    allowed: false,
  },
];

export function WriteGatePermissionInspectorView({
  currentGateResult,
  onCheckWriteGate,
  onSetWriteGatePolicy,
}: WriteGatePermissionInspectorViewProps): React.JSX.Element {
  const [selectedPolicy, setSelectedPolicy] = useState<WriteGatePolicy>('enabled');
  const [sessionInput, setSessionInput] = useState<string>('');
  const [isUpdating, setIsUpdating] = useState<boolean>(false);
  const [isProbing, setIsProbing] = useState<boolean>(false);

  const handleUpdatePolicySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsUpdating(true);
    try {
      await onSetWriteGatePolicy({
        policy: selectedPolicy,
        session_id: sessionInput.trim() || undefined,
      });
    } finally {
      setIsUpdating(false);
    }
  };

  const handleProbeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsProbing(true);
    try {
      await onCheckWriteGate(sessionInput.trim() || undefined);
    } finally {
      setIsProbing(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="write-gate-permission-inspector-view">
      {/* Decoupling Notice */}
      <div className="rounded-lg border border-border/60 bg-accent/15 p-3 text-xs space-y-1.5">
        <div className="font-semibold text-foreground flex items-center gap-1.5">
          <Eye className="w-4 h-4 text-emerald-500" />
          严格读写解耦架构 (Read-Always-Open vs Write-Permission-Checked)
        </div>
        <p className="text-muted-foreground leading-relaxed text-[11px]">
          遵循小米 MiMo Code 架构精髓：<span className="text-foreground font-semibold">读取操作恒定开放</span>
          ，不受写门禁任何干扰；<span className="text-foreground font-semibold">写入操作受强类型门禁严格管控</span>
          。配置缺失或沙箱受限时安全退化，从根源杜绝后台盲写污染记忆库。
        </p>
      </div>

      {/* Grid: Policy Settings & Live Probe */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Left: Policy Configuration */}
        <div className="rounded-lg border border-border/60 bg-accent/15 p-3.5 space-y-3">
          <div className="flex items-center gap-2 font-semibold text-xs text-foreground">
            <Lock className="w-4 h-4 text-primary" />
            写入门禁策略管控 (Write Gate Policy Switch)
          </div>

          <form onSubmit={handleUpdatePolicySubmit} className="space-y-3 text-xs" data-testid="set-write-gate-form">
            <div>
              <label htmlFor="select-gate-policy" className="block text-muted-foreground mb-1 text-[11px]">
                选择目标门禁策略：
              </label>
              <select
                id="select-gate-policy"
                value={selectedPolicy}
                onChange={(e) => setSelectedPolicy(e.target.value as WriteGatePolicy)}
                className="w-full rounded border border-border bg-background px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              >
                {POLICY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="gate-session-override-input" className="block text-muted-foreground mb-1 text-[11px]">
                会话作用域（留空为全局策略；填入 session_id 则为该会话专属覆盖）：
              </label>
              <input
                id="gate-session-override-input"
                type="text"
                value={sessionInput}
                onChange={(e) => setSessionInput(e.target.value)}
                placeholder="例如：sess_inspect_01 或留空全局"
                className="w-full rounded border border-border bg-background px-2.5 py-1.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary font-mono"
              />
            </div>

            <div className="flex justify-end pt-1">
              <Button
                type="submit"
                size="sm"
                disabled={isUpdating}
                aria-label="应用写入门禁策略"
                className="text-xs focus:outline-none focus:ring-2 focus:ring-primary"
                data-testid="btn-apply-write-policy"
              >
                {isUpdating ? '正在切换...' : '应用门禁策略'}
              </Button>
            </div>
          </form>

          {/* Policy Descriptions */}
          <div className="space-y-1.5 pt-2 border-t border-border/40">
            {POLICY_OPTIONS.map((opt) => (
              <div
                key={opt.value}
                className={`p-2 rounded border text-[11px] space-y-0.5 ${
                  selectedPolicy === opt.value
                    ? 'border-primary/50 bg-primary/10'
                    : 'border-border/40 bg-background/40 opacity-75'
                }`}
              >
                <div className="flex items-center justify-between font-semibold">
                  <span>{opt.label}</span>
                  <Badge
                    variant={opt.allowed ? 'outline' : 'secondary'}
                    className={`text-[9px] ${opt.allowed ? 'text-emerald-600 border-emerald-500/40' : 'text-amber-600'}`}
                  >
                    {opt.allowed ? '允许写入' : '拦截阻断'}
                  </Badge>
                </div>
                <div className="text-muted-foreground text-[10px]">{opt.desc}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Live Gate Decision Probe */}
        <div className="rounded-lg border border-border/60 bg-accent/15 p-3.5 space-y-3">
          <div className="flex items-center justify-between border-b border-border/40 pb-2">
            <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-primary" />
              实时写门禁裁决探针 (Live Gate Decision Probe)
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleProbeSubmit}
              disabled={isProbing}
              aria-label="评估当前写门禁状态"
              className="text-xs h-7 focus:outline-none focus:ring-2 focus:ring-primary"
              data-testid="btn-probe-write-gate"
            >
              {isProbing ? '评估中...' : '校验写权限'}
            </Button>
          </div>

          {currentGateResult ? (
            <div className="space-y-3 text-xs" data-testid="gate-decision-box">
              <div
                className={`rounded-lg border p-3 flex items-start gap-2.5 ${
                  currentGateResult.is_allowed
                    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-800 dark:text-emerald-300'
                    : 'border-amber-500/30 bg-amber-500/10 text-amber-800 dark:text-amber-300'
                }`}
              >
                {currentGateResult.is_allowed ? (
                  <Unlock className="w-5 h-5 text-emerald-500 shrink-0 mt-0.5" />
                ) : (
                  <ShieldAlert className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
                )}
                <div className="space-y-1">
                  <div className="font-semibold text-sm flex items-center gap-2">
                    <span>
                      {currentGateResult.is_allowed ? '写权限通过：允许持久化写入' : '写权限拦截：禁止持久化写入'}
                    </span>
                    <Badge variant="outline" className="text-[10px] uppercase font-mono">
                      {currentGateResult.policy}
                    </Badge>
                  </div>
                  <p className="text-xs opacity-90">{currentGateResult.reason}</p>
                </div>
              </div>

              <div className="rounded border border-border/50 bg-background/60 p-2.5 space-y-1.5 text-[11px]">
                <div className="font-medium text-foreground flex items-center gap-1">
                  <HelpCircle className="w-3.5 h-3.5 text-muted-foreground" />
                  当前运行时防护说明：
                </div>
                <div className="text-muted-foreground leading-relaxed">
                  若在此模式下执行 `write_memory` 或写入工作区记忆卡片，Harness 引擎将主动触发{' '}
                  <span className="font-mono text-foreground font-medium">MemoryWriteBlockedError</span>{' '}
                  受控异常，避免发生脏写入或覆盖用户在外部 IDE 中精心维护的代码设计笔记。
                </div>
              </div>
            </div>
          ) : (
            <div className="py-8 text-center text-xs text-muted-foreground">
              尚未检测门禁状态，可点击右上角按钮立即评估当前会话的写权限。
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
