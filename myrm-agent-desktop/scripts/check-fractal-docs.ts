/**
 * [INPUT]
 * - myrm-agent-desktop 仓内 _ARCH.md 清单、核心 Rust/TS 路径、行数预算 baseline
 *
 * [OUTPUT]
 * - 分形文档门禁：必检 _ARCH、核心 [INPUT] 头、Rust 源文件行数预算
 *
 * [POS]
 * 桌面仓分形自文档 CI 守门。对齐 server/frontend check_fractal_docs + check_file_line_budget 纪律。
 */
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const DESKTOP_ROOT = join(import.meta.dir, '..');
const RUST_SRC_ROOT = join(DESKTOP_ROOT, 'src-tauri/src');
const MAX_LINES = 400;
const HEADER_SCAN_LINES = 25;
const INPUT_MARKER = '[INPUT]';

/** Module _ARCH.md paths relative to myrm-agent-desktop root. */
const REQUIRED_ARCH_PATHS = [
  '_ARCH.md',
  'ARCHITECTURE.md',
  'scripts/_ARCH.md',
  'sidecar/_ARCH.md',
  'sidecar/agent-runner/_ARCH.md',
  'src-tauri/src/_ARCH.md',
  'src-tauri/src/runtime/_ARCH.md',
  'src-tauri/src/commands/_ARCH.md',
  'src-tauri/src/utils/_ARCH.md',
  'src-tauri/src/agent_runner_rpc/_ARCH.md',
  'src-tauri/src/sessions/_ARCH.md',
  'src-tauri/src/permissions/_ARCH.md',
  'src-tauri/src/app/_ARCH.md',
  'src-tauri/src/runtime/appshot/_ARCH.md',
  'src-tauri/frontend-shell/_ARCH.md',
] as const;

/** Core source files that must declare fractal [INPUT] headers. */
const CORE_IOP_PATHS = [
  'src-tauri/src/main.rs',
  'src-tauri/src/config.rs',
  'src-tauri/src/runtime/mod.rs',
  'src-tauri/src/runtime/python_backend.rs',
  'src-tauri/src/runtime/agent_runner.rs',
  'src-tauri/src/agent_runner_rpc/mod.rs',
  'src-tauri/src/runtime/appshot/mod.rs',
  'src-tauri/src/runtime/inline_input.rs',
  'src-tauri/src/runtime/watchdog.rs',
  'src-tauri/src/sessions/mod.rs',
  'src-tauri/src/app/lifecycle.rs',
  'src-tauri/src/app/tray.rs',
  'src-tauri/src/cli_agent_types.rs',
  'src-tauri/src/utils/updater_safety.rs',
  'scripts/check-fractal-docs.ts',
] as const;

const LINE_BUDGET_BASELINE_PATH = join(import.meta.dir, 'ci', 'rust_line_budget_baseline.txt');

function loadLineBudgetBaseline(): Set<string> {
  if (!existsSync(LINE_BUDGET_BASELINE_PATH)) {
    return new Set();
  }
  const entries = new Set<string>();
  for (const line of readFileSync(LINE_BUDGET_BASELINE_PATH, 'utf8').split('\n')) {
    const stripped = line.trim();
    if (!stripped || stripped.startsWith('#')) {
      continue;
    }
    entries.add(stripped);
  }
  return entries;
}

function collectRustSourceFiles(dir: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const abs = join(dir, entry);
    const st = statSync(abs);
    if (st.isDirectory()) {
      collectRustSourceFiles(abs, acc);
    } else if (entry.endsWith('.rs')) {
      acc.push(abs);
    }
  }
  return acc;
}

function countLines(absPath: string): number {
  return readFileSync(absPath, 'utf8').split('\n').length;
}

function hasInputHeader(relPath: string): boolean {
  const abs = join(DESKTOP_ROOT, relPath);
  const head = readFileSync(abs, 'utf8')
    .split('\n')
    .slice(0, HEADER_SCAN_LINES)
    .join('\n');
  return head.includes(INPUT_MARKER);
}

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
    if (!hasInputHeader(rel)) {
      errors.push(`missing ${INPUT_MARKER} in first ${HEADER_SCAN_LINES} lines: ${rel}`);
    }
  }

  const baseline = loadLineBudgetBaseline();
  const rustFiles = collectRustSourceFiles(RUST_SRC_ROOT);
  for (const abs of rustFiles) {
    const rel = relative(DESKTOP_ROOT, abs).replaceAll('\\', '/');
    const lines = countLines(abs);
    if (lines > MAX_LINES && !baseline.has(rel)) {
      errors.push(`line budget exceeded (${lines} > ${MAX_LINES}): ${rel}`);
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
    `Fractal docs OK (${REQUIRED_ARCH_PATHS.length} arch paths, ${CORE_IOP_PATHS.length} IOP files, line budget ${MAX_LINES})`,
  );
}
