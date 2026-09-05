/**
 * [INPUT] None (zero-dependency pure utility)
 * [OUTPUT] redactErrorMessage, redactErrorObject, redactSensitiveText, formatUiError, maskToken, REDACTION_MASK
 * [POS] Control UI 全面错误展示脱敏引擎。统一对 Toast、API 响应解析和内联错误文本执行不可逆高敏感字段抹除。
 */

export const REDACTION_MASK = '***REDACTED***';

/**
 * 敏感凭证与高危信息匹配模式集
 */
const PATTERNS = {
  // 1. 常见平台 API 密钥与凭证 (OpenAI, Anthropic, GitHub, Slack, HuggingFace, GitLab 等)
  apiKeys: /\b(?:sk-[a-zA-Z0-9_\-]{10,}|(?:ghp|gho|ghu|ghs|ghr|xoxb|xoxp|xapp|xoxa|glpat|npm_|hf_)[A-Za-z0-9_\-]{16,})\b/g,

  // 2. HTTP Bearer 认证头部
  bearerTokens: /\b(Bearer\s+)[A-Za-z0-9_\-.]{12,}\b/gi,

  // 3. JWT 三段式 Token
  jwtTokens: /\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/g,

  // 4. AWS 访问密钥
  awsKeys: /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g,

  // 5. 键值对型凭证 (如 token=abc, password: 123)
  keyValueSecrets: /\b(token|password|secret|api_key|apikey|auth_token|client_secret)\s*([:=])\s*["']?([^\s"',;]{6,})["']?/gi,

  // 6. 数据库与消息队列 URI 密码 (postgres://user:password@host)
  dbUriCredentials: /\b((?:postgres(?:ql)?|mysql|mariadb|redis(?:s)?|mongodb(?:\+srv)?|amqp(?:s)?):\/\/[^:\s/]+:)([^@\s]+)(@)/gi,

  // 7. PEM 私钥块
  pemPrivateKey: /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g,

  // 8. 本地用户主目录绝对路径前缀 (macOS / Linux / Windows) - 仅替换用户主目录前缀，保留相对文件名排错
  sensitiveFsUserHome: /(^|[\s"'`=:(])(?:\/Users\/|\/home\/|\/var\/folders\/)[a-zA-Z0-9._-]+\//g,
  sensitiveFsWindowsUserHome: /(^|[\s"'`=:(])[A-Za-z]:\\Users\\[^\\/\s"')]+[\\/]/g,

  // 9. Authorization 头
  authHeader: /\b(Authorization|Proxy-Authorization)\s*:\s*[^\r\n,;]+/gi,

  // 10. 错误信息中内网私有 IP 地址端点 (RFC1918)
  privateEndpoints: /\b(https?:\/\/)(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(:\d+)?\b/gi,
};

/**
 * 生成兼顾排障指纹与防泄密的安全掩码
 * 长度 <= 10 强制全掩码以防负数切片重叠，长度 > 10 保留前 6 后 4
 */
export function maskToken(token: string): string {
  if (!token || typeof token !== 'string') {
    return '[redacted]';
  }
  if (token.length <= 10) {
    return '[redacted]';
  }
  return `${token.slice(0, 6)}...${token.slice(-4)}`;
}

/**
 * 对纯文本执行脱敏清洗
 */
export function redactSensitiveText(text: string): string {
  if (!text || typeof text !== 'string') {
    return text;
  }

  return text
    // 1. PEM 私钥块
    .replace(PATTERNS.pemPrivateKey, '[redacted private key]')
    // 2. 数据库 URI 密码打码
    .replace(PATTERNS.dbUriCredentials, '$1***$3')
    // 3. Authorization 头部打码
    .replace(PATTERNS.authHeader, '$1: [redacted]')
    // 4. Bearer Token 打码 (保留 6/4 掩码指纹)
    .replace(PATTERNS.bearerTokens, (_match, prefix, offset, fullStr) => {
      const fullMatch = _match.trim();
      const token = fullMatch.replace(/^Bearer\s+/i, '');
      return `${prefix}${maskToken(token)}`;
    })
    // 5. API Keys (OpenAI, GitHub, etc.) 保留 6/4 掩码
    .replace(PATTERNS.apiKeys, (match) => maskToken(match))
    // 6. JWT 打码
    .replace(PATTERNS.jwtTokens, (match) => maskToken(match))
    // 7. AWS Key 打码
    .replace(PATTERNS.awsKeys, (match) => maskToken(match))
    // 8. 键值对型凭据与敏感 URL Query 打码
    .replace(PATTERNS.keyValueSecrets, (_match, key, sep, value) => {
      return `${key}${sep}${maskToken(value)}`;
    })
    // 9. 本地绝对主目录路径规范化为 ~/，保留子路径用于排查定位
    .replace(PATTERNS.sensitiveFsUserHome, '$1~/')
    .replace(PATTERNS.sensitiveFsWindowsUserHome, '$1~/')
    // 10. 私有内网 IP 端点打码
    .replace(PATTERNS.privateEndpoints, '$1[private-ip]$2');
}

/**
 * 清洗单条错误信息（支持 string、Error 实例或带 message 的结构）
 */
export function redactErrorMessage(input: unknown): string {
  if (input === null || input === undefined) {
    return '';
  }

  if (typeof input === 'string') {
    return redactSensitiveText(input);
  }

  if (input instanceof Error) {
    const sanitizedMsg = redactSensitiveText(input.message);
    const sanitizedError = new Error(sanitizedMsg);
    sanitizedError.name = input.name;
    return sanitizedError.message;
  }

  if (typeof input === 'object') {
    const maybeObj = input as Record<string, unknown>;
    if (typeof maybeObj.message === 'string') {
      return redactSensitiveText(maybeObj.message);
    }
    if (typeof maybeObj.detail === 'string') {
      return redactSensitiveText(maybeObj.detail);
    }
    try {
      return redactSensitiveText(JSON.stringify(redactErrorObject(maybeObj)));
    } catch {
      return redactSensitiveText(String(input));
    }
  }

  return redactSensitiveText(String(input));
}

/**
 * 递归清洗错误数据对象（支持 FastAPI 422 验证错误等结构）
 * 杜绝 detail[].input 中回显用户的私钥或明文密码。
 */
export function redactErrorObject<T>(obj: T): T {
  if (obj === null || obj === undefined || typeof obj !== 'object') {
    if (typeof obj === 'string') {
      return redactSensitiveText(obj) as unknown as T;
    }
    return obj;
  }

  if (Array.isArray(obj)) {
    return obj.map((item) => redactErrorObject(item)) as unknown as T;
  }

  const record = obj as Record<string, unknown>;
  const result: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(record)) {
    const lowerKey = key.toLowerCase();
    if (
      lowerKey === 'input' ||
      lowerKey.includes('secret') ||
      lowerKey.includes('token') ||
      lowerKey.includes('password') ||
      lowerKey.includes('api_key') ||
      lowerKey.includes('apikey')
    ) {
      if (typeof value === 'string') {
        result[key] = maskToken(value);
      } else {
        result[key] = redactErrorObject(value);
      }
    } else if (typeof value === 'string') {
      result[key] = redactSensitiveText(value);
    } else if (typeof value === 'object' && value !== null) {
      result[key] = redactErrorObject(value);
    } else {
      result[key] = value;
    }
  }

  return result as T;
}

/**
 * 格式化 UI 错误显示文本
 */
export function formatUiError(error: unknown, fallback = 'Unknown error occurred'): string {
  if (!error) {
    return fallback;
  }

  const sanitized = redactErrorMessage(error);
  return sanitized || fallback;
}
