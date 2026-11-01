/**
 * 硬编码文案棘轮的比较规则：按文件对比当前数量与基线，只降不升。
 *
 * - 高于基线（含基线里没有的新文件，其基线视为 0）→ `increased`：新增了硬编码文案；
 * - 低于基线（含文件已删除或改名，其当前值视为 0）→ `drifted`：已改善但基线没有收紧，
 *   不收紧的话空出的额度会被后续改动悄悄占用。
 *
 * 按文件而非总数比较：一个文件清掉的额度不能抵扣另一个文件的新增。
 *
 * 比较的范围只含从产品入口可达的文件（`partitionByReachability`）：孤儿模块没有任何页面渲染它，用户看不到它的文案，
 * 它由孤儿门禁管；孤儿被接入产品入口的那一刻起变成可达，其字面量按「基线里没有的新文件」计数，必须先走 i18n。
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

export interface ReachabilityPartition<Site> {
  /** 从产品入口可达的文件：参与基线比较。 */
  reachable: Map<string, Site[]>;
  /** 孤儿模块里的文件：不参与基线比较，只用于如实报告数量。 */
  orphaned: Map<string, Site[]>;
}

/** 按文件是否是孤儿模块划分各文件的字面量；`orphans` 是相对项目根的 posix 路径集合。 */
export function partitionByReachability<Site>(
  sitesByFile: ReadonlyMap<string, Site[]>,
  orphans: ReadonlySet<string>,
): ReachabilityPartition<Site> {
  const reachable = new Map<string, Site[]>();
  const orphaned = new Map<string, Site[]>();
  for (const [file, sites] of sitesByFile) {
    (orphans.has(file) ? orphaned : reachable).set(file, sites);
  }
  return { reachable, orphaned };
}
