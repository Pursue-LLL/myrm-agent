/**
 * 文案 ICU 语法有效性扫描：用 next-intl 运行时同款解析器（`icu-minify` 编译时调用的
 * `@formatjs/icu-messageformat-parser`，默认选项）逐条解析 locale 树里的字符串叶子（数组逐元素），
 * 返回解析失败的文案。
 *
 * 解析失败时运行时拿不到编译结果：开发构建对含 `{` 或 `<` 的文案一律编译，抛 `INVALID_MESSAGE`；
 * 生产构建只在传了插值参数或含 `'{` 一类转义序列时编译，其余直接返回原文——同一条文案在两种构建里表现不同，
 * 所以只能在源头按语法有效性拦截，不能依赖运行时表现。
 */
import { parse } from '@formatjs/icu-messageformat-parser';

export interface InvalidIcuMessage {
  /** 文案在 locale 树里的点分路径，数组元素用下标。 */
  path: string;
  /** 解析器给出的错误类别，如 `MALFORMED_ARGUMENT`、`UNCLOSED_TAG`。 */
  error: string;
}

export interface IcuScanResult {
  /** 实际解析的字符串叶子数，用于门禁的反向自检。 */
  scanned: number;
  invalid: InvalidIcuMessage[];
}

/** 解析器抛出的错误第一行即错误类别。 */
function errorKind(error: unknown): string {
  return (error instanceof Error ? error.message : String(error)).split('\n')[0] ?? 'UNKNOWN';
}

/**
 * 机翻保护标记：批量翻译把品牌 / ICU 占位符换成 `__BR_` / `__PH` 记号，翻译后必须还原。
 * 残留说明还原环节漏了，用户会在界面上看到 `__BR_OAuth2__` 这种内部标记。
 */
const ARTIFACT_RE = /__[A-Z]{2,}_[A-Za-z0-9._-]+|__PH[0-9]+__/;

/** Scan one already-parsed locale tree for leftover translation-pipeline markers. */
export function scanTranslationArtifacts(tree: unknown, prefix = ''): IcuScanResult {
  if (typeof tree === 'string') {
    return ARTIFACT_RE.test(tree)
      ? { scanned: 1, invalid: [{ path: prefix, error: `ARTIFACT ${ARTIFACT_RE.exec(tree)?.[0]}` }] }
      : { scanned: 1, invalid: [] };
  }
  const result: IcuScanResult = { scanned: 0, invalid: [] };
  if (tree === null || typeof tree !== 'object') {
    return result;
  }
  for (const [key, child] of Object.entries(tree)) {
    const nested = scanTranslationArtifacts(child, prefix === '' ? key : `${prefix}.${key}`);
    result.scanned += nested.scanned;
    result.invalid.push(...nested.invalid);
  }
  return result;
}

/** 递归扫描 locale 树；非字符串叶子（数字、布尔、null）不是文案，跳过。 */
export function scanIcuMessages(tree: unknown, prefix = ''): IcuScanResult {
  if (typeof tree === 'string') {
    try {
      parse(tree);
      return { scanned: 1, invalid: [] };
    } catch (error) {
      return { scanned: 1, invalid: [{ path: prefix, error: errorKind(error) }] };
    }
  }
  const result: IcuScanResult = { scanned: 0, invalid: [] };
  if (tree === null || typeof tree !== 'object') {
    return result;
  }
  for (const [key, child] of Object.entries(tree)) {
    const nested = scanIcuMessages(child, prefix === '' ? key : `${prefix}.${key}`);
    result.scanned += nested.scanned;
    result.invalid.push(...nested.invalid);
  }
  return result;
}
