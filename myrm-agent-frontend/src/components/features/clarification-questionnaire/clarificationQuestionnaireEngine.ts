import {
  ClarificationAttachment,
  QuestionOption,
  QuestionnaireQuestion,
  V1SpecContract,
} from './clarificationQuestionnaireTypes';

export const DEFAULT_CLARIFICATION_QUESTIONS: QuestionnaireQuestion[] = [
  {
    id: 'q-shape',
    title: '1. 您期望的目标运行形态是怎样的？',
    description: '运行环境决定了技术栈和部署复杂度',
    isMultiSelect: false,
    options: [
      {
        id: 'opt-spa',
        label: '单页本地 Web 应用 (开箱即用)',
        isRecommended: true,
        description: '无需复杂后端，浏览器直接打开运行，轻巧高效',
        nonGoalTag: '不搭建独立微服务容器',
      },
      {
        id: 'opt-cli',
        label: '轻量命令行 CLI 工具',
        isRecommended: false,
        description: '终端键入命令直接交互，适合极客与自动化批处理',
      },
      {
        id: 'opt-fullstack',
        label: '全栈前后端分离系统',
        isRecommended: false,
        description: '包含独立 Server、ORM 与数据库，适合团队多人协作',
      },
    ],
    selectedOptionIds: ['opt-spa'],
    attachments: [],
  },
  {
    id: 'q-complexity',
    title: '2. 系统的核心业务复杂度与功能范围？',
    description: '明确首发 MVP 范围，避免战线拉长',
    isMultiSelect: false,
    options: [
      {
        id: 'opt-mvp-calc',
        label: '聚焦核心参数录入与即时计算汇总',
        isRecommended: true,
        description: '仅做最关键的公式推导、配置项录入与结果清单呈现',
        nonGoalTag: '不做复杂审批流、财务发票对账与在线支付',
      },
      {
        id: 'opt-full-workflow',
        label: '包含工单审批流与多角色流转',
        isRecommended: false,
        description: '涉及不同部门的角色权限、状态机流转与审计留痕',
      },
    ],
    selectedOptionIds: ['opt-mvp-calc'],
    attachments: [],
  },
  {
    id: 'q-storage',
    title: '3. 数据的存储与持久化偏好？',
    description: '选择数据保存方式',
    isMultiSelect: false,
    options: [
      {
        id: 'opt-local-storage',
        label: '本地浏览器存储 (LocalStorage / IndexedDB)',
        isRecommended: true,
        description: '数据完全留在本地，无隐私外泄风险，一键导出 JSON / CSV',
        nonGoalTag: '不依赖外部云端数据库与账号体系',
      },
      {
        id: 'opt-cloud-db',
        label: '云端数据库存储 (SQLite / Postgres)',
        isRecommended: false,
        description: '支持多设备云端同步与远程查询',
      },
    ],
    selectedOptionIds: ['opt-local-storage'],
    attachments: [],
  },
  {
    id: 'q-non-goals',
    title: '4. 本轮首发版本明确排除的不做项 (Non-goals)？',
    description: '克制需求范围，拦截过度设计',
    isMultiSelect: true,
    options: [
      {
        id: 'opt-exclude-auth',
        label: '排除复杂多租户与用户鉴权登录',
        isRecommended: true,
        description: '无需注册密码找回流程，直接使用',
        nonGoalTag: '不写多租户鉴权中间件',
      },
      {
        id: 'opt-exclude-pdf',
        label: '排除重型 PDF 排版生成与打印机驱动适配',
        isRecommended: true,
        description: '优先提供清晰 Web 表格和标准 CSV 导出',
        nonGoalTag: '不引入重型 PDF 渲染引擎',
      },
      {
        id: 'opt-exclude-i18n',
        label: '排除多国语言国际化适配 (仅保留单一母语)',
        isRecommended: false,
        description: '首发版本专注核心业务逻辑',
        nonGoalTag: '不建多语言本地化资源包',
      },
    ],
    selectedOptionIds: ['opt-exclude-auth', 'opt-exclude-pdf'],
    attachments: [],
  },
];

export function parseQuestionOption(rawText: string, index: number): QuestionOption {
  const isRecommended =
    rawText.includes('(推荐)') ||
    rawText.includes('（推荐）') ||
    rawText.toLowerCase().includes('[recommended]');

  const cleanLabel = rawText
    .replace(/\(推荐\)|（推荐\)|\[recommended\]/gi, '')
    .trim();

  return {
    id: `opt-parsed-${index}-${Math.random().toString(36).substring(2, 6)}`,
    label: cleanLabel,
    isRecommended,
  };
}

export function autoApplyAllRecommendations(
  questions: QuestionnaireQuestion[]
): QuestionnaireQuestion[] {
  return questions.map((q) => {
    const recommendedOpts = q.options.filter((opt) => opt.isRecommended);
    if (recommendedOpts.length === 0) {
      return q;
    }

    if (q.isMultiSelect) {
      return {
        ...q,
        selectedOptionIds: recommendedOpts.map((opt) => opt.id),
      };
    }

    const firstRec = recommendedOpts[0];
    return {
      ...q,
      selectedOptionIds: firstRec ? [firstRec.id] : [],
    };
  });
}

export function synthesizeV1Spec(questions: QuestionnaireQuestion[]): V1SpecContract {
  let productShape = '标准单页应用 (Single Page Application)';
  const coreCapabilities: string[] = [];
  const nonGoals: string[] = [];
  let totalAnswered = 0;

  for (const q of questions) {
    const hasSelection = q.selectedOptionIds.length > 0;
    const hasCustomText = Boolean(q.customTextAnswer && q.customTextAnswer.trim() !== '');
    const hasAttachments = q.attachments.length > 0;

    if (hasSelection || hasCustomText || hasAttachments) {
      totalAnswered += 1;
    }

    for (const optId of q.selectedOptionIds) {
      const opt = q.options.find((o) => o.id === optId);
      if (!opt) {
        continue;
      }

      if (q.id === 'q-shape' || opt.label.includes('形态') || opt.label.includes('应用')) {
        productShape = opt.label;
      } else {
        coreCapabilities.push(opt.label);
      }

      if (opt.nonGoalTag) {
        nonGoals.push(opt.nonGoalTag);
      }
    }

    if (hasCustomText && q.customTextAnswer) {
      coreCapabilities.push(`补充细节: ${q.customTextAnswer.trim()}`);
    }

    if (hasAttachments) {
      const attNames = q.attachments.map((a) => a.name).join(', ');
      coreCapabilities.push(`附带参考材料: [${attNames}]`);
    }
  }

  // 整理汇总后的结构化 Prompt
  const summaryLines: string[] = [
    '【克制 V1 需求规范与目标对齐协议 (Spec Lock-in)】',
    `- 目标运行形态: ${productShape}`,
    `- 核心首发功能范围: ${coreCapabilities.length > 0 ? coreCapabilities.join('；') : '基础核心业务流'}`,
    `- 明确排除不做项 (Non-goals): ${nonGoals.length > 0 ? nonGoals.join('；') : '不引入过度设计'}`,
    '请严格依据上述克制 V1 范围推进代码落地，绝不擅自扩大战线。',
  ];

  return {
    productShape,
    coreCapabilities,
    nonGoals,
    generatedPromptText: summaryLines.join('\n'),
    totalAnswered,
  };
}

export interface ReadyCheckResult {
  isReady: boolean;
  unfulfilledIndex: number;
  reason?: string;
}

export function isQuestionnaireReadyToSubmit(
  questions: QuestionnaireQuestion[]
): ReadyCheckResult {
  for (let idx = 0; idx < questions.length; idx += 1) {
    const q = questions[idx];
    if (!q) {
      continue;
    }

    const hasSelection = q.selectedOptionIds.length > 0;
    const hasCustomText = Boolean(q.customTextAnswer && q.customTextAnswer.trim() !== '');

    if (!hasSelection && !hasCustomText) {
      return {
        isReady: false,
        unfulfilledIndex: idx,
        reason: `问题 "${q.title}" 尚未做出选择或补充输入`,
      };
    }

    // 检查是否有正在上传中的附件
    const uploadingAttachment = q.attachments.find((att: ClarificationAttachment) => att.uploadStatus === 'uploading');
    if (uploadingAttachment) {
      return {
        isReady: false,
        unfulfilledIndex: idx,
        reason: `问题 "${q.title}" 存在正在上传的文件 [${uploadingAttachment.name}]，请等待完成`,
      };
    }
  }

  return {
    isReady: true,
    unfulfilledIndex: -1,
  };
}
