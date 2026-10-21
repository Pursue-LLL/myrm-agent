/**
 * [INPUT]
 * - Nothing (pure URL builders, no I/O)
 *
 * [OUTPUT]
 * - IdeHandoffTarget / IDE_HANDOFF_TARGETS: supported external IDEs
 * - buildIdeDeepLink: OS-handled deep link that opens the IDE
 *
 * [POS]
 * External IDE handoff deep-link builder. The transcript payload travels via
 * the existing chat export + clipboard path; this module only decides which
 * application the OS should activate.
 */

export type IdeHandoffTarget = 'cursor' | 'vscode';

export const IDE_HANDOFF_TARGETS: readonly IdeHandoffTarget[] = ['cursor', 'vscode'];

const IDE_DEEP_LINKS: Record<IdeHandoffTarget, string> = {
  cursor: 'cursor://',
  vscode: 'vscode://',
};

export function buildIdeDeepLink(target: IdeHandoffTarget): string {
  return IDE_DEEP_LINKS[target];
}

export function isIdeHandoffTarget(value: string): value is IdeHandoffTarget {
  return (IDE_HANDOFF_TARGETS as readonly string[]).includes(value);
}
