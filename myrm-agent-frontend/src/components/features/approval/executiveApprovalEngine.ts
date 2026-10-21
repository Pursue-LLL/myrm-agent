import type {
  ApprovalActionType,
  ApprovalDecision,
  ApprovalRequest,
  ApprovalRiskLevel,
  ApprovalStats,
} from './executiveApprovalTypes';

export function evaluateRiskLevel(
  actionType: ApprovalActionType,
  _params: Record<string, unknown> = {}
): { level: ApprovalRiskLevel; reason: string } {
  if (actionType === 'payment') {
    return {
      level: 'critical',
      reason: '涉及实际财务转账与支付授权，可能产生真金白银支出。',
    };
  }

  if (actionType === 'delete') {
    return {
      level: 'high',
      reason: '涉及沙箱或外部数据库文件物理删除，属于不可逆写操作。',
    };
  }

  if (actionType === 'publish') {
    return {
      level: 'high',
      reason: '涉及社交平台公开发布，直接影响企业/个人声誉与公关安全。',
    };
  }

  if (actionType === 'deploy') {
    return {
      level: 'high',
      reason: '涉及生产环境上线与容器实例热更，需把关服务可用性。',
    };
  }

  return {
    level: 'low',
    reason: '常规辅助协同动作，风险在沙箱隔离受控范围之内。',
  };
}

export function computeApprovalStats(requests: readonly ApprovalRequest[]): ApprovalStats {
  const totalCount = requests.length;
  let pendingCount = 0;
  let approvedCount = 0;
  let rejectedCount = 0;
  let highRiskCount = 0;

  for (const item of requests) {
    if (item.status === 'pending') {
      pendingCount++;
    } else if (item.status === 'approved' || item.status === 'modified_approved') {
      approvedCount++;
    } else if (item.status === 'rejected') {
      rejectedCount++;
    }

    if (item.riskLevel === 'high' || item.riskLevel === 'critical') {
      highRiskCount++;
    }
  }

  return {
    pendingCount,
    approvedCount,
    rejectedCount,
    highRiskCount,
    totalCount,
  };
}

export function applyApprovalDecision(
  request: ApprovalRequest,
  decision: ApprovalDecision
): ApprovalRequest {
  if (decision.decision === 'approve') {
    return {
      ...request,
      status: 'approved',
      feedbackComment: decision.feedbackComment,
    };
  }

  if (decision.decision === 'reject') {
    return {
      ...request,
      status: 'rejected',
      feedbackComment: decision.feedbackComment ?? '董事长已驳回该执行方案，请调整重试。',
    };
  }

  return {
    ...request,
    status: 'modified_approved',
    modifiedContent: decision.modifiedContent ?? request.proposedContent,
    feedbackComment: decision.feedbackComment ?? '董事长已就地修改拟执行参数并批准。',
  };
}

export const DEFAULT_APPROVAL_REQUESTS: readonly ApprovalRequest[] = [
  {
    id: 'req-pub-001',
    taskId: 'task-market-801',
    agentId: 'agent-chief-marketer',
    agentName: '市场公关大管家',
    actionType: 'publish',
    actionTitle: '发布季度财报亮点至官方社交媒体',
    targetChannel: '官方微博 @Myrm_AI',
    summary: '已根据 Q3 业绩审计结果生成 6 张高清信息图文，准备直接发布至官方账号。',
    proposedContent: '【Q3 成绩单出炉】营收同比增长 128%，全自主智能体企业级落地超 500 家！感谢各位伙伴信任，更多黑科技功能即将震撼解锁！',
    riskLevel: 'high',
    riskReason: '公开发布涉及品牌对外声誉与财务信息准确度。',
    createdAt: '2026-10-15T10:00:00Z',
    status: 'pending',
  },
  {
    id: 'req-del-002',
    taskId: 'task-clean-902',
    agentId: 'agent-devops-sentinel',
    agentName: '运维巡检智能体',
    actionType: 'delete',
    actionTitle: '清理冷备日志与无用镜像资产',
    targetChannel: '生产存储集群 vol-prod-backup',
    summary: '扫描到 42.8 GB 超过 90 天未访问的过期调试转储文件，拟执行递归物理抹除。',
    proposedContent: 'rm -rf /volumes/prod-backup/logs/2026-06-* && vacuum_storage_cache',
    riskLevel: 'high',
    riskReason: '物理抹除动作不可逆，需人工把关确认无核心审计日志被错删。',
    createdAt: '2026-10-15T11:30:00Z',
    status: 'pending',
  },
  {
    id: 'req-pay-003',
    taskId: 'task-procure-103',
    agentId: 'agent-finance-controller',
    agentName: '财务核算专家',
    actionType: 'payment',
    actionTitle: '续订云托管 GPU 推理算力池',
    targetChannel: 'Cloudflare Workers AI 算力账单',
    summary: '当前推理并发量触达阈值，拟从企业资金账户自动划扣支付下月预留实例费用。',
    proposedContent: 'PAYMENT_AUTH: USD $420.00 -> Cloudflare GPU Reserved Cluster (8x H100)',
    riskLevel: 'critical',
    riskReason: '产生真金白银外部扣费，属于顶层最高风控红线。',
    createdAt: '2026-10-15T12:15:00Z',
    status: 'pending',
  },
];
