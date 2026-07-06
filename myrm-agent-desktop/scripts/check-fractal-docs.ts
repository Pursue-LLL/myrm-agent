/**
 * [INPUT]
 * - myrm-agent-desktop 仓内 _ARCH.md 清单与核心 Rust/脚本路径
 *
 * [OUTPUT]
 * - 分形文档门禁：必检 _ARCH 存在；核心文件含 [INPUT] 头注释
 *
 * [POS]
 * 桌面仓分形自文档 CI 守门。对齐 myrm-agent-brand/scripts/check-fractal-docs.ts 清单式 gate。
 */
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const DESKTOP_ROOT = join(import.meta.dir, '..');

/** Module _ARCH.md paths relative to myrm-agent-desktop root. */
const REQUIRED_ARCH_PATHS = [
  '_ARCH.md',
  'scripts/_ARCH.md',
  'sidecar/_ARCH.md',
  'src-tauri/src/_ARCH.md',
] as const;

/** Core source files that must declare fractal [INPUT] headers. */
const CORE_IOP_PATHS = [
  'src-tauri/src/main.rs',
  'src-tauri/src/config.rs',
  'scripts/check-fractal-docs.ts',
] as const;

const HEADER_SCAN_LINES = 20;
const INPUT_MARKER = '[INPUT]';

export function collectFractalDocViolations(): string[] {
  const errors: string[] = [];

  for (const rel of REQUIRED_ARCH_PATHS) {
    const abs = join(DESKTOP_ROOT, rel);
    if (!existsSync(abs)) {
      errors.push(`missing required doc: ${rel}`);
    }
  }

  for (const rel of CORE_IOP_PATHS) {
    const abs = join(DESKTOP_ROOT, rel);
    if (!existsSync(abs)) {
      errors.push(`missing core file for IOP check: ${rel}`);
      continue;
    }
    const head = readFileSync(abs, 'utf8')
      .split('\n')
      .slice(0, HEADER_SCAN_LINES)
      .join('\n');
    if (!head.includes(INPUT_MARKER)) {
      errors.push(`missing ${INPUT_MARKER} in first ${HEADER_SCAN_LINES} lines: ${rel}`);
    }
  }

  return errors;
}

export function assertFractalDocsCompliant(): void {
  const errors = collectFractalDocViolations();
  if (errors.length > 0) {
    throw new Error(`Fractal documentation gate failed:\n${errors.join('\n')}`);
  }
}

if (import.meta.main) {
  const errors = collectFractalDocViolations();
  if (errors.length > 0) {
    console.error('Fractal documentation gate failed:\n' + errors.join('\n'));
    process.exit(1);
  }
  console.log(
    `Fractal docs OK (${REQUIRED_ARCH_PATHS.length} arch paths, ${CORE_IOP_PATHS.length} IOP files)`,
  );
}
