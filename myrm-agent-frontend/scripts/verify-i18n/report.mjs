/**
 * [INPUT] 无（只写 stderr；hasErrors 由调用方置位）
 * [OUTPUT] reportKeys / reportShells
 * [POS] verify-i18n 的违规打印：统一「标题 + 前 N 条键」格式，截断口径在各门禁间一致。
 */

/** 打印标题与前 `limit` 条违规键；超出部分不展开。 */
export function reportKeys(message, keys, limit = 10) {
  console.error(message);
  keys.slice(0, limit).forEach((key) => console.error(`     - ${key}`));
}

/** 打印翻译壳（值与英文一致）：前 15 条带值预览，其余只给总数。 */
export function reportShells(ctx, locale, shells) {
  if (shells.length === 0) {
    return;
  }
  console.error(`  ❌ ${locale}.json 存在 ${shells.length} 个翻译壳（值与英文一致）：`);
  shells.slice(0, 15).forEach(({ path, value }) => {
    console.error(`     - ${path} = ${JSON.stringify(value.slice(0, 80))}`);
  });
  if (shells.length > 15) {
    console.error(`     ... 还有 ${shells.length - 15} 个`);
  }
  ctx.hasErrors = true;
}
