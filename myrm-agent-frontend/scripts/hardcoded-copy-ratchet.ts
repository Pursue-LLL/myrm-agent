/**
 * 硬编码文案棘轮的比较规则：按文件对比当前数量与基线，只降不升。
 *
 * - 高于基线（含基线里没有的新文件，其基线视为 0）→ `increased`：新增了硬编码文案；
 * - 低于基线（含文件已删除或改名，其当前值视为 0）→ `drifted`：已改善但基线没有收紧，
 *   不收紧的话空出的额度会被后续改动悄悄占用。
 *
 * 按文件而非总数比较：一个文件清掉的额度不能抵扣另一个文件的新增。
 */

/** 文件路径 → 该文件里硬编码文案的数量。 */
export type CopyCounts = Readonly<Record<string, number>>;

export interface RatchetDiff {
  increased: string[];
  drifted: string[];
}

export function diffAgainstBaseline(current: CopyCounts, baseline: CopyCounts): RatchetDiff {
  const files = [...new Set([...Object.keys(baseline), ...Object.keys(current)])].sort();
  const countOf = (counts: CopyCounts, file: string): number => counts[file] ?? 0;
  return {
    increased: files.filter((file) => countOf(current, file) > countOf(baseline, file)),
    drifted: files.filter((file) => countOf(current, file) < countOf(baseline, file)),
  };
}
