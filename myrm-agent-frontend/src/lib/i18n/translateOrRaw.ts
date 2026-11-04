/**
 * [INPUT]
 * - next-intl 翻译器（`useTranslations` / `getTranslations` 的返回值，需带 `has`）
 *
 * [OUTPUT]
 * - KeyedTranslator: 翻译器的最小结构契约
 * - translateOrRaw: 语言包有该键就翻译，没有就原样展示服务端给的值
 *
 * [POS]
 * 展示服务端开放词表（权限名、来源标签、错误类别等）的统一兜底。next-intl 缺键时返回键路径本身，
 * 且不读取 `defaultValue`；必须先 `has` 判断，未知值才会显示成可读的原文而不是 `ns.key`。
 */

export interface KeyedTranslator {
  (key: string): string;
  has: (key: string) => boolean;
}

export function translateOrRaw(t: KeyedTranslator, key: string, raw: string): string {
  return t.has(key) ? t(key) : raw;
}
