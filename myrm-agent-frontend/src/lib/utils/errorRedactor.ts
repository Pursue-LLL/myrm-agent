/**
 * [INPUT] None (zero-dependency pure utility)
 * [OUTPUT] redactErrorMessage, redactErrorObject, redactErrorPayload, maskToken, REDACTION_MASK
 * [POS] Control UI 全面错误展示脱敏引擎。统一对 Toast、API 响应解析和内联错误文本执行不可逆高敏感字段抹除。
 */

export const REDACTION_MASK = '***REDACTED***';

/**
 * 将高熵 Token 安全掩码，保留前后几位供用户识别是哪个 Key，中间打码
 * 例: sk-proj-1234567890abcdef123456 -> sk-p...456
 */
export function maskToken(token: string): string {
  if (!token || token.length <= 10) {
    return REDACTION_MASK;
  }
  return `${token.slice(0, 4)}...${token.slice(-3)}`;
}

/**
 * 敏感凭证与高危信息匹配模式集
 */
const PATTERNS = {
  // 1. 常见平台 API 密钥与凭证 (OpenAI, Anthropic, GitHub, Slack, HuggingFace, GitLab 等)
  apiKeys: /\b(?:sk|ghp|gho|ghu|ghs|ghr|xoxb|xoxp|xapp|xoxa|glpat|npm_|hf_)[A-Za-z0-9_\-]{16,}\b/g,

  // 2. HTTP Bearer 认证头部
  bearerTokens: /\bBearer\s+[A-Za-z0-9_\-.]{16,}\b/gi,

  // 3. JWT 三段式 Token
  jwtTokens: /\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/g,

  // 4. AWS 访问密钥
  awsKeys: /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g,

  // 5. 键值对型凭证 (如 token=abc, password: 123)
  keyValueSecrets: /\b(token|password|secret|api_key|apikey|auth_token|client_secret)\s*([:=])\s*["']?([^\s"',;]{6,})["']?/gi,

  // 6. 数据库与消息队列 URI 密码 (postgres://user:password@host)
  dbUriCredentials: /\b((?:postgres(?:ql)?|mysql|mariadb|redis(?:s)?|mongodb(?:\+srv)?|amqp(?:s)?):\/\/[^:\s\/]+:)([^@\s]+)(@)/gi,

  // 7. 本地用户主目录路径 (macOS / Linux / Windows)
  macHomePaths: /(^|[\s"'(])\/Users\/[^\/\s"')]+/g,
  linuxHomePaths: /(^|[\s"'(])\/home\/[^\/\s"')]+/g,
  windowsHomePaths: /(^|[\s"'(])[A-Za-z]:\\Users\\[^\\/\s"')]+/g,

  // 8. 错误信息中内网私有 IP 地址端点 (RFC1918)
  privateEndpoints: /\b(https?:\/\/)(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(:\d+)?\b/gi,
};

/**
 * 清洗单条错误文本字符串
 * 针对高熵凭据、系统路径、数据库密码执行精确打码，同时保留错误排查上下文。
 */
export function redactErrorMessage(input: unknown): string {
  if (input === null || input === undefined) {
    return '';
  }

  let text: string;

  if (typeof input === 'string') {
    text = input;
  } else if (input instanceof Error) {
    text = input.message || String(input);
  } else if (typeof input === 'object') {
    const maybeObj = input as Record<string, unknown>;
    if (typeof maybeObj.message === 'string') {
      text = maybeObj.message;
    } else if (typeof maybeObj.detail === 'string') {
      text = maybeObj.detail;
    } else {
      try {
        text = JSON.stringify(redactErrorObject(maybeObj));
      } catch {
        text = String(input);
      }
    }
  } else {
    text = String(input);
  }

  if (!text) {
    return '';
  }

  return text
    // 1. API Keys 打码 (保留前后几位辅助排查)
    .replace(PATTERNS.apiKeys, (match) => maskToken(match))
    // 2. Bearer Token 打码
    .replace(PATTERNS.bearerTokens, `Bearer ${REDACTION_MASK}`)
    // 3. JWT 打码
    .replace(PATTERNS.jwtTokens, REDACTION_MASK)
    // 4. AWS Key 打码
    .replace(PATTERNS.awsKeys, (match) => maskToken(match))
    // 5. 键值对凭据打码
    .replace(PATTERNS.keyValueSecrets, (_match, key, sep) => `${key}${sep}${REDACTION_MASK}`)
    // 6. 数据库 URI 密码打码
    .replace(PATTERNS.dbUriCredentials, (_match, prefix, _pwd, suffix) => `${prefix}${REDACTION_MASK}${suffix}`)
    // 7. 本地主目录路径打码为 ~
    .replace(PATTERNS.macHomePaths, '$1~')
    .replace(PATTERNS.linuxHomePaths, '$1~')
    .replace(PATTERNS.windowsHomePaths, '$1~')
    // 8. 私有内网 IP 端点打码
    .replace(PATTERNS.privateEndpoints, '$1[private-ip]$2');
}

/**
 * 递归清洗错误数据对象（支持 FastAPI 422 验证错误等结构）
 * 杜绝 detail[].input 中回显用户的私钥或明文密码。
 */
export function redactErrorObject<T>(obj: T): T {
  if (obj === null || obj === undefined || typeof obj !== 'object') {
    if (typeof obj === 'string') {
      return redactErrorMessage(obj) as unknown as T;
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
    // 敏感字段或 FastAPI Pydantic V2 校验失败回显字段
    if (
      lowerKey === 'input' ||
      lowerKey.includes('secret') ||
      lowerKey.includes('token') ||
      lowerKey.includes('password') ||
      lowerKey.includes('api_key') ||
      lowerKey.includes('apikey')
    ) {
      if (typeof value === 'string') {
        result[key] = REDACTION_MASK;
      } else {
        result[key] = redactErrorObject(value);
      }
    } else if (typeof value === 'string') {
      result[key] = redactErrorMessage(value);
    } else if (typeof value === 'object' && value !== null) {
      result[key] = redactErrorObject(value);
    } else {
      result[key] = value;
    }
  }

  return result as T;
}

/**
 * 兼容旧版/同义词导出
 */
export const redactErrorPayload = redactErrorObject;
