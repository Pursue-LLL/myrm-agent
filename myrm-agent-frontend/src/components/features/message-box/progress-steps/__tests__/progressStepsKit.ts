import { vi } from 'vitest';

import type { ProgressItem } from '@/store/chat/types';
import type { StepNodeContext } from '../ProgressStepNode';
import type { TreeNode } from '../treeUtils';

/** Echoes the key, followed by the interpolation values when there are any: `key:{"count":3}`. */
export const translate = (key: string, values?: Record<string, string | number>): string =>
  values === undefined ? key : `${key}:${JSON.stringify(values)}`;

/** The fill token `destructive` used as a text colour: the contrast bug the destructive-text token replaces. */
export const BARE_DESTRUCTIVE_TEXT = /(?<![\w-])text-destructive(?![\w-])/;

/** A finished step titled "Alpha": its key carries no translation, so the title is the key made readable. */
export const makeStep = (overrides: Partial<ProgressItem> = {}): ProgressItem => ({
  step_key: 'alpha',
  status: 'success',
  ...overrides,
});

/** A search tool call's items. They arrive as `{ pattern }` objects that the stream's `items` type does not list. */
export const searchItems = (pattern: string): ProgressItem['items'] =>
  [{ pattern }] as unknown as ProgressItem['items'];

export const makeNode = (step: ProgressItem, originalIndex = 0, children: TreeNode[] = []): TreeNode => ({
  step,
  originalIndex,
  children,
});

export const makeContext = (overrides: Partial<StepNodeContext> = {}): StepNodeContext => ({
  messageId: 'msg-1',
  lastIndex: 0,
  loading: false,
  t: translate,
  tHumanize: translate,
  onViewDetail: vi.fn(),
  ...overrides,
});
