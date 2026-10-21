import {
  PairingSessionConfig,
  TaskPhase,
} from './mobileCompanionTypes';

export function generatePairingConfig(
  sessionId: string,
  baseUrl = 'https://app.myrmidon.local'
): PairingSessionConfig {
  const token = `pair-${Date.now()}-${Math.random().toString(36).substring(2, 10)}`;
  const expiresAt = Date.now() + 30 * 60 * 1000; // 30 分钟有效
  const pairingUrl = `${baseUrl}/m/task?session=${encodeURIComponent(
    sessionId
  )}&token=${token}`;

  return {
    sessionId,
    pairingToken: token,
    pairingUrl,
    expiresAt,
    isPwaInstallable: true,
  };
}

export function formatTimeRemaining(seconds: number): string {
  if (seconds <= 0) {
    return '即将完成';
  }
  if (seconds < 60) {
    return `约 ${Math.round(seconds)} 秒`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSec = Math.round(seconds % 60);
  if (remainingSec === 0) {
    return `约 ${minutes} 分钟`;
  }
  return `约 ${minutes} 分 ${remainingSec} 秒`;
}

export function filterHighSnrLogs(rawLogs: string[]): string[] {
  const noisyPatterns = [
    /^npm http/i,
    /^get http/i,
    /^fetch\s+/i,
    /^\s*at\s+/i,
    /^\s*\.\.\.\s*$/,
    /^transpiling\s+file/i,
    /^downloading/i,
  ];

  const filtered: string[] = [];
  for (const log of rawLogs) {
    const trimmed = log.trim();
    if (!trimmed) {
      continue;
    }

    const isNoisy = noisyPatterns.some((pattern) => pattern.test(trimmed));
    if (!isNoisy) {
      filtered.push(trimmed);
    }
  }

  // 保证最多保留最新的 8 条高信噪比事件
  return filtered.slice(-8);
}

export interface PhaseBadgeInfo {
  label: string;
  badgeClass: string;
  dotClass: string;
}

export function getPhaseBadgeInfo(phase: TaskPhase): PhaseBadgeInfo {
  if (phase === 'initializing') {
    return {
      label: '环境初始化中',
      badgeClass: 'bg-zinc-800 text-zinc-300 border-zinc-750',
      dotClass: 'bg-zinc-400 animate-pulse',
    };
  }

  if (phase === 'analyzing') {
    return {
      label: '需求与代码分析',
      badgeClass: 'bg-purple-500/10 text-purple-300 border-purple-500/30',
      dotClass: 'bg-purple-400 animate-pulse',
    };
  }

  if (phase === 'generating') {
    return {
      label: '沙箱代码生成',
      badgeClass: 'bg-indigo-500/10 text-indigo-300 border-indigo-500/30',
      dotClass: 'bg-indigo-400 animate-pulse',
    };
  }

  if (phase === 'testing') {
    return {
      label: '单元与回归测试',
      badgeClass: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30',
      dotClass: 'bg-cyan-400 animate-pulse',
    };
  }

  if (phase === 'deploying') {
    return {
      label: '沙箱渲染与发布',
      badgeClass: 'bg-blue-500/10 text-blue-300 border-blue-500/30',
      dotClass: 'bg-blue-400 animate-pulse',
    };
  }

  if (phase === 'paused_approval') {
    return {
      label: '等待人工高危审批',
      badgeClass: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
      dotClass: 'bg-amber-400 animate-ping',
    };
  }

  return {
    label: '任务全部交付',
    badgeClass: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30',
    dotClass: 'bg-emerald-400',
  };
}
