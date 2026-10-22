import {
  PrivacySanitizeResult,
  RoamingStateRecord,
  StorageBackendType,
  TransformFormat,
} from './localFirstTypes';

/**
 * 纯客户端离线脱敏引擎 (Zero Data Upload)
 */
export function sanitizeClientSideData(text: string): PrivacySanitizeResult {
  const startTime = performance.now();
  let sanitized = text;
  let maskedCount = 0;
  const detectedTypesSet = new Set<string>();

  // 1. 脱敏中国大陆 18 位身份证 (优先处理长数字串，防被切断成手机号)
  const idCardRegex = /(?<!\d)(\d{6})\d{8}(\d{3}[\dXx])(?!\d)/g;
  sanitized = sanitized.replace(idCardRegex, (_match, p1, p2) => {
    maskedCount += 1;
    detectedTypesSet.add('身份证号');
    return `${p1}********${p2}`;
  });

  // 2. 脱敏手机号 (中国 11 位数字 1[3-9]\d{9}，且前后无相连数字)
  const phoneRegex = /(?<!\d)(?:\+?86)?(1[3-9]\d)(\d{4})(\d{4})(?!\d)/g;
  sanitized = sanitized.replace(phoneRegex, (_match, p1, _p2, p3) => {
    maskedCount += 1;
    detectedTypesSet.add('手机号');
    return `${p1}****${p3}`;
  });

  // 3. 脱敏电子邮箱
  const emailRegex = /([a-zA-Z0-9_.+-])[a-zA-Z0-9_.+-]*@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)/g;
  sanitized = sanitized.replace(emailRegex, (_match, p1, p2) => {
    maskedCount += 1;
    detectedTypesSet.add('电子邮箱');
    return `${p1}***@${p2}`;
  });

  // 4. 脱敏 API Key 凭据 (如 sk-xxxxxxxxxxxx)
  const apiKeyRegex = /(sk-[a-zA-Z0-9]{4})[a-zA-Z0-9]{8,}([a-zA-Z0-9]{4})/g;
  sanitized = sanitized.replace(apiKeyRegex, (_match, p1, p2) => {
    maskedCount += 1;
    detectedTypesSet.add('API Key');
    return `${p1}****${p2}`;
  });

  const executionTimeMs = Math.max(0, performance.now() - startTime);

  return {
    sanitizedText: sanitized,
    maskedCount,
    detectedTypes: Array.from(detectedTypesSet),
    executionTimeMs: Math.round(executionTimeMs * 100) / 100,
  };
}

/**
 * 纯客户端就地数据格式轻量转换器
 */
export function convertJsonToFormat(
  jsonStr: string,
  targetFormat: TransformFormat,
): string {
  const trimmed = jsonStr.trim();
  if (!trimmed) {
    return '';
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch (_e) {
    throw new Error('无效的 JSON 格式，请检查语法');
  }

  if (targetFormat === 'json') {
    return JSON.stringify(parsed, null, 2);
  }

  if (targetFormat === 'csv') {
    if (!Array.isArray(parsed) || parsed.length === 0) {
      return '';
    }
    const headers = Object.keys(
      (parsed[0] as Record<string, unknown>) ?? {},
    );
    const headerRow = headers.join(',');
    const rows = parsed.map((item) => {
      const obj = (item as Record<string, unknown>) ?? {};
      return headers
        .map((h) => {
          const val = String(obj[h] ?? '');
          return val.includes(',') ? `"${val}"` : val;
        })
        .join(',');
    });
    return [headerRow, ...rows].join('\n');
  }

  if (targetFormat === 'markdown_table') {
    if (!Array.isArray(parsed) || parsed.length === 0) {
      return '';
    }
    const headers = Object.keys(
      (parsed[0] as Record<string, unknown>) ?? {},
    );
    const headerRow = `| ${headers.join(' | ')} |`;
    const separatorRow = `| ${headers.map(() => '---').join(' | ')} |`;
    const rows = parsed.map((item) => {
      const obj = (item as Record<string, unknown>) ?? {};
      return `| ${headers.map((h) => String(obj[h] ?? '')).join(' | ')} |`;
    });
    return [headerRow, separatorRow, ...rows].join('\n');
  }

  if (targetFormat === 'yaml') {
    if (typeof parsed !== 'object' || parsed === null) {
      return String(parsed);
    }
    const lines: string[] = [];
    if (Array.isArray(parsed)) {
      parsed.forEach((item) => {
        if (typeof item === 'object' && item !== null) {
          const entries = Object.entries(item as Record<string, unknown>);
          entries.forEach(([k, v], idx) => {
            lines.push(`${idx === 0 ? '- ' : '  '}${k}: ${String(v)}`);
          });
        } else {
          lines.push(`- ${String(item)}`);
        }
      });
    } else {
      const entries = Object.entries(parsed as Record<string, unknown>);
      entries.forEach(([k, v]) => {
        lines.push(`${k}: ${String(v)}`);
      });
    }
    return lines.join('\n');
  }

  return JSON.stringify(parsed, null, 2);
}

/**
 * 纯客户端生成校验和摘要
 */
export function calculateSimpleChecksum(content: string): string {
  let hash = 0;
  for (let i = 0; i < content.length; i += 1) {
    const char = content.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash |= 0;
  }
  return `chk-${Math.abs(hash).toString(16)}`;
}

/**
 * 构造跨端漫游记录模型
 */
export function buildRoamingRecord<T>(
  key: string,
  data: T,
  backend: StorageBackendType = 'local_storage',
  version: number = 1,
): RoamingStateRecord<T> {
  const contentStr = JSON.stringify(data);
  return {
    key,
    data,
    backend,
    version,
    updatedAt: Date.now(),
    checksum: calculateSimpleChecksum(contentStr),
  };
}
