import {
  MainTaskProgressInfo,
  SideChatMessage,
  SteeringBufferItem,
  SteeringIntentType,
} from './sideChatTypes';

export function classifySideChatIntent(input: string): SteeringIntentType {
  const text = input.trim().toLowerCase();

  const statusKeywords = [
    '进度',
    '到哪一步',
    '状态',
    '在干什么',
    '还在跑吗',
    '还剩多久',
    '完成了没',
    'status',
    'progress',
    'what step',
  ];
  for (const kw of statusKeywords) {
    if (text.includes(kw)) {
      return 'status_inquiry';
    }
  }

  const featureKeywords = [
    '加个',
    '增加',
    '支持',
    '新增',
    '顺手加',
    '顺便加',
    '还要加',
    '加一个',
    'add',
    'feature',
    'export',
    '导出',
  ];
  for (const kw of featureKeywords) {
    if (text.includes(kw)) {
      return 'incremental_feature';
    }
  }

  const paramKeywords = [
    '改成',
    '修改为',
    '参数',
    '配置',
    '系数',
    '阈值',
    '调成',
    'override',
    'param',
    'config',
  ];
  for (const kw of paramKeywords) {
    if (text.includes(kw)) {
      return 'parameter_override';
    }
  }

  return 'general_note';
}

export function generateInstantCollaboratorReply(
  intent: SteeringIntentType,
  input: string,
  mainTask: MainTaskProgressInfo
): string {
  if (intent === 'status_inquiry') {
    if (mainTask.status === 'idle') {
      return '当前主任务处于空闲状态，未在沙箱中执行长任务。';
    }
    return `[协作者即时同步] 主任务当前正处于第 ${mainTask.currentStep}/${mainTask.totalSteps} 步：${mainTask.currentStepDescription}。沙箱运行正常，无需打断主线。`;
  }

  if (intent === 'incremental_feature') {
    return `[微调队列已签收] 已将增量需求 “${input}” 挂入非阻塞缓冲队列。主 Agent 完成当前原子操作后将自动吸收并无缝接入，主沙箱持续运行中。`;
  }

  if (intent === 'parameter_override') {
    return `[参数覆写已挂起] 已捕捉到新的配置意图 “${input}”，将在下一个 step 触发上下文热加载并更新对应参数。`;
  }

  return `[支线备忘已记录] 已为您记录补充要求：“${input}”，将在主任务验收前统一对齐检查。`;
}

export function createSteeringItemFromMessage(message: SideChatMessage): SteeringBufferItem {
  const priority =
    message.intentType === 'parameter_override'
      ? 10
      : message.intentType === 'incremental_feature'
      ? 8
      : 5;

  return {
    id: `steering-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`,
    sourceMessageId: message.id,
    intentType: message.intentType || 'general_note',
    content: message.content,
    priority,
    status: 'pending',
    createdAt: Date.now(),
  };
}

export function formatSteeringQueueForMainAgent(items: SteeringBufferItem[]): string {
  const pendingItems = items.filter((i) => i.status === 'pending');
  if (pendingItems.length === 0) {
    return '';
  }

  const lines = pendingItems.map((item, idx) => {
    const tag =
      item.intentType === 'incremental_feature'
        ? '[增量需求]'
        : item.intentType === 'parameter_override'
        ? '[参数覆写]'
        : '[补充备忘]';
    return `${idx + 1}. ${tag} ${item.content}`;
  });

  return [
    '【非阻塞支线补充调优指令 (Steering Injection)】',
    '用户在任务执行期间通过 Side Chat 补充了以下要求，请在当前步骤完成后无缝平滑吸收，无需中断整体进度：',
    ...lines,
  ].join('\n');
}
