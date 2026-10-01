/**
 * [INPUT] 纯文本输入（聊天消息、思考过程、单条消息导出内容）。
 * [OUTPUT] redactSensitiveClientText, containsSensitiveData.
 * [POS] 客户端轻量敏感凭据脱敏清洗工具（OpenAI/GitHub/AWS/私钥/JWT/密钥对脱敏，CWE-312 防护）。
 */

const REDACTION_PATTERNS: Array<{ regex: RegExp; replace: (substring: string, ...args: string[]) => string }> = [
  // 1. PEM 私钥
  {
    regex: /-----BEGIN [A-Z0-9_ ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9_ ]*PRIVATE KEY-----/g,
    replace: () => '[REDACTED_PRIVATE_KEY]',
  },
  // 2. OpenAI / Anthropic 风格 API Keys (sk-...)
  {
    regex: /\bsk-[A-Za-z0-9_\-]{20,}\b/g,
    replace: () => '[REDACTED_API_KEY]',
  },
  // 3. GitHub Tokens (ghp_, gho_, ghu_, ghs_, ghr_, github_pat_)
  {
    regex: /\b(gh[pousr]_[A-Za-z0-9_]{36,}|github_pat_[A-Za-z0-9_]{40,})\b/g,
    replace: () => '[REDACTED_GH_TOKEN]',
  },
  // 4. AWS Access Key ID (AKIA...)
  {
    regex: /\bAKIA[0-9A-Z]{16}\b/g,
    replace: () => '[REDACTED_AWS_KEY]',
  },
  // 5. Authorization: Bearer <token>
  {
    regex: /(authorization:\s*bearer\s+)[A-Za-z0-9_\-\.]{16,}/gi,
    replace: (_match, prefix: string) => `${prefix}[REDACTED_TOKEN]`,
  },
  // 6. JWT Tokens
  {
    regex: /\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_\-.]{10,}\b/g,
    replace: () => '[REDACTED_JWT]',
  },
  // 7. 常见配置键值中的密钥与密码 (api_key=..., password: "...", etc.)，避免二次覆盖已有 [REDACTED_ 标记
  {
    regex:
      /((?:api[_-]?key|access[_-]?token|secret[_-]?key|password|db_pass)\s*[:=]\s*["']?)(?!\[?REDACTED_)([^"'\s\r\n]{8,})(["']?)/gi,
    replace: (_match, prefix: string, _secret: string, suffix: string) => `${prefix}[REDACTED_SECRET]${suffix}`,
  },
];

/**
 * 清洗客户端导出文本中的敏感认证凭据，防御 CWE-312 敏感信息明文泄露。
 */
export function redactSensitiveClientText(text: string): string {
  if (!text) {
    return text;
  }
  let result = text;
  for (const { regex, replace } of REDACTION_PATTERNS) {
    result = result.replace(regex, replace as (substring: string, ...args: unknown[]) => string);
  }
  return result;
}

/**
 * 检查文本是否命中任何敏感信息特征。
 */
export function containsSensitiveData(text: string): boolean {
  if (!text) {
    return false;
  }
  for (const { regex } of REDACTION_PATTERNS) {
    regex.lastIndex = 0;
    if (regex.test(text)) {
      return true;
    }
  }
  return false;
}
