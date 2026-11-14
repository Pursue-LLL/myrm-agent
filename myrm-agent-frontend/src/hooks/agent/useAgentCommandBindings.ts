'use client';

/**
 * [INPUT]
 * @/services/agent::getAgent, updateAgent, CommandBindingConfig (POS: Agent API 客户端与 DTO 类型)
 * @/lib/utils/agent-config (POS: 命令绑定清洗/校验/载荷纯逻辑)
 *
 * [OUTPUT]
 * useAgentCommandBindings, AgentCommandBindingsState: 命令绑定草稿的加载、校验与独立持久化
 *
 * [POS]
 * Settings Agent 编辑面板中命令绑定的状态层。绑定以显式 `command_bindings` 键单独更新（服务端省略该键即保持不变），
 * 不进入 useAgentEditor 的整体保存载荷，两条保存互不覆盖；草稿由面板持有，切换 Tab 不丢失。
 * 草稿只对其基于的服务端快照有效：编辑器整体重载（回滚、时光机恢复）后重新拉取，新快照会让旧草稿自动失效。
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  areBindingsEqual,
  findBindingIssues,
  normalizeBinding,
  toBindingsPayload,
  type BindingIssue,
} from '@/lib/utils/agent-config';
import { getAgent, updateAgent, type CommandBindingConfig } from '@/services/agent';

type LoadStatus = 'idle' | 'loading' | 'ready' | 'error';

export interface AgentCommandBindingsState {
  /** 新建中的智能体还没有 id，无法持久化绑定。 */
  unavailable: boolean;
  status: LoadStatus;
  bindings: CommandBindingConfig[];
  setBindings: (next: CommandBindingConfig[]) => void;
  /** 与 `bindings` 按下标对齐的校验结果。 */
  issues: (BindingIssue | null)[];
  dirty: boolean;
  /** 已加载且每条绑定都可提交；加载失败时不可保存，避免用空草稿覆盖服务端绑定。 */
  canSave: boolean;
  saving: boolean;
  /** 失败时抛出，提示由调用方负责。 */
  save: () => Promise<void>;
}

/** 某次拉取的结果；`bindings` 为 null 表示拉取失败。 */
interface Snapshot {
  agentId: string;
  generation: number;
  bindings: CommandBindingConfig[] | null;
}

/** 草稿及其所基于的服务端快照；快照换了，草稿即作废。 */
interface Draft {
  baseline: CommandBindingConfig[];
  value: CommandBindingConfig[];
}

const NO_BINDINGS: CommandBindingConfig[] = [];

/** 编辑器每完成一次载入（含回滚后的重载）加一，作为重新拉取的信号；挂载时已就绪视为完成一次。 */
function useCompletedLoads(loading: boolean): number {
  const [completed, setCompleted] = useState(loading ? 0 : 1);
  const [wasLoading, setWasLoading] = useState(loading);
  if (loading !== wasLoading) {
    setWasLoading(loading);
    if (wasLoading) {
      setCompleted(completed + 1);
    }
  }
  return completed;
}

/**
 * @param editorLoading 编辑器整体（重）载入期间为 true；其结束后重新拉取绑定，保证回滚等操作后草稿与服务端一致。
 */
export function useAgentCommandBindings(
  agentId: string | null,
  isNew: boolean,
  editorLoading: boolean,
): AgentCommandBindingsState {
  const unavailable = isNew || !agentId;
  const generation = useCompletedLoads(editorLoading);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [draftState, setDraftState] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isNew || !agentId || editorLoading) {
      return;
    }
    let cancelled = false;
    getAgent(agentId)
      .then((agent) => {
        if (!cancelled) {
          setSnapshot({ agentId, generation, bindings: (agent.command_bindings ?? []).map(normalizeBinding) });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          console.error('Failed to load command bindings:', error);
          setSnapshot({ agentId, generation, bindings: null });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [agentId, isNew, editorLoading, generation]);

  const current = snapshot?.agentId === agentId && snapshot.generation === generation ? snapshot : null;
  const baseline = current?.bindings ?? null;
  const status: LoadStatus = unavailable
    ? 'idle'
    : editorLoading || !current
      ? 'loading'
      : baseline
        ? 'ready'
        : 'error';
  const draft = draftState && draftState.baseline === baseline ? draftState.value : null;
  const bindings = draft ?? baseline ?? NO_BINDINGS;

  const issues = useMemo(() => findBindingIssues(bindings), [bindings]);
  const dirty = status === 'ready' && baseline !== null && draft !== null && !areBindingsEqual(baseline, draft);
  const canSave = status === 'ready' && issues.every((issue) => issue === null);

  const setBindings = useCallback(
    (next: CommandBindingConfig[]) => {
      if (baseline) {
        setDraftState({ baseline, value: next });
      }
    },
    [baseline],
  );

  const save = useCallback(async () => {
    if (!agentId || !dirty || !canSave) {
      return;
    }
    const submitted = bindings;
    setSaving(true);
    try {
      const saved = await updateAgent(agentId, { command_bindings: toBindingsPayload(submitted) });
      const confirmed = (saved.command_bindings ?? []).map(normalizeBinding);
      setSnapshot({ agentId, generation, bindings: confirmed });
      // 请求期间用户若继续编辑，保留其最新草稿，只把它改为基于刚保存的快照。
      setDraftState((latest) =>
        latest && !areBindingsEqual(latest.value, submitted) ? { baseline: confirmed, value: latest.value } : null,
      );
    } finally {
      setSaving(false);
    }
  }, [agentId, bindings, canSave, dirty, generation]);

  return { unavailable, status, bindings, setBindings, issues, dirty, canSave, saving, save };
}
