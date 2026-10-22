/**
 * [INPUT]
 * - @/components/features/chat-window/lane-gradient/laneSemanticTypes
 *
 * [OUTPUT]
 * - resolveLaneGradientSpec, detectGraduationIntent, buildGraduationEvent, formatLaneDisplay
 *
 * [POS]
 * Pure computation engine for Item 188: ChatLaneVsWorkspaceLaneSemanticGradientAndAutoGraduationSuite.
 * Resolves authoritative lane specs from heterogeneous chat state and performs
 * deterministic in-session intent detection for boundary-crossing triggers without side effects.
 */

import type {
  LaneType,
  LaneEnvironmentMode,
  LaneGradientSpec,
  GraduationIntentMatch,
  GraduationTriggerKind,
  LaneGraduationEvent,
} from './laneSemanticTypes';

interface IntentRule {
  readonly kind: GraduationTriggerKind;
  readonly pattern: RegExp;
  readonly confidence: number;
  readonly reason: string;
  readonly defaultTarget: 'local_workspace' | 'cloud_sandbox';
}

const GRADUATION_RULES: readonly IntentRule[] = [
  {
    kind: 'file_write',
    pattern: /(保存到|写入文件|修改文件|创建文件|修改代码|新建文件|写到本地|save\s+(to|file)|write\s+(to|file)|create\s+file|edit\s+file|update\s+file|\.tsx?|\.jsx?|\.json|\.py|\.rs|\.go|\.env)/i,
    confidence: 0.92,
    reason: '检测到文件写入或代码保存意图，当前纯对话通道无写磁盘权限',
    defaultTarget: 'local_workspace',
  },
  {
    kind: 'dependency_install',
    pattern: /(安装依赖|添加依赖|install\s+package|add\s+dependency|\bnpm\s+i(nstall)?\b|\bpip\s+install\b|\bpnpm\s+add\b|\byarn\s+add\b)/i,
    confidence: 0.9,
    reason: '检测到包依赖安装请求，需要持久化工作区环境',
    defaultTarget: 'cloud_sandbox',
  },
  {
    kind: 'project_scaffold',
    pattern: /(初始化项目|搭建项目|创建工程|脚手架|create-next-app|npx\s+create|npm\s+init|scaffold|git\s+clone)/i,
    confidence: 0.88,
    reason: '检测到项目初始化与目录脚手架搭建意图，需关联工作区目录',
    defaultTarget: 'local_workspace',
  },
  {
    kind: 'shell_command',
    pattern: /(执行命令|运行命令|跑一下|终端运行|命令行|\bnpm\s+(test|run|dev|build)\b|\bpnpm\s+\w+\b|\byarn\s+\w+\b|\bcargo\s+\w+\b|\bgit\s+(commit|push|pull|status)\b|\b(bash|sh)\s+)/i,
    confidence: 0.95,
    reason: '检测到终端脚本或系统命令执行意图，需在工作区通道中安全运行',
    defaultTarget: 'local_workspace',
  },
  {
    kind: 'git_operation',
    pattern: /(提交代码|推送远端|创建分支|新建分支|\bgit\s+(checkout|branch|merge|rebase)\b)/i,
    confidence: 0.91,
    reason: '检测到版本控制与 Git 仓库操作意图，需绑定本地 Git 工作区',
    defaultTarget: 'local_workspace',
  },
];

export function resolveLaneGradientSpec(
  actionMode: string | null | undefined,
  sandboxMode: boolean | null | undefined,
  workspaceDir: string | null | undefined,
): LaneGradientSpec {
  if (sandboxMode === true) {
    return {
      laneType: 'workspace',
      envMode: 'cloud_sandbox',
      displayName: '云端沙箱工作区',
      summary: '安全云端隔离环境，支持代码生成与命令执行',
      capabilities: ['file_write', 'shell_exec', 'web_search', 'code_sandbox'],
      persistenceScope: 'cloud_container',
      canWriteFiles: true,
      canExecCommands: true,
      badgeColor: 'indigo',
    };
  }

  if (Boolean(workspaceDir) || actionMode === 'agent') {
    return {
      laneType: 'workspace',
      envMode: 'local_workspace',
      displayName: '本地工作区',
      summary: '直接读写本地磁盘目录，支持终端执行与工程操作',
      capabilities: ['file_write', 'shell_exec', 'web_search', 'git_ops'],
      persistenceScope: 'local_disk',
      canWriteFiles: true,
      canExecCommands: true,
      badgeColor: 'emerald',
    };
  }

  return {
    laneType: 'chat',
    envMode: 'fast_chat',
    displayName: '快速对话通道',
    summary: '纯文本会话与只读问答，零本地文件与终端副作用',
    capabilities: ['read_only', 'web_search'],
    persistenceScope: 'ephemeral_memory',
    canWriteFiles: false,
    canExecCommands: false,
    badgeColor: 'sky',
  };
}

export function detectGraduationIntent(
  text: string,
  currentLane: LaneType,
): GraduationIntentMatch | null {
  if (currentLane === 'workspace') {
    return null;
  }

  const trimmed = text.trim();
  if (!trimmed) {
    return null;
  }

  for (const rule of GRADUATION_RULES) {
    const match = rule.pattern.exec(trimmed);
    if (match) {
      return {
        triggerKind: rule.kind,
        matchedKeyword: match[0],
        confidence: rule.confidence,
        reason: rule.reason,
        suggestedTargetMode: rule.defaultTarget,
        detectedSnippet: trimmed.length > 80 ? `${trimmed.slice(0, 77)}...` : trimmed,
      };
    }
  }

  return null;
}

export function formatLaneDisplay(
  spec: LaneGradientSpec,
  t?: (key: string) => string,
): { title: string; badgeText: string; description: string } {
  if (t) {
    const title = t(`lanes.${spec.envMode}.title`);
    const badgeText = t(`lanes.${spec.envMode}.badge`);
    const description = t(`lanes.${spec.envMode}.description`);
    if (title && !title.startsWith('lanes.')) {
      return { title, badgeText, description };
    }
  }

  return {
    title: spec.displayName,
    badgeText: spec.laneType === 'workspace' ? '工作区通道' : '对话通道',
    description: spec.summary,
  };
}

export function buildGraduationEvent(params: {
  fromSpec: LaneGradientSpec;
  toEnvMode: LaneEnvironmentMode;
  reason: string;
  workspaceDir: string | null;
}): LaneGraduationEvent {
  const toLane: LaneType = params.toEnvMode === 'fast_chat' ? 'chat' : 'workspace';
  return {
    id: `grad_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`,
    timestamp: Date.now(),
    fromLane: params.fromSpec.laneType,
    fromEnvMode: params.fromSpec.envMode,
    toLane,
    toEnvMode: params.toEnvMode,
    reason: params.reason,
    workspaceDir: params.workspaceDir,
  };
}
