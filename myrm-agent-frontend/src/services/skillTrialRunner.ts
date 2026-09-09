/**
 * [INPUT]
 * - skillId, skillName, description, examples (POS: 技能基础元数据)
 * - useChatStore.setInputMessage (POS: 会话输入草稿预填)
 *
 * [OUTPUT]
 * - getSkillSmokeTestPrompt: 获取技能冒烟测试提示词
 * - launchSkillTrialRun: 启动技能沙箱试跑交互流程
 *
 * [POS]
 * 技能市场试跑引导层。为新安装技能提供预置的冒烟模板与快速引导能力，
 * 帮助用户在沙箱会话中一键执行端到端技能功能验证。
 */

import useChatStore from '@/store/useChatStore';

/**
 * 经典技能类型的冒烟测试模板映射
 */
const KNOWN_SKILL_SMOKE_TEMPLATES: Record<string, { zh: string; en: string }> = {
  'host-server-ops': {
    zh: '请调用 host-server-ops 技能，对我当前所在主机进行一次快速健康与资源利用率只读巡检。',
    en: 'Please use the host-server-ops skill to run a quick, read-only health and resource utilization check on my host system.',
  },
  'office-document': {
    zh: '请调用 office-document 技能，生成一份包含示例收支数据与柱状图的 Excel 演示表格。',
    en: 'Please use the office-document skill to generate a sample Excel spreadsheet with financial numbers and a chart.',
  },
  'data-analysis-pipeline': {
    zh: '请使用 data-analysis-pipeline 技能，对给定的样本数据进行描述性统计并输出核心指标分布。',
    en: 'Please use data-analysis-pipeline skill to perform descriptive statistics on sample data and output key distributions.',
  },
  'deep-research': {
    zh: '请使用 deep-research 技能，围绕 2026 年最新大模型推理发展趋势进行一次快速概览调研。',
    en: 'Please use deep-research skill to conduct a quick overview research on the latest LLM reasoning trends in 2026.',
  },
  'pdf-generator': {
    zh: '请使用 pdf-generator 技能，制作一份版面规范的单页项目立项备忘录 PDF 文档。',
    en: 'Please use pdf-generator skill to create a well-formatted one-page project charter memo in PDF.',
  },
  'web-scraping': {
    zh: '请使用 web-scraping 技能，抓取示例网页结构并提取主要标题与链接摘要。',
    en: 'Please use web-scraping skill to extract key headings and link summaries from a target webpage.',
  },
};

export interface SkillTrialRunOptions {
  skillId: string;
  skillName: string;
  description?: string;
  examplePrompt?: string;
  lang?: string;
  onNavigate?: () => void;
}

/**
 * 解析并生成技能的推荐冒烟测试 Prompt
 */
export function getSkillSmokeTestPrompt(options: {
  skillId: string;
  skillName: string;
  description?: string;
  examplePrompt?: string;
  lang?: string;
}): string {
  if (options.examplePrompt && options.examplePrompt.trim().length > 0) {
    return options.examplePrompt.trim();
  }

  const isZh = (options.lang || 'zh').toLowerCase().includes('zh');
  const matched = KNOWN_SKILL_SMOKE_TEMPLATES[options.skillId];
  if (matched) {
    return isZh ? matched.zh : matched.en;
  }

  // 通用兜底模板
  if (isZh) {
    return `请调用已安装的技能【${options.skillName}】（ID: ${options.skillId}），进行一次基础功能测试与冒烟试跑，验证其执行正常。`;
  }
  return `Please invoke the newly installed skill "${options.skillName}" (ID: ${options.skillId}) to run a basic smoke test and verify its execution.`;
}

/**
 * 触发技能试跑流程：
 * 1. 自动组装冒烟测试提示词
 * 2. 写入全局输入框草稿 (setInputMessage)
 * 3. 执行导航回调跳转到聊天界面
 */
export function launchSkillTrialRun(options: SkillTrialRunOptions): string {
  const prompt = getSkillSmokeTestPrompt(options);
  const { setInputMessage } = useChatStore.getState();
  setInputMessage(prompt);

  if (options.onNavigate) {
    options.onNavigate();
  }

  return prompt;
}
