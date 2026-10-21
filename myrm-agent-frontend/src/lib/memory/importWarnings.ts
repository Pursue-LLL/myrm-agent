/**
 * [INPUT]
 * None (pure formatting helper).
 *
 * [OUTPUT]
 * ImportWarningTranslator, resolveImportWarning: 记忆导入告警码到用户文案的解析函数。
 *
 * [POS]
 * 记忆域前端纯函数。告警码到文案的唯一映射是 `memory.importWarnings` 命名空间，
 * 迁移向导与导入审阅弹窗共用此处解析，保证同一告警码只有一套文案。
 */

export interface ImportWarningTranslator {
  (key: string): string;
  has: (key: string) => boolean;
}

const WARNING_CODE_PATTERN = /^[a-z0-9]+(?:_[a-z0-9]+)+$/;

const humanizeWarningCode = (code: string): string =>
  code
    .split('_')
    .filter(Boolean)
    .map((part, index) => (index === 0 ? part.charAt(0).toUpperCase() + part.slice(1) : part))
    .join(' ');

export const resolveImportWarning = (warning: string, t: ImportWarningTranslator): string => {
  if (t.has(warning)) {
    return t(warning);
  }
  // Unknown codes fall back to a readable sentence instead of leaking the raw identifier.
  return WARNING_CODE_PATTERN.test(warning) ? humanizeWarningCode(warning) : warning;
};
