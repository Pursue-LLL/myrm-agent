import {
  ChannelFootprintItem,
  DigestStylePreset,
  WeeklyDigestSummary,
} from './weeklyDigestTypes';
import { getCategoryDisplayName } from './footprintAggregatorData';

export function synthesizeWeeklyDigest(
  items: ChannelFootprintItem[],
  options: {
    weekIdentifier?: string;
    stylePreset?: DigestStylePreset;
  } = {}
): WeeklyDigestSummary {
  const weekIdentifier = options.weekIdentifier || '2026-W36';
  const stylePreset = options.stylePreset || 'executive';

  const includedItems = items.filter((item) => item.includedInDigest);

  const accomplishments: string[] = [];
  const keyDecisions: string[] = [];
  const codeLearnings: string[] = [];
  const pendingRisks: string[] = [];
  const nextSteps: string[] = [];

  for (const item of includedItems) {
    const formattedEntry = item.metrics
      ? `${item.title} —— ${item.description} [关键指标: ${item.metrics}]`
      : `${item.title} —— ${item.description}`;

    if (item.category === 'deliverable' || item.category === 'pr-review') {
      accomplishments.push(formattedEntry);
    } else if (item.category === 'rfc-decision') {
      keyDecisions.push(formattedEntry);
    } else if (item.category === 'learning') {
      codeLearnings.push(formattedEntry);
    } else if (item.category === 'risk-roadblock') {
      pendingRisks.push(formattedEntry);
      nextSteps.push(`针对 ${item.title} 落实风险防御与应急预案`);
    }
  }

  if (accomplishments.length > 0) {
    nextSteps.unshift('跟进已交付特性的线上灰度观测与用户反馈收集');
  }

  const markdownContent = renderDigestMarkdown({
    weekIdentifier,
    stylePreset,
    accomplishments,
    keyDecisions,
    codeLearnings,
    pendingRisks,
    nextSteps,
  });

  return {
    id: `digest-${weekIdentifier}-${Date.now()}`,
    weekIdentifier,
    dateRange: '本周工作周期 (周一 至 周五)',
    stylePreset,
    accomplishments,
    keyDecisions,
    codeLearnings,
    pendingRisks,
    nextSteps,
    markdownContent,
    synthesizedAt: Date.now(),
  };
}

interface RenderParams {
  weekIdentifier: string;
  stylePreset: DigestStylePreset;
  accomplishments: string[];
  keyDecisions: string[];
  codeLearnings: string[];
  pendingRisks: string[];
  nextSteps: string[];
}

function renderDigestMarkdown(params: RenderParams): string {
  const {
    weekIdentifier,
    stylePreset,
    accomplishments,
    keyDecisions,
    codeLearnings,
    pendingRisks,
    nextSteps,
  } = params;

  if (stylePreset === 'bullet') {
    return [
      `# 工作简报 · ${weekIdentifier}`,
      '## 核心产出',
      ...accomplishments.map((item) => `- ${item}`),
      '## 决策与思考',
      ...keyDecisions.map((item) => `- ${item}`),
      '## 风险与下一步',
      ...pendingRisks.map((item) => `- [风险] ${item}`),
      ...nextSteps.map((item) => `- [行动] ${item}`),
    ].join('\n');
  }

  if (stylePreset === 'technical') {
    return [
      `# 研发工作周报与技术复盘 (${weekIdentifier})`,
      '### 一、核心功能交付与代码评审 (Deliverables & Reviews)',
      ...accomplishments.map((item) => `* **${item.split('——')[0].trim()}**\n  > ${item}`),
      '### 二、架构设计与 RFC 关键决策 (Architecture Decisions)',
      ...keyDecisions.map((item) => `* ${item}`),
      '### 三、踩坑沉淀与工程经验 (Code Learnings)',
      ...codeLearnings.map((item) => `* ${item}`),
      '### 四、技术卡点与待决风险 (Technical Blockers)',
      ...pendingRisks.map((item) => `* ⚠️ ${item}`),
      '### 五、下周核心技术规划 (Next Sprint Commitments)',
      ...nextSteps.map((item) => `1. ${item}`),
    ].join('\n\n');
  }

  // 默认高管审阅级 (Executive Summary)
  return [
    `# 工作复盘周报 · ${weekIdentifier} (高管审阅版)`,
    '## 1. 本周核心业务与产品成果',
    ...accomplishments.map((item, idx) => `${idx + 1}. **${item.split('——')[0].trim()}**\n   ${item}`),
    '## 2. 重大技术与方案决策',
    ...keyDecisions.map((item) => `- ${item}`),
    '## 3. 经验沉淀与质效改进',
    ...codeLearnings.map((item) => `- ${item}`),
    '## 4. 潜在风险与防御保障',
    ...pendingRisks.map((item) => `- ⚠️ ${item}`),
    '## 5. 下周明确承诺与落地规划',
    ...nextSteps.map((item, idx) => `${idx + 1}. ${item}`),
  ].join('\n\n');
}

export function applyRefinementInstruction(
  digest: WeeklyDigestSummary,
  instruction: string
): WeeklyDigestSummary {
  const trimmed = instruction.trim().toLowerCase();
  let nextStyle: DigestStylePreset = digest.stylePreset;

  if (trimmed.includes('极简') || trimmed.includes('短') || trimmed.includes('速览')) {
    nextStyle = 'bullet';
  } else if (trimmed.includes('技术') || trimmed.includes('架构') || trimmed.includes('代码')) {
    nextStyle = 'technical';
  } else if (trimmed.includes('高管') || trimmed.includes('业务') || trimmed.includes('收益')) {
    nextStyle = 'executive';
  }

  const refinedMarkdown = renderDigestMarkdown({
    weekIdentifier: digest.weekIdentifier,
    stylePreset: nextStyle,
    accomplishments: digest.accomplishments,
    keyDecisions: digest.keyDecisions,
    codeLearnings: digest.codeLearnings,
    pendingRisks: digest.pendingRisks,
    nextSteps: digest.nextSteps,
  });

  return {
    ...digest,
    stylePreset: nextStyle,
    markdownContent: `<!-- 微调指令: ${instruction} -->\n${refinedMarkdown}`,
    synthesizedAt: Date.now(),
  };
}
