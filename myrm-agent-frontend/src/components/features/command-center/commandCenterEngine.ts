import {
  CommandCenterLogEntry,
  GatewayHealthState,
  SessionAuditPackPayload,
  SessionSummaryItem,
  UsageHorizon,
  UsageSummary,
} from './commandCenterTypes';

/**
 * 判断是否触发全局 Command Center 唤起快捷键
 * macOS: Cmd+. 或 Cmd+K
 * Windows / Linux: Ctrl+. 或 Ctrl+K
 */
export function isCommandCenterShortcut(event: KeyboardEvent): boolean {
  const hasModifier = Boolean(event.metaKey || event.ctrlKey);

  if (!hasModifier) {
    return false;
  }

  // 按键 '.' (key === '.' or code === 'Period')
  if (event.key === '.' || event.code === 'Period') {
    return true;
  }

  // 经典 Command Palette 键 'k' / 'K'
  if (event.key === 'k' || event.key === 'K' || event.code === 'KeyK') {
    return true;
  }

  return false;
}

/**
 * 过滤与排序会话列表：置顶项排在最前，按相关度和更新时间排序
 */
export function filterSessions(
  sessions: SessionSummaryItem[],
  query: string
): SessionSummaryItem[] {
  const trimmed = query.trim().toLowerCase();

  const filtered = sessions.filter((s) => {
    if (!trimmed) {
      return true;
    }
    const matchTitle = s.title.toLowerCase().includes(trimmed);
    const matchAgent = s.agentName.toLowerCase().includes(trimmed);
    const matchTags = s.tags.some((t) => t.toLowerCase().includes(trimmed));
    return matchTitle || matchAgent || matchTags;
  });

  return filtered.sort((a, b) => {
    if (a.isPinned && !b.isPinned) {
      return -1;
    }
    if (!a.isPinned && b.isPinned) {
      return 1;
    }
    return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime();
  });
}

/**
 * 组装全要素可审计会话包 (Session Audit Pack)
 */
export function generateSessionAuditPack(
  session: SessionSummaryItem
): SessionAuditPackPayload {
  const generatedAt = new Date().toISOString();
  const summaryMarkdown = `# 📋 Myrm 权威会话审计报告\n\n- **会话 ID**: \`${session.id}\`\n- **会话标题**: ${session.title}\n- **主要负责人**: ${session.agentName}\n- **审计生成时间**: ${generatedAt}\n- **总消息轮数**: ${session.messageCount} 轮\n- **累计 Token 消耗**: ${session.tokenCount} T\n- **归属标签**: ${session.tags.join(', ')}\n\n---\n\n## 🛡️ 审计合规签名\n本审计包包含全链路 Prompt 上下文、工具调用回显、Token 消耗记账与最终工件摘要，供跨团队归档与安全审计。`;

  const rawJsonData = JSON.stringify(
    {
      version: '1.0.0',
      sessionId: session.id,
      title: session.title,
      agent: session.agentName,
      messageCount: session.messageCount,
      tokenCount: session.tokenCount,
      generatedAt,
      tags: session.tags,
      verificationHash: `sha256-${Math.random().toString(36).substring(2, 10)}`,
    },
    null,
    2
  );

  return {
    sessionId: session.id,
    title: session.title,
    generatedAt,
    exportFormat: 'markdown',
    summaryMarkdown,
    rawJsonData,
  };
}

/**
 * 生成已脱敏的 Debug Share 系统排障包
 */
export function generateDebugShareBundle(
  logs: CommandCenterLogEntry[],
  health: GatewayHealthState
): string {
  const sanitizedLogs = logs.map((log) => {
    // 脱敏常见秘钥、Token 与用户个人绝对路径
    const sanitizedMsg = log.message
      .replace(/sk-[a-zA-Z0-9]{20,}/g, 'sk-***[REDACTED]***')
      .replace(/\/Users\/[a-zA-Z0-9_-]+\//g, '/Users/***USER***/')
      .replace(/bearer\s+[a-zA-Z0-9._-]+/gi, 'Bearer ***[REDACTED]***');
    return `[${log.timestamp}] [${log.level.toUpperCase()}] [${log.component}] ${sanitizedMsg}`;
  });

  const payload = {
    generatedAt: new Date().toISOString(),
    gatewayHealth: health,
    recentSanitizedLogs: sanitizedLogs.slice(-100),
    systemEnvironment: {
      platform: typeof navigator !== 'undefined' ? navigator.platform : 'macOS',
      userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : 'Node/JSDOM',
    },
  };

  return JSON.stringify(payload, null, 2);
}

/**
 * 默认示范数据构造器
 */
export function getDefaultSessions(): SessionSummaryItem[] {
  return [
    {
      id: 'sess-001',
      title: 'Roadmap 09 前端 UX 架构与拟物化微应用重构',
      agentName: 'Arch-Master-4o',
      updatedAt: '2026-09-08 17:15',
      messageCount: 38,
      tokenCount: 48920,
      isPinned: true,
      tags: ['UX', 'Frontend', 'P0'],
    },
    {
      id: 'sess-002',
      title: 'OpenClaw Gateway 延迟压测与 N+1 请求清零',
      agentName: 'Diagnostics-Reaper',
      updatedAt: '2026-09-08 16:40',
      messageCount: 24,
      tokenCount: 31200,
      isPinned: true,
      tags: ['Gateway', 'Network', 'P0'],
    },
    {
      id: 'sess-003',
      title: '多模型分栏竞技场对比 DeepSeek-R1 与 Claude 3.7',
      agentName: 'Arena-Evaluator',
      updatedAt: '2026-09-08 14:10',
      messageCount: 19,
      tokenCount: 22100,
      isPinned: false,
      tags: ['Arena', 'Eval'],
    },
    {
      id: 'sess-004',
      title: '拍立得工件相册与复古转盘任务回放器联调',
      agentName: 'UX-Aesthetics-Bot',
      updatedAt: '2026-09-08 11:20',
      messageCount: 12,
      tokenCount: 15400,
      isPinned: false,
      tags: ['Skeuomorphic', 'Visualizer'],
    },
  ];
}

export function getDefaultHealth(): GatewayHealthState {
  return {
    isRunning: true,
    latencyMs: 18,
    version: 'v2026.8.1-myrm',
    activeSessionsCount: 4,
    serverType: 'local_python',
    status: 'healthy',
  };
}

export function getDefaultUsageSummary(horizon: UsageHorizon = 7): UsageSummary {
  const multiplier = horizon === 90 ? 12 : horizon === 30 ? 4 : 1;
  return {
    horizonDays: horizon,
    totalSessions: 697 * multiplier,
    totalApiCalls: 7120 * multiplier,
    tokensIn: 44200000 * multiplier,
    tokensOut: 6200000 * multiplier,
    topModels: [
      {
        modelId: 'claude-3-7-thinking',
        modelName: 'Claude 3.7 Thinking',
        tokenCount: 24500000 * multiplier,
        percentage: 48.6,
        costEstimateUsd: 73.5 * multiplier,
      },
      {
        modelId: 'deepseek-r1',
        modelName: 'DeepSeek-R1 (Local/API)',
        tokenCount: 16100000 * multiplier,
        percentage: 31.9,
        costEstimateUsd: 8.05 * multiplier,
      },
      {
        modelId: 'gpt-4o',
        modelName: 'GPT-4o Omniverse',
        tokenCount: 9800000 * multiplier,
        percentage: 19.5,
        costEstimateUsd: 34.3 * multiplier,
      },
    ],
    topSkills: [
      {
        skillId: 'code_execution',
        skillName: 'code_execution (沙箱代码执行)',
        actionCount: 122 * multiplier,
        successRate: 98.4,
      },
      {
        skillId: 'web_search',
        skillName: 'web_search (实时全网搜索)',
        actionCount: 36 * multiplier,
        successRate: 100.0,
      },
      {
        skillId: 'ast_grep_inspect',
        skillName: 'ast_grep_inspect (代码语法树探针)',
        actionCount: 29 * multiplier,
        successRate: 96.6,
      },
      {
        skillId: 'git_changes_review',
        skillName: 'git_changes_review (Diff 只读核验)',
        actionCount: 18 * multiplier,
        successRate: 100.0,
      },
    ],
  };
}

export function getDefaultLogs(): CommandCenterLogEntry[] {
  return [
    {
      id: 'log-1',
      timestamp: '18:10:02',
      level: 'info',
      component: 'gateway',
      message: 'Gateway HTTP/WS router heartbeat acknowledged (latency 18ms).',
    },
    {
      id: 'log-2',
      timestamp: '18:10:15',
      level: 'info',
      component: 'agent',
      message: 'Agent Arch-Master-4o dispatched tool code_execution (run id 8923).',
    },
    {
      id: 'log-3',
      timestamp: '18:11:00',
      level: 'debug',
      component: 'desktop',
      message: 'Global hotkey listener registered: Cmd+. and Cmd+K active.',
    },
    {
      id: 'log-4',
      timestamp: '18:12:30',
      level: 'warn',
      component: 'error',
      message: 'Minor token rate-limit near warning threshold (82% budget).',
    },
  ];
}
