/**
 * [INPUT]
 * - 无（纯函数，不含 React 与副作用）
 *
 * [OUTPUT]
 * - ProbeStatus / ProbeRecommendedMode / ProbeReasonCode: 连通性探测的受控状态与枚举
 * - normalizeProbeRecommendedMode / normalizeProbeReasonCode: 后端自由字符串收敛为受控枚举
 * - probeErrorI18nKey: reasonCode 到失败文案 i18n key 的映射
 * - isLoopbackProbeUrl / resolveProbeUrl: 探测资格与地址解析（仅本机回环目标可探测，远端由安全门握手校验）
 *
 * [POS]
 * 连接对话框连通性探测的类型与归一化规则，供 useConnectivityProbe 与探测提示 UI 共用。
 */

export type ProbeStatus = 'idle' | 'probing' | 'reachable' | 'unreachable' | 'cloud_not_supported';

export type ProbeRecommendedMode = 'local_or_tauri' | 'start_local_editor_mcp' | 'verify_local_network_and_editor';

export type ProbeReasonCode =
  | 'reachable'
  | 'connection_refused'
  | 'connection_unreachable'
  | 'tls_verification_failed'
  | 'connection_timeout'
  | 'probe_failed_unknown'
  | 'loopback_unavailable_in_cloud';

export function normalizeProbeRecommendedMode(value: string | undefined): ProbeRecommendedMode | null {
  if (value === 'local_or_tauri' || value === 'start_local_editor_mcp' || value === 'verify_local_network_and_editor') {
    return value;
  }
  return null;
}

export function normalizeProbeReasonCode(value: string | undefined): ProbeReasonCode | null {
  if (
    value === 'reachable' ||
    value === 'connection_refused' ||
    value === 'connection_unreachable' ||
    value === 'tls_verification_failed' ||
    value === 'connection_timeout' ||
    value === 'probe_failed_unknown' ||
    value === 'loopback_unavailable_in_cloud'
  ) {
    return value;
  }
  return null;
}

export function probeErrorI18nKey(
  reasonCode: ProbeReasonCode | null,
):
  | 'probeConnectionRefused'
  | 'probeConnectionUnreachable'
  | 'probeTlsVerificationFailed'
  | 'probeConnectionTimeout'
  | 'probeUnknownFailure'
  | null {
  if (reasonCode === 'connection_refused') {
    return 'probeConnectionRefused';
  }
  if (reasonCode === 'connection_unreachable') {
    return 'probeConnectionUnreachable';
  }
  if (reasonCode === 'tls_verification_failed') {
    return 'probeTlsVerificationFailed';
  }
  if (reasonCode === 'connection_timeout') {
    return 'probeConnectionTimeout';
  }
  if (reasonCode === 'probe_failed_unknown') {
    return 'probeUnknownFailure';
  }
  return null;
}

// Mirrors the backend /probe allowlist (SSRF guard): only these hosts may be probed.
const LOOPBACK_PROBE_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '0.0.0.0']);

/**
 * The backend probe endpoint only accepts loopback targets; remote entries are
 * verified by the security gate's real MCP handshake instead of a probe.
 */
export function isLoopbackProbeUrl(candidate: string): boolean {
  try {
    const hostname = new URL(candidate).hostname.replace(/^\[|\]$/g, '').toLowerCase();
    return LOOPBACK_PROBE_HOSTS.has(hostname);
  } catch {
    return false;
  }
}

export function resolveProbeUrl(mcpConfig: Record<string, unknown> | null): string | undefined {
  const probeUrlCandidate = mcpConfig?.probeUrl;
  if (typeof probeUrlCandidate === 'string' && probeUrlCandidate.trim()) {
    return isLoopbackProbeUrl(probeUrlCandidate) ? probeUrlCandidate : undefined;
  }
  const urlCandidate = mcpConfig?.url;
  if (typeof urlCandidate === 'string' && urlCandidate.trim()) {
    return isLoopbackProbeUrl(urlCandidate) ? urlCandidate : undefined;
  }
  return undefined;
}
