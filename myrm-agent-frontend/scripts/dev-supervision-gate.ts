/**
 * [INPUT]
 * - process.execArgv / process.env.NODE_OPTIONS (POS: where the preload `dev.ts` starts every Next process with shows up)
 *
 * [OUTPUT]
 * - SUPERVISOR_PRELOAD / isSupervised / enforceSupervisedDev
 *
 * [POS]
 * Refuses a `next dev` that `scripts/dev.ts` did not start. Only that supervisor bounds the server's memory
 * (`next-supervisor.ts` replaces a process tree that outgrows its limit); a raw `next dev` has no such bound,
 * so a long session can grow without limit. `dev.ts` starts Next as `node --require next-dev-gate.cjs ...`
 * and nothing else passes that preload to node, so its presence proves supervision: the Next CLI has it in its
 * own `execArgv`, and the server worker the CLI forks (with whatever that spawns) gets it through `NODE_OPTIONS`.
 * It guards against launching the server raw by mistake and is not a security boundary: passing the same flag by
 * hand defeats it. Self-contained: next.config.ts imports it statically and the Docker builder copies only the
 * frontend package.
 */

/** The preload `dev.ts` starts every Next process with (`node --require <it> next dev`). */
export const SUPERVISOR_PRELOAD = 'next-dev-gate.cjs';

export interface NodeFlags {
  execArgv: readonly string[];
  nodeOptions: string | undefined;
}

export function isSupervised({ execArgv, nodeOptions }: NodeFlags): boolean {
  return [...execArgv, nodeOptions ?? ''].some((flags) => flags.includes(SUPERVISOR_PRELOAD));
}

export interface EnforceSupervisedOptions extends Partial<NodeFlags> {
  /** What is being refused, as it reads in the message (for example `next dev (next.config load)`). */
  context: string;
  exit?: (code: number) => never;
}

export function enforceSupervisedDev({
  context,
  execArgv = process.execArgv,
  nodeOptions = process.env.NODE_OPTIONS,
  exit = (code: number): never => process.exit(code),
}: EnforceSupervisedOptions): void {
  if (isSupervised({ execArgv, nodeOptions })) {
    return;
  }
  console.error(
    `❌ Refusing ${context}: it was not started by \`bun run dev\` (no ${SUPERVISOR_PRELOAD} preload), so nothing bounds its memory.`,
  );
  console.error('   Start it with: MYRM_FRONTEND_PORT=<port> bun run dev');
  exit(1);
}
