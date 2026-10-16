/**
 * 孤儿门禁的 diff 模式（`check-orphan-modules.mjs --base REV`）：只有“本次改动之后才成为孤儿”的模块失败。
 *
 * 绝对口径要求全树零孤儿，而进行中的功能分支会长时间留下未接入的模块，门禁因此无处可跑。diff 模式取
 * HEAD 与 `REV` 的 merge-base 作为对照：一个模块当前是孤儿、在 merge-base 也是孤儿，就是存量，不算本次引入；
 * 当前是孤儿、在 merge-base 不是（新增未接入，或本次改动切断了它的最后一个消费者），才失败。
 * 按路径比较：移动或重命名一个存量孤儿，它在新路径上会再次被报告——改路径不是接入入口的理由。
 *
 * 没有基线文件，也没有豁免：对照树每次从 git 现取。凡是无法确定对照的情形（非 git 树、修订不存在、无共同祖先、
 * 对照树缺少所需目录）一律抛 `BaseUnavailableError`，调用方必须 fail-closed，不能静默放行。
 */
import { execFileSync } from 'node:child_process';
import { extname } from 'node:path';

const GIT_TIMEOUT_MS = 120_000;
const GIT_MAX_BUFFER_BYTES = 1 << 30;

/** 对照修订无法确定；门禁必须失败而不是放行。 */
export class BaseUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'BaseUnavailableError';
  }
}

export interface BaseTreeRequest {
  /** 前端项目根（可以是 git 仓库的子目录）。 */
  readonly projectRoot: string;
  readonly rev: string;
  /** 把对照树写到这个已存在的空目录。 */
  readonly destination: string;
  /** 一并取出的项目子目录（扫描入口：`src`、`scripts`）。 */
  readonly directories: readonly string[];
  /** 一并取出的项目根文件扩展名（构建配置，带点）。 */
  readonly rootExtensions: ReadonlySet<string>;
}

function git(cwd: string, args: readonly string[], input?: Buffer): Buffer {
  try {
    return execFileSync('git', args, {
      cwd,
      input,
      maxBuffer: GIT_MAX_BUFFER_BYTES,
      timeout: GIT_TIMEOUT_MS,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
  } catch (error) {
    const failure = error as Error & { stderr?: Buffer };
    throw new BaseUnavailableError(`git ${args[0]} 失败: ${failure.stderr?.toString().trim() || failure.message}`);
  }
}

/** `git ls-tree -z` 的直接子文件名（不含目录与子模块）。 */
function blobNames(cwd: string, tree: string): string[] {
  return git(cwd, ['ls-tree', '-z', tree])
    .toString()
    .split('\0')
    .flatMap((entry) => {
      const [meta, name] = entry.split('\t');
      return name && meta.split(' ')[1] === 'blob' ? [name] : [];
    });
}

/**
 * 把 HEAD 与 `rev` 的 merge-base 上的扫描输入（目录 + 根配置文件）写入 `destination`，返回 merge-base 的提交号。
 */
export function materializeBase({
  projectRoot,
  rev,
  destination,
  directories,
  rootExtensions,
}: BaseTreeRequest): string {
  if (rev.startsWith('-')) {
    throw new BaseUnavailableError(`不是合法的修订: ${rev}`);
  }
  const prefix = git(projectRoot, ['rev-parse', '--show-prefix']).toString().trim().replace(/\/$/, '');
  // `git archive` 在子目录里运行时会把子目录前缀当作树内路径解析，对照树就找不到它；改在仓库根运行。
  const repoRoot = git(projectRoot, ['rev-parse', '--show-toplevel']).toString().trim();
  const base = git(repoRoot, ['merge-base', 'HEAD', rev]).toString().trim();
  const tree = `${base}:${prefix}`;
  const rootFiles = blobNames(repoRoot, tree).filter(
    (name) => rootExtensions.has(extname(name)) && !name.endsWith('.d.ts'),
  );
  const archive = git(repoRoot, ['archive', '--format=tar', tree, '--', ...directories, ...rootFiles]);
  try {
    execFileSync('tar', ['-x', '-C', destination], { input: archive, stdio: ['pipe', 'pipe', 'pipe'] });
  } catch (error) {
    throw new BaseUnavailableError(`解包对照树失败: ${(error as Error).message}`);
  }
  return base;
}

/** 当前是孤儿、而在对照树不是孤儿的模块：本次改动新增未接入的，或切断了最后一个消费者的。 */
export function introducedOrphans(head: readonly string[], base: readonly string[]): string[] {
  const existing = new Set(base);
  return head.filter((path) => !existing.has(path));
}
