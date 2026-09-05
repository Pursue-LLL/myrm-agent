export const OAUTH_POLL_INTERVAL_MS = 2000;
export const OAUTH_POLL_TIMEOUT_MS = 600_000;

export type OauthIntegration = {
  id: string;
  name: string;
  desc: string;
  descZh: string;
  category: string;
  oauthFlow?: 'google_workspace' | 'xai_device_code';
};

export type OauthCredentialRecord = {
  issuer: string;
  user_id?: string;
  scope?: string;
  expires_at?: number;
  connected?: boolean;
};

export const SUPPORTED_INTEGRATIONS: OauthIntegration[] = [
  {
    id: 'google_workspace',
    name: 'Google Workspace',
    desc: 'Calendar, Gmail, and Drive via OAuth',
    descZh: '通过 OAuth 连接 Google 日历、Gmail 与云端硬盘',
    category: 'productivity',
    oauthFlow: 'google_workspace' as const,
  },
  {
    id: 'xai',
    name: 'xAI / SuperGrok',
    desc: 'Use your SuperGrok subscription for Grok chat models, X (Twitter) search, and multimodal generation',
    descZh: '使用 SuperGrok 订阅驱动 Grok 对话模型、X (Twitter) 实时搜索与多模态生成',
    category: 'productivity',
    oauthFlow: 'xai_device_code' as const,
  },
  {
    id: 'feishu',
    name: 'Feishu / 飞书',
    desc: 'Sync docs, messages, and automate tasks',
    descZh: '同步飞书文档、消息及执行自动化任务',
    category: 'communication',
  },
  {
    id: 'dingtalk',
    name: 'DingTalk / 钉钉',
    desc: 'Automate messages, work items, and workflows',
    descZh: '同步钉钉消息、工作项及审批流',
    category: 'communication',
  },
  {
    id: 'github',
    name: 'GitHub',
    desc: 'Manage repositories, issues, and PRs',
    descZh: '管理 GitHub 代码库、Issues 及 Pull Requests',
    category: 'development',
  },
  {
    id: 'jira',
    name: 'Jira',
    desc: 'Sync issues, backlogs, and agile boards',
    descZh: '同步 Jira 问题、待办事项及敏捷看板',
    category: 'productivity',
  },
  {
    id: 'slack',
    name: 'Slack',
    desc: 'Send channel alerts and automate team chat',
    descZh: '发送 Slack 渠道提醒并自动化团队沟通',
    category: 'communication',
  },
];
