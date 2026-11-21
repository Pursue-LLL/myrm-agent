/**
 * [INPUT]
 * - ./turnCapabilityOverrideCore::TurnCapabilitySelection (POS: 本轮能力覆写的 Skill / MCP 子集)
 * - @/store/chat/types::AgentConfig (POS: 会话级 Agent 配置，提供能力基线)
 *
 * [OUTPUT]
 * - useTurnCapabilitySelection: 输入区暂存的「仅本轮」能力覆写及其消费
 *
 * [POS]
 * 聊天输入业务 Hook 的单轮能力部分：覆写只属于做出它的会话与能力基线，会话或基线一变就作废；提交时消费一次。
 */

import { useCallback, useState } from 'react';
import type { AgentConfig } from '@/store/chat/types';
import type { TurnCapabilitySelection } from './turnCapabilityOverrideCore';

interface HeldSelection {
  /** 做出这个覆写时的会话与能力基线。 */
  scopeKey: string;
  selection: TurnCapabilitySelection | null;
}

export function useTurnCapabilitySelection(chatId: string | undefined, agentConfig: AgentConfig | null) {
  const scopeKey = JSON.stringify([
    chatId ?? null,
    agentConfig?.agentId ?? null,
    agentConfig?.selectedSkillIds ?? [],
    agentConfig?.selectedMcpNames ?? [],
  ]);
  const [held, setHeld] = useState<HeldSelection>({ scopeKey, selection: null });

  // 作用域一变，在这次渲染里就清掉旧覆写（不经 effect），也就不会有一帧把旧会话的覆写显示给新会话；
  // 回到旧作用域时它也不会复活，因为已经被清掉。
  if (held.scopeKey !== scopeKey) {
    setHeld({ scopeKey, selection: null });
  }
  const turnCapabilitySelection = held.scopeKey === scopeKey ? held.selection : null;

  // 已离开的作用域留下的旧 setter 写进来的值，会在下一次渲染被上面的判断丢弃。
  const setTurnCapabilitySelection = useCallback(
    (selection: TurnCapabilitySelection | null) => setHeld({ scopeKey, selection }),
    [scopeKey],
  );

  const consumeTurnCapabilitySelection = useCallback(() => {
    if (!turnCapabilitySelection) {
      return null;
    }
    setHeld({ scopeKey, selection: null });
    return turnCapabilitySelection;
  }, [scopeKey, turnCapabilitySelection]);

  return { turnCapabilitySelection, setTurnCapabilitySelection, consumeTurnCapabilitySelection };
}
