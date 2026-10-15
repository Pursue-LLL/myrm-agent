import {
  ForkedSessionSnapshot,
  ReadOnlyCodeSnapshot,
  ReadOnlyStepSnapshot,
  SideTrackSession,
} from './sideTrackTypes';

/**
 * 根据当前主任务状态生成瞬时只读快照
 */
export function generateForkedSnapshot(
  mainSessionId: string,
  mainTaskName: string,
  activeStep?: ReadOnlyStepSnapshot,
  codeSnapshots: ReadOnlyCodeSnapshot[] = [],
  branchName: string = 'main'
): ForkedSessionSnapshot {
  return {
    mainSessionId,
    forkTimestamp: Date.now(),
    mainTaskName,
    activeStep,
    codeSnapshots,
    branchName,
    isUncommittedWorktree: true,
  };
}

/**
 * 根据快照内容智能生成推荐快速提问芯片 (Quick Inquiry Chips)
 */
export function generatePresetInquiries(
  activeStep?: ReadOnlyStepSnapshot,
  codeSnapshots: ReadOnlyCodeSnapshot[] = []
): string[] {
  const suggestions: string[] = [];

  if (activeStep?.toolAction) {
    suggestions.push(`解释当前执行动作 [${activeStep.toolAction}] 的底层原理与设计意图`);
  }

  if (codeSnapshots.length > 0) {
    const firstSnippet = codeSnapshots[0];
    suggestions.push(`分析 ${firstSnippet.filePath} 中核心逻辑的边界条件与并发安全性`);
    suggestions.push(`这段代码的时间/空间复杂度是多少？存在更优解吗？`);
  } else {
    suggestions.push('当前正在构建的模块整体架构设计是什么？');
    suggestions.push('如果底层网络连接超时，主任务将如何优雅重试？');
  }

  suggestions.push('主任务后台全速执行中，请解释当前阶段的关键交付目标');
  return suggestions.slice(0, 4);
}

/**
 * 构造轻量只读解释助手的上下文系统提示词
 */
export function buildSideTrackSystemPrompt(snapshot: ForkedSessionSnapshot): string {
  const stepInfo = snapshot.activeStep
    ? `当前步骤: ${snapshot.activeStep.stepTitle} (${snapshot.activeStep.toolAction || '执行中'})`
    : '当前步骤: 任务执行中';

  const filesInfo =
    snapshot.codeSnapshots.length > 0
      ? snapshot.codeSnapshots.map((f) => `- ${f.filePath} (${f.language})`).join('\n')
      : '暂无挂载文件';

  return `你是一个专用的只读架构与代码原理解释专家。
你挂载了主任务 [${snapshot.mainTaskName}] 的瞬时只读快照。
${stepInfo}
挂载工作区代码:
${filesInfo}

规则:
1. 你的回答仅用于解答用户的技术探索、原理好奇或架构决策疑问；
2. 严禁修改代码，你的解答不会注入主任务上下文，零上下文污染；
3. 输出严谨、高性能且清晰的技术分析，解释“为什么”而不是表面罗列。`;
}

/**
 * 初始化侧边探索分支会话
 */
export function createSideTrackSession(
  mainSessionId: string,
  mainTaskName: string,
  activeStep?: ReadOnlyStepSnapshot,
  codeSnapshots: ReadOnlyCodeSnapshot[] = []
): SideTrackSession {
  const snapshot = generateForkedSnapshot(
    mainSessionId,
    mainTaskName,
    activeStep,
    codeSnapshots
  );

  const presetInquiries = generatePresetInquiries(activeStep, codeSnapshots);

  const sideSessionId = `side-${mainSessionId.slice(-6)}-${Date.now().toString(36)}`;

  return {
    sideSessionId,
    mainSessionId,
    title: `侧边分支: 探索 ${activeStep?.stepTitle || mainTaskName}`,
    status: 'idle',
    snapshot,
    messages: [
      {
        id: `msg-welcome-${Date.now()}`,
        sender: 'system',
        content: `已从主任务「${mainTaskName}」成功 Fork 独立只读会话。主 Agent 正在后台全速运转，此处提问完全零上下文污染。`,
        timestamp: Date.now(),
      },
    ],
    presetInquiries,
  };
}

/**
 * 模拟生成原理解答 (用于纯前端离线测试或即时演示)
 */
export function generateLocalExplainerAnswer(
  query: string,
  snapshot: ForkedSessionSnapshot
): string {
  if (query.includes('并发') || query.includes('锁') || query.includes('安全')) {
    return `关于当前代码在并发场景下的分析：\n1. 状态由纯函数和不可变数据流驱动，避免了共享可变状态产生的竞态条件；\n2. 对于 I/O 密集型操作，采用非阻塞异步管线并配备幂等性保护；\n3. 主 Agent 处于无锁后台并发执行，本侧边会话仅以只读方式快照 AST，绝对安全。`;
  }

  if (query.includes('复杂度') || query.includes('性能')) {
    return `关于性能与复杂度评估：\n1. 核心查找索引的时间复杂度为 O(1)，空间占用为 O(N)；\n2. 内存占用严格受控在轻量缓冲区内，并在批处理完成后主动解引用触发 GC；\n3. 经过预研基准测试，处理 10,000 个节点耗时小于 12ms。`;
  }

  return `针对你的提问「${query}」进行深度原理解读：\n主任务当前阶段处于 [${snapshot.activeStep?.stepTitle || '核心构建'}]。该实现采用依赖倒置与单一职责设计，将复杂的执行逻辑解耦为领域引擎、响应式 Store 与展示层组件。主 Agent 此时正在继续自动化推进后续步骤，完全不受本问答影响。`;
}
