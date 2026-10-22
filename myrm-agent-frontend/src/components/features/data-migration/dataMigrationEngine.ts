import {
  ConflictStrategy,
  FourDimensionalAssets,
  LegacyCronJob,
  LegacyMcpConfig,
  LegacyMemoryItem,
  LegacyTaskItem,
  MigrationReconciliationReport,
  MigrationSourceType,
} from './dataMigrationTypes';

/**
 * 异构 Cron 表达式容错归一化 (宽类型兼容 6 字段带秒或特殊字符)
 */
export function normalizeCronExpression(expr: string): string {
  const trimmed = expr.trim();
  if (!trimmed) {
    return '0 0 * * *';
  }

  const parts = trimmed.split(/\s+/);
  // 若是 6 字段格式 (秒 分 时 日 月 周)，去除第一位秒数，保留标准 5 字段
  if (parts.length === 6) {
    return parts.slice(1).join(' ');
  }
  // 若是 5 字段标准格式
  if (parts.length === 5) {
    return parts.join(' ');
  }

  // 快捷别名映射
  if (trimmed === '@daily' || trimmed === '@midnight') {
    return '0 0 * * *';
  }
  if (trimmed === '@hourly') {
    return '0 * * * *';
  }
  if (trimmed === '@weekly') {
    return '0 0 * * 0';
  }
  if (trimmed === '@monthly') {
    return '0 0 1 * *';
  }

  return '0 0 * * *';
}

/**
 * 宽类型安全解析异构 MCP 配置
 */
export function normalizeMcpConfig(
  rawName: string,
  rawConfig: Record<string, unknown>
): LegacyMcpConfig {
  const transport =
    rawConfig.transport === 'sse' || rawConfig.type === 'sse'
      ? ('sse' as const)
      : ('stdio' as const);

  const command =
    typeof rawConfig.command === 'string'
      ? rawConfig.command
      : typeof rawConfig.cmd === 'string'
      ? rawConfig.cmd
      : undefined;

  let args: string[] | undefined;
  if (Array.isArray(rawConfig.args)) {
    args = rawConfig.args.map((a) => String(a));
  }

  const url = typeof rawConfig.url === 'string' ? rawConfig.url : undefined;

  let env: Record<string, string> | undefined;
  if (rawConfig.env && typeof rawConfig.env === 'object') {
    env = Object.entries(rawConfig.env as Record<string, unknown>).reduce<
      Record<string, string>
    >((acc, [k, v]) => {
      acc[k] = String(v);
      return acc;
    }, {});
  }

  const enabled = rawConfig.enabled !== false;

  return {
    name: rawName.trim() || 'unnamed-mcp-server',
    transport,
    command,
    args,
    url,
    env,
    enabled,
  };
}

/**
 * 生成轻量资产指纹字符串用于冲突检测
 */
export function generateAssetFingerprint(
  category: 'task' | 'cron' | 'memory' | 'mcp',
  item: LegacyTaskItem | LegacyCronJob | LegacyMemoryItem | LegacyMcpConfig
): string {
  if (category === 'task') {
    const t = item as LegacyTaskItem;
    return `task:${t.title.trim().toLowerCase()}`;
  }
  if (category === 'cron') {
    const c = item as LegacyCronJob;
    return `cron:${c.name.trim().toLowerCase()}:${normalizeCronExpression(c.cronExpression)}`;
  }
  if (category === 'memory') {
    const m = item as LegacyMemoryItem;
    return `memory:${m.category}:${m.content.trim().toLowerCase()}`;
  }
  const mcp = item as LegacyMcpConfig;
  return `mcp:${mcp.name.trim().toLowerCase()}`;
}

/**
 * 汇总对账单统计
 */
export function buildReconciliationReport(
  incomingAssets: FourDimensionalAssets,
  existingFingerprints: Set<string>,
  sourceType: MigrationSourceType,
  sourcePath?: string,
  conflictStrategy: ConflictStrategy = 'skip'
): MigrationReconciliationReport {
  const calcStats = (
    category: 'task' | 'cron' | 'memory' | 'mcp',
    items: (LegacyTaskItem | LegacyCronJob | LegacyMemoryItem | LegacyMcpConfig)[]
  ) => {
    let duplicateCount = 0;
    items.forEach((item) => {
      const fp = generateAssetFingerprint(category, item);
      if (existingFingerprints.has(fp)) {
        duplicateCount += 1;
      }
    });
    return {
      total: items.length,
      duplicateCount,
      newCount: items.length - duplicateCount,
    };
  };

  return {
    batchId: `reconcile-${Date.now().toString(36)}`,
    sourceType,
    sourcePath,
    detectedAt: Date.now(),
    tasks: calcStats('task', incomingAssets.tasks),
    cronJobs: calcStats('cron', incomingAssets.cronJobs),
    memories: calcStats('memory', incomingAssets.memories),
    mcpConfigs: calcStats('mcp', incomingAssets.mcpConfigs),
    conflictStrategy,
  };
}

/**
 * 根据冲突合并策略应用过滤与重命名
 */
export function applyConflictResolution(
  incomingAssets: FourDimensionalAssets,
  existingFingerprints: Set<string>,
  strategy: ConflictStrategy
): FourDimensionalAssets {
  if (strategy === 'overwrite') {
    return incomingAssets;
  }

  const resolveList = <
    T extends LegacyTaskItem | LegacyCronJob | LegacyMemoryItem | LegacyMcpConfig
  >(
    category: 'task' | 'cron' | 'memory' | 'mcp',
    list: T[]
  ): T[] => {
    return list.flatMap((item) => {
      const fp = generateAssetFingerprint(category, item);
      const isDuplicated = existingFingerprints.has(fp);

      if (!isDuplicated) {
        return [item];
      }

      if (strategy === 'skip') {
        return [];
      }

      // rename 策略
      if (category === 'task') {
        const t = item as unknown as LegacyTaskItem;
        return [{ ...t, title: `${t.title} (迁移重名)` } as unknown as T];
      }
      if (category === 'cron') {
        const c = item as unknown as LegacyCronJob;
        return [{ ...c, name: `${c.name} (迁移重名)` } as unknown as T];
      }
      if (category === 'mcp') {
        const m = item as unknown as LegacyMcpConfig;
        return [{ ...m, name: `${m.name}_migrated` } as unknown as T];
      }
      return [item];
    });
  };

  return {
    tasks: resolveList('task', incomingAssets.tasks),
    cronJobs: resolveList('cron', incomingAssets.cronJobs),
    memories: resolveList('memory', incomingAssets.memories),
    mcpConfigs: resolveList('mcp', incomingAssets.mcpConfigs),
  };
}

/**
 * 获取迁移源类型的友好显示名称
 */
export function formatSourceTypeLabel(type: MigrationSourceType): string {
  if (type === 'qoder_v1') {
    return '老版 Qoder 工作台 (桌面/本地配置)';
  }
  if (type === 'hermes_legacy') {
    return 'Hermes 历史项目环境 (~/.hermes)';
  }
  if (type === 'openclaw') {
    return 'OpenClaw Agent 归档包 (~/.openclaw)';
  }
  if (type === 'sqlite_backup') {
    return '历史 SQLite 数据库归档 (*.db / *.sqlite)';
  }
  return '自定义 JSON 资产归档文件';
}
