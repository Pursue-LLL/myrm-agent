import {
  CircuitBreakerStatus,
  ComponentHealthRecord,
  DegradationEvent,
  GlobalSystemHealthStatus,
  SystemHealthSummary,
} from './gracefulDegradationTypes';

/**
 * 计算系统全局依赖组件健康态与得分
 */
export function computeOverallSystemHealth(
  components: ComponentHealthRecord[],
): SystemHealthSummary {
  if (components.length === 0) {
    return {
      overallStatus: 'healthy',
      healthyCount: 0,
      degradedCount: 0,
      openBreakerCount: 0,
      averageLatencyMs: 0,
      healthScore: 100,
    };
  }

  let healthyCount = 0;
  let degradedCount = 0;
  let openBreakerCount = 0;
  let totalLatency = 0;

  for (const comp of components) {
    totalLatency += comp.latencyMs;
    if (comp.status === 'open') {
      openBreakerCount += 1;
    } else if (comp.status === 'half_open' || comp.errorRatePercent > 5) {
      degradedCount += 1;
    } else {
      healthyCount += 1;
    }
  }

  const averageLatencyMs = Math.round(totalLatency / components.length);

  // 评分模型：基础 100 分，每个断路器 open 扣 35 分，每个 degraded 扣 15 分，高延迟 (> 1500ms) 扣 10 分
  let score = 100 - openBreakerCount * 35 - degradedCount * 15;
  if (averageLatencyMs > 1500) {
    score -= 10;
  }
  const healthScore = Math.max(0, Math.min(100, score));

  let overallStatus: GlobalSystemHealthStatus = 'healthy';
  if (openBreakerCount >= 2 || healthScore < 50) {
    overallStatus = 'maintenance';
  } else if (openBreakerCount > 0 || degradedCount > 0 || healthScore < 85) {
    overallStatus = 'degraded';
  }

  return {
    overallStatus,
    healthyCount,
    degradedCount,
    openBreakerCount,
    averageLatencyMs,
    healthScore,
  };
}

/**
 * 格式化延迟毫秒数
 */
export function formatLatency(latencyMs: number): {
  text: string;
  level: 'good' | 'moderate' | 'slow';
} {
  const safeMs = Math.max(0, Math.round(latencyMs));
  if (safeMs < 400) {
    return { text: `${safeMs}ms`, level: 'good' };
  }
  if (safeMs < 1200) {
    return { text: `${safeMs}ms`, level: 'moderate' };
  }
  return { text: `${(safeMs / 1000).toFixed(1)}s`, level: 'slow' };
}

/**
 * 组装非侵入式降级徽章的主标题文案
 */
export function generateFallbackPillText(event: DegradationEvent): string {
  if (event.fallbackActive) {
    return `${event.componentName}暂时拥堵，已无缝切换至降级策略回答`;
  }
  return `${event.componentName}存在偶发抖动`;
}

/**
 * 获取断路器状态的标准中文标签与配色语义
 */
export function getCircuitBreakerLabel(status: CircuitBreakerStatus): {
  label: string;
  badgeClass: string;
} {
  if (status === 'closed') {
    return {
      label: '正常闭合 (Closed)',
      badgeClass:
        'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
    };
  }
  if (status === 'half_open') {
    return {
      label: '半开探测 (Half-Open)',
      badgeClass:
        'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
    };
  }
  return {
    label: '熔断保护 (Open)',
    badgeClass:
      'bg-destructive/10 text-destructive border-destructive/20',
  };
}
