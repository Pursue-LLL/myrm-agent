/**
 * `bun run lint` 的门禁聚合器：把全部静态门禁跑完，再汇总失败项。
 *
 * 用 `&&` 串联时，第一个红灯会让后面的门禁根本没有执行，一次运行只能暴露一个问题，
 * 后面的门禁在 CI 里等于不存在。这里每个门禁都执行，退出码在任一门禁失败时为 1。
 *
 * 门禁清单只在 `LINT_GATES` 维护，本地与 CI 共用；每项都是 `package.json` 里的脚本名，
 * 脚本本身仍可单独运行（如 `bun run verify:a11y`）。
 */
import { spawnSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

/** 门禁清单（`package.json` 脚本名），按执行顺序排列。 */
export const LINT_GATES: readonly string[] = [
  'verify:stable-mocks',
  'verify:a11y',
  'verify:theme-colors',
  'verify:reduced-motion',
  'verify:hardcoded-copy',
  'verify:icu-syntax',
  'lint:oxlint',
];

/** 执行单个门禁并返回退出码；被信号终止等拿不到退出码的情况按失败处理。 */
export type GateExecutor = (script: string) => number;

/** 依次执行全部门禁，不因失败中断，返回失败的门禁名（保持执行顺序）。 */
export function runGates(gates: readonly string[], execute: GateExecutor): string[] {
  return gates.filter((script) => execute(script) !== 0);
}

function main(): void {
  const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
  const failed = runGates(LINT_GATES, (script) => {
    const run = spawnSync(process.execPath, ['run', script], { cwd: rootDir, stdio: 'inherit' });
    return run.status ?? 1;
  });

  if (failed.length > 0) {
    console.error(`\n[lint-gates] ${failed.length}/${LINT_GATES.length} 个门禁失败：${failed.join(', ')}`);
    process.exit(1);
  }
  console.log(`\n[lint-gates] OK：${LINT_GATES.length} 个门禁全部通过。`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
