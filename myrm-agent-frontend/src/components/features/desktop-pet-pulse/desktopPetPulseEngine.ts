/**
 * desktopPetPulseEngine.ts
 * 桌面微型悬浮桌宠状态转换、智能体身份投影与数据迁移纯函数引擎
 */

import type {
  AgentIdentityProjection,
  DataMigrationBundle,
  DataMigrationCategory,
  MigrationExecutionOptions,
  MigrationReport,
  PetExpression,
  PetPulseStatus,
  PetPulseVisualConfig,
  SecondaryAgentBadge,
  VoiceTaskDispatchPayload,
} from './desktopPetPulseTypes';

export function derivePetVisualConfig(
  status: PetPulseStatus,
  hasApproval = false,
  hasError = false
): PetPulseVisualConfig {
  if (hasError || status === 'error') {
    return {
      status: 'error',
      expression: 'concerned',
      haloColor: 'rgba(239, 68, 68, 0.45)',
      pulseRateHz: 2.0,
      badgeLabel: '异常拦截',
    };
  }

  if (hasApproval || status === 'approval_needed') {
    return {
      status: 'approval_needed',
      expression: 'alert_shake',
      haloColor: 'rgba(245, 158, 11, 0.55)',
      pulseRateHz: 1.5,
      badgeLabel: '待授权',
    };
  }

  switch (status) {
    case 'thinking': {
      return {
        status: 'thinking',
        expression: 'pulsing',
        haloColor: 'rgba(59, 130, 246, 0.45)',
        pulseRateHz: 1.2,
        badgeLabel: '思考中',
      };
    }
    case 'working': {
      return {
        status: 'working',
        expression: 'focused',
        haloColor: 'rgba(16, 185, 129, 0.5)',
        pulseRateHz: 0.8,
        badgeLabel: '执行中',
      };
    }
    case 'done': {
      return {
        status: 'done',
        expression: 'celebrate',
        haloColor: 'rgba(34, 197, 94, 0.6)',
        pulseRateHz: 0.4,
        badgeLabel: '已达成',
      };
    }
    case 'idle':
    default: {
      return {
        status: 'idle',
        expression: 'calm',
        haloColor: 'rgba(148, 163, 184, 0.25)',
        pulseRateHz: 0.2,
        badgeLabel: '就绪',
      };
    }
  }
}

export function computeStackedAgentBadges(
  primaryAgentId: string | null,
  allAgents: AgentIdentityProjection[],
  activeQueue: Array<{
    agentId: string;
    status: 'queued' | 'approving' | 'working';
  }>
): SecondaryAgentBadge[] {
  const agentMap = new Map<string, AgentIdentityProjection>();
  for (const agent of allAgents) {
    agentMap.set(agent.agentId, agent);
  }

  const result: SecondaryAgentBadge[] = [];
  const visited = new Set<string>();

  for (const item of activeQueue) {
    if (item.agentId === primaryAgentId) {
      continue;
    }
    if (visited.has(item.agentId)) {
      continue;
    }
    visited.add(item.agentId);

    const meta = agentMap.get(item.agentId);
    const name = meta !== undefined ? meta.name : item.agentId;
    const colorTheme = meta !== undefined ? meta.colorTheme : '#64748b';

    result.push({
      agentId: item.agentId,
      name,
      status: item.status,
      colorTheme,
    });
  }

  return result;
}

export function formatVoiceDispatchPayload(
  transcript: string,
  options?: {
    targetAgentId?: string;
    sessionId?: string;
    autoRun?: boolean;
  }
): VoiceTaskDispatchPayload {
  const cleanPrompt = transcript.trim();
  return {
    sessionId: options?.sessionId,
    targetAgentId: options?.targetAgentId,
    prompt: cleanPrompt,
    autoRun: options?.autoRun ?? true,
    timestamp: Date.now(),
  };
}

export function validateMigrationBundle(raw: unknown): {
  valid: boolean;
  bundle?: DataMigrationBundle;
  error?: string;
} {
  if (typeof raw !== 'object' || raw === null) {
    return { valid: false, error: '导入数据必须是合法 JSON 对象' };
  }

  const record = raw as Record<string, unknown>;

  if (typeof record.version !== 'string' || record.version.trim() === '') {
    return { valid: false, error: '缺少有效的版本字段 (version)' };
  }

  if (typeof record.source !== 'string' || record.source.trim() === '') {
    return { valid: false, error: '缺少有效的数据来源字段 (source)' };
  }

  const bundle: DataMigrationBundle = {
    version: String(record.version),
    source: record.source as DataMigrationBundle['source'],
    createdAt:
      typeof record.createdAt === 'number' ? record.createdAt : Date.now(),
    tasks: Array.isArray(record.tasks)
      ? (record.tasks as DataMigrationBundle['tasks'])
      : [],
    crons: Array.isArray(record.crons)
      ? (record.crons as DataMigrationBundle['crons'])
      : [],
    memories: Array.isArray(record.memories)
      ? (record.memories as DataMigrationBundle['memories'])
      : [],
    mcps: Array.isArray(record.mcps)
      ? (record.mcps as DataMigrationBundle['mcps'])
      : [],
    agents: Array.isArray(record.agents)
      ? (record.agents as DataMigrationBundle['agents'])
      : [],
  };

  return { valid: true, bundle };
}

export function executeDataMigrationMerge(
  bundle: DataMigrationBundle,
  options: MigrationExecutionOptions,
  existingKeys?: {
    tasks?: Set<string>;
    crons?: Set<string>;
    memories?: Set<string>;
    mcps?: Set<string>;
    agents?: Set<string>;
  }
): MigrationReport {
  const initialCategoryCounts: Record<DataMigrationCategory, number> = {
    tasks: 0,
    crons: 0,
    memories: 0,
    mcps: 0,
    agents: 0,
  };

  const importedCounts: Record<DataMigrationCategory, number> = {
    ...initialCategoryCounts,
  };
  const skippedCounts: Record<DataMigrationCategory, number> = {
    ...initialCategoryCounts,
  };
  const logs: string[] = [];

  const checkCategory = (
    cat: DataMigrationCategory,
    items: Array<{ id: string }>,
    existingSet?: Set<string>
  ): void => {
    if (!options.selectedCategories.includes(cat)) {
      return;
    }

    let imported = 0;
    let skipped = 0;

    for (const item of items) {
      const exists = existingSet !== undefined && existingSet.has(item.id);
      if (exists) {
        if (options.strategy === 'skip') {
          skipped += 1;
        } else {
          imported += 1;
        }
      } else {
        imported += 1;
      }
    }

    importedCounts[cat] = imported;
    skippedCounts[cat] = skipped;
    logs.push(
      `[${cat}] 处理完成: 成功导入 ${imported} 项, 跳过 ${skipped} 项 (策略: ${options.strategy})`
    );
  };

  checkCategory('tasks', bundle.tasks ?? [], existingKeys?.tasks);
  checkCategory('crons', bundle.crons ?? [], existingKeys?.crons);
  checkCategory('memories', bundle.memories ?? [], existingKeys?.memories);
  checkCategory('mcps', bundle.mcps ?? [], existingKeys?.mcps);
  checkCategory('agents', bundle.agents ?? [], existingKeys?.agents);

  return {
    success: true,
    source: bundle.source,
    importedCounts,
    skippedCounts,
    logs,
    timestamp: Date.now(),
  };
}
