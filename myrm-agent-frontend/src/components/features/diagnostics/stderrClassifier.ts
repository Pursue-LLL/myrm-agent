import type {
  ActionableFixGuide,
  ClassifiedDiagnosticResult,
  ExitCauseCategory,
} from './stderrDiagnosticTypes';

export const MAX_STDERR_BUFFER_BYTES = 2048; // 2 KiB 受限内存环形缓冲区

export function appendBoundedStderr(currentBuffer: string, newChunk: string): string {
  const combined = currentBuffer + newChunk;
  if (combined.length <= MAX_STDERR_BUFFER_BYTES) {
    return combined;
  }
  // 保留最新的 2 KiB 尾部
  return combined.slice(combined.length - MAX_STDERR_BUFFER_BYTES);
}

export function sanitizeStderrSnippet(raw: string): string {
  let sanitized = raw;

  // 脱敏 Unix 用户主目录: /Users/username/... 或 /home/username/...
  sanitized = sanitized.replace(/(?:\/Users|\/home)\/[a-zA-Z0-9._-]+/g, '[REDACTED_USER_PATH]');

  // 脱敏 Windows 用户主目录: C:\Users\username\...
  sanitized = sanitized.replace(/[A-Za-z]:\\Users\\[a-zA-Z0-9._-]+/g, '[REDACTED_USER_PATH]');

  // 脱敏常见 API 密钥模式: sk-..., Bearer ...
  sanitized = sanitized.replace(/sk-[a-zA-Z0-9_-]{20,}/g, '[REDACTED_API_KEY]');
  sanitized = sanitized.replace(/Bearer\s+[a-zA-Z0-9._~+/-]+=*/gi, 'Bearer [REDACTED_TOKEN]');

  return sanitized;
}

export function classifyStderr(rawStderr: string, exitCode: number): ClassifiedDiagnosticResult {
  const sanitized = sanitizeStderrSnippet(rawStderr);
  const lower = sanitized.toLowerCase();

  // 1. OOM 内存耗尽检测 (Exit Code 137 或显式关键字)
  if (exitCode === 137 || lower.includes('out of memory') || lower.includes('heap limit') || lower.includes('oom-killer')) {
    return {
      category: 'oom_killed',
      categoryLabel: '沙箱内存耗尽 (OOM Killed)',
      exitCode,
      rootCauseSummary: '进程在执行高负载计算或大数据集处理时触发了宿主沙箱内存硬限制，被系统 SIGKILL (137) 强制回收。',
      sanitizedStderrSnippet: sanitized.trim() || 'Process terminated with signal SIGKILL (Out of Memory)',
      confidenceScore: 0.98,
      fixGuides: [
        {
          actionId: 'fix_increase_memory',
          buttonLabel: '将沙箱内存提升至 4GB',
          actionType: 'increase_memory',
          isRecommended: true,
        },
        {
          actionId: 'fix_retry_smaller_batch',
          buttonLabel: '拆分任务并重试',
          actionType: 'retry_command',
          isRecommended: false,
        },
      ],
      occurredAt: new Date().toISOString(),
    };
  }

  // 2. 缺失运行依赖 (Python ModuleNotFoundError 或 Node Cannot find module)
  const pythonModuleMatch = sanitized.match(/ModuleNotFoundError:\s+No module named\s+'([^']+)'/i);
  const nodeModuleMatch = sanitized.match(/Cannot find module\s+'([^']+)'/i);
  const missingPkg = pythonModuleMatch?.[1] || nodeModuleMatch?.[1];

  if (missingPkg) {
    return {
      category: 'missing_dependency',
      categoryLabel: `缺少运行依赖: ${missingPkg}`,
      exitCode,
      rootCauseSummary: `执行环境中未找到依赖库「${missingPkg}」，导致解释器无法继续执行。`,
      sanitizedStderrSnippet: sanitized.trim(),
      confidenceScore: 0.95,
      fixGuides: [
        {
          actionId: `fix_install_${missingPkg}`,
          buttonLabel: `一键在沙箱安装 ${missingPkg}`,
          actionType: 'auto_install',
          payload: { package: missingPkg },
          isRecommended: true,
        },
      ],
      occurredAt: new Date().toISOString(),
    };
  }

  // 3. 端口占用冲突
  const portMatch = sanitized.match(/(?:EADDRINUSE|address already in use).*?:?(\d{2,5})/i);
  const portNumber = portMatch?.[1] || '8000';

  if (lower.includes('eaddrinuse') || lower.includes('address already in use')) {
    return {
      category: 'port_conflict',
      categoryLabel: `端口被占用 (Port ${portNumber})`,
      exitCode,
      rootCauseSummary: `本地端口 ${portNumber} 已被其他活跃进程占用，服务绑定失败。`,
      sanitizedStderrSnippet: sanitized.trim(),
      confidenceScore: 0.95,
      fixGuides: [
        {
          actionId: 'fix_switch_port',
          buttonLabel: '自动切换随机可用端口并重启',
          actionType: 'change_port',
          isRecommended: true,
        },
      ],
      occurredAt: new Date().toISOString(),
    };
  }

  // 4. 鉴权失败或 API Key 无效
  if (lower.includes('401 unauthorized') || lower.includes('invalid api key') || lower.includes('authenticationerror')) {
    return {
      category: 'auth_invalid',
      categoryLabel: '鉴权失败 / API Key 无效',
      exitCode,
      rootCauseSummary: '调用的外部大模型或三方服务拒绝了凭据，可能密钥已过期或未填写正确。',
      sanitizedStderrSnippet: sanitized.trim(),
      confidenceScore: 0.92,
      fixGuides: [
        {
          actionId: 'fix_open_provider_settings',
          buttonLabel: '前往设置中心检查密钥',
          actionType: 'open_settings',
          isRecommended: true,
        },
      ],
      occurredAt: new Date().toISOString(),
    };
  }

  // 5. 权限被拒绝 (EACCES / Permission denied)
  if (lower.includes('eacces') || lower.includes('permission denied')) {
    return {
      category: 'permission_denied',
      categoryLabel: '系统文件权限不足 (EACCES)',
      exitCode,
      rootCauseSummary: '沙箱内尝试读写受保护的文件或无执行权限的脚本。',
      sanitizedStderrSnippet: sanitized.trim(),
      confidenceScore: 0.9,
      fixGuides: [
        {
          actionId: 'fix_grant_permissions',
          buttonLabel: '重新尝试并放行权限',
          actionType: 'retry_command',
          isRecommended: true,
        },
      ],
      occurredAt: new Date().toISOString(),
    };
  }

  // 6. 网络超时与拒绝连接
  if (lower.includes('etimedout') || lower.includes('connection refused') || lower.includes('fetch failed')) {
    return {
      category: 'network_timeout',
      categoryLabel: '网络超时 / 连接被拒绝',
      exitCode,
      rootCauseSummary: '沙箱发起的外网请求未能建立握手，可能遇到代理受阻或远端服务离线。',
      sanitizedStderrSnippet: sanitized.trim(),
      confidenceScore: 0.88,
      fixGuides: [
        {
          actionId: 'fix_retry_network',
          buttonLabel: '重试网络连接',
          actionType: 'retry_command',
          isRecommended: true,
        },
      ],
      occurredAt: new Date().toISOString(),
    };
  }

  // 7. 通用降级未知失败
  return {
    category: 'unknown_failure',
    categoryLabel: `非预期退出 (Exit Code ${exitCode})`,
    exitCode,
    rootCauseSummary: `子进程异常终止，退出码为 ${exitCode}。已在内存截取脱敏诊断尾部供排查。`,
    sanitizedStderrSnippet: sanitized.trim() || 'No explicit stderr output captured.',
    confidenceScore: 0.5,
    fixGuides: [
      {
        actionId: 'fix_retry_general',
        buttonLabel: '重新尝试执行该命令',
        actionType: 'retry_command',
        isRecommended: true,
      },
    ],
    occurredAt: new Date().toISOString(),
  };
}
