import {
  BargeInSensitivity,
  BargeInState,
  DuplexSessionStatus,
  DuplexTurnMessage,
} from './duplexVoiceTypes';

/**
 * 根据灵敏度返回触发打断的音量门限 (0 - 100)
 */
export function getBargeInVolumeThreshold(sensitivity: BargeInSensitivity): number {
  switch (sensitivity) {
    case 'high': {
      return 25;
    }
    case 'medium': {
      return 45;
    }
    case 'low': {
      return 65;
    }
    default: {
      return 45;
    }
  }
}

/**
 * 判定是否触发 Barge-In 随时插话打断
 */
export function shouldTriggerBargeIn(
  status: DuplexSessionStatus,
  micVolume: number,
  sensitivity: BargeInSensitivity
): boolean {
  if (status !== 'speaking') {
    return false;
  }
  const threshold = getBargeInVolumeThreshold(sensitivity);
  return micVolume >= threshold;
}

/**
 * 上下文自愈算法：平滑剪裁被插话截断的 Agent 回复，构造统一上下文自愈预览
 */
export function healContextOnBargeIn(
  currentAgentSpeech: string,
  userSpeechSnippet: string,
  interruptedCharIndex?: number
): BargeInState {
  const safeIndex =
    typeof interruptedCharIndex === 'number' && interruptedCharIndex > 0
      ? interruptedCharIndex
      : currentAgentSpeech.length;

  const deliveredAgentContent = currentAgentSpeech.slice(0, safeIndex).trim();
  const cleanUserSpeech = userSpeechSnippet.trim();

  const healedContextPreview = deliveredAgentContent
    ? `[系统已在第 ${safeIndex} 字执行毫秒级中断] 智能体已交付：「${deliveredAgentContent}」；用户插话纠偏：「${cleanUserSpeech}」`
    : `[智能体开头发言即被即时打断] 用户直接指示：「${cleanUserSpeech}」`;

  return {
    active: true,
    interruptedAt: Date.now(),
    interruptedAgentMessage: deliveredAgentContent,
    userInterruptionSnippet: cleanUserSpeech,
    healedContextPreview,
  };
}

/**
 * 将打断事件沉淀为对齐的消息历史
 */
export function finalizeInterruptedTurn(
  messages: DuplexTurnMessage[],
  deliveredAgentContent: string,
  userCorrection: string
): DuplexTurnMessage[] {
  const nextMessages: DuplexTurnMessage[] = [...messages];

  // 1. 如果有 Agent 已经说出的部分，记录为被截断的消息
  if (deliveredAgentContent) {
    nextMessages.push({
      id: `msg-agent-interrupted-${Date.now()}`,
      role: 'agent',
      content: deliveredAgentContent,
      wasInterrupted: true,
      interruptedAtPosition: deliveredAgentContent.length,
      timestamp: Date.now() - 100,
    });
  }

  // 2. 插入用户的纠偏打断指令
  if (userCorrection) {
    nextMessages.push({
      id: `msg-user-bargein-${Date.now()}`,
      role: 'user',
      content: userCorrection,
      timestamp: Date.now(),
    });
  }

  return nextMessages;
}

/**
 * 计算波形条高度百分比 (0 - 100)
 */
export function normalizeWaveformHeights(
  volume: number,
  barsCount: number = 12
): number[] {
  const clamped = Math.max(0, Math.min(100, volume));
  const baseScale = clamped / 100;

  return Array.from({ length: barsCount }, (_, idx) => {
    // 模拟中间高两边稍低的自然声波曲线
    const centerFactor = 1 - Math.abs(idx - (barsCount - 1) / 2) / (barsCount / 2);
    const variance = (idx % 3 === 0 ? 0.9 : 1.1);
    const height = Math.round(15 + 85 * baseScale * centerFactor * variance);
    return Math.max(12, Math.min(100, height));
  });
}
