/**
 * 棘轮基线的收紧规则，硬编码文案门禁与无障碍门禁共用。
 *
 * 为什么基线只能收紧：基线是“存量上限”。若写基线 = 用当前值覆盖，那么新增退化的作者（或在脏工作区里
 * 混入他人未完成改动的人）只要运行一次写基线命令，门禁就被自己刷绿了。收紧写入只取
 * `min(当前, 基线)`：额度只会降低，既不会新增基线里没有的条目，也不会抬高已有条目。
 * 确需放宽上限时手改基线 JSON，改动会作为显式 diff 出现在评审里。
 */

export type CountMap = Readonly<Record<string, number>>;

/**
 * 以基线为骨架逐项取 `min(当前, 基线)`：保持基线的条目顺序，不新增条目，当前值缺失或降到 0 的条目移除。
 */
export function tightenCounts(current: CountMap, baseline: CountMap): Record<string, number> {
  const tightened: Record<string, number> = {};
  for (const [key, limit] of Object.entries(baseline)) {
    const value = Math.min(current[key] ?? 0, limit);
    if (value > 0) {
      tightened[key] = value;
    }
  }
  return tightened;
}
