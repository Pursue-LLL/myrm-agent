import {
  ComparisonFeature,
  PlaybookCategory,
  PlaybookScenario,
} from './nonCodingPlaybookTypes';

/**
 * 组装参数化填装生成的 Prompt 文本
 */
export function generatePrefilledPrompt(
  scenario: PlaybookScenario,
  values: Record<string, string>,
): string {
  let result = scenario.defaultPromptTemplate;

  for (const field of scenario.parameters) {
    const val = values[field.id] ?? field.defaultValue ?? '';
    const placeholderRegex = new RegExp(`{{${field.id}}}`, 'g');
    result = result.replace(placeholderRegex, val);
  }

  return result.trim();
}

/**
 * 按分类过滤非编码工作流剧本
 */
export function filterPlaybooksByCategory(
  scenarios: PlaybookScenario[],
  category: PlaybookCategory | 'all' = 'all',
): PlaybookScenario[] {
  if (category === 'all') {
    return scenarios;
  }
  return scenarios.filter((s) => s.category === category);
}

/**
 * 关键字多维检索剧本（标题、描述、工具、输出）
 */
export function searchPlaybooks(
  scenarios: PlaybookScenario[],
  keyword: string,
): PlaybookScenario[] {
  const safeKeyword = keyword.trim().toLowerCase();
  if (!safeKeyword) {
    return scenarios;
  }

  return scenarios.filter((s) => {
    const titleMatch = s.title.toLowerCase().includes(safeKeyword);
    const descMatch = s.description.toLowerCase().includes(safeKeyword);
    const outputMatch = s.expectedOutput.toLowerCase().includes(safeKeyword);
    const toolMatch = s.toolsUsed.some((t) =>
      t.toLowerCase().includes(safeKeyword),
    );
    return titleMatch || descMatch || outputMatch || toolMatch;
  });
}

/**
 * 获取业务分类对应的标签与徽标配色
 */
export function getCategoryMeta(category: PlaybookCategory): {
  label: string;
  badgeClass: string;
} {
  switch (category) {
    case 'finance':
      return {
        label: '财务发票',
        badgeClass:
          'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
      };
    case 'admin':
      return {
        label: '行政办公',
        badgeClass:
          'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20',
      };
    case 'research':
      return {
        label: '研报分析',
        badgeClass:
          'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20',
      };
    case 'legal':
      return {
        label: '合同法务',
        badgeClass:
          'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20',
      };
    case 'content':
      return {
        label: '媒体创作',
        badgeClass:
          'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
      };
    default:
      return {
        label: '通用生产力',
        badgeClass: 'bg-muted text-muted-foreground border-border/40',
      };
  }
}

/**
 * 纯网页 Chat vs Myrm Agent 核心价值维度对比
 */
export const STATIC_COMPARISON_FEATURES: ComparisonFeature[] = [
  {
    id: 'comp-1',
    title: '本地文件与办公文档实操',
    rawWebChat: '仅支持单次上传文本/图片，无法在本地生成并写入真实格式文件',
    myrmAgent: '直连沙箱与本地工作区，直接创建、解析并修改真实 Excel / PPT / Word',
    advantageDetail:
      '发票汇总可直接生成格式美观带公式的 xlsx 文件并写入本地指定目录。',
  },
  {
    id: 'comp-2',
    title: '复杂数据计算与真实验证',
    rawWebChat: '依赖纯语言概率续写，计算公式极易出现大模型“幻觉”算错',
    myrmAgent: '调用真实隔离 Python 环境运行实际代码运算，绝不脑补虚假数字',
    advantageDetail: '百万级数据求和、统计方差与财税比对 100% 精确。',
  },
  {
    id: 'comp-3',
    title: '长效团队持久记忆与背景认知',
    rawWebChat: '每次新建聊天都是一张白纸，必须重新复制长篇公司规范与偏好',
    myrmAgent: '自带企业与项目活事实账本 (Living Fact Ledger)，自动继承上下文',
    advantageDetail: '记住常用开票抬头、审批层级与业务黑名单，免去反复告知。',
  },
  {
    id: 'comp-4',
    title: '多智能体分工与全双工长任务',
    rawWebChat: '单线程阻塞，遇长任务必须死等转圈，无法离开或继续提问',
    myrmAgent: '前台对话永不卡顿，后台多 Worker 并发运行，成果就绪智能插播',
    advantageDetail: '一边整理 50 份合同，一边继续向主助手提问，互不干扰。',
  },
];
