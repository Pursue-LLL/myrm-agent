/**
 * [OUTPUT]
 * - HitlCardKind: card fields of an assistant row that take over the composer while pending
 * - HitlCardDrafts: what each card kind keeps of the user's unsent input
 * - saveHitlCardDraft / loadHitlCardDraft / clearHitlCardDraft: per-card draft, held in memory only
 *
 * [POS]
 * A card closes at click and the composer takeover unmounts it, so a resume that is then refused would bring it back
 * empty. The draft carries what the user wrote across that gap; it is dropped once the answer is settled.
 */

export interface ClarificationDraft {
  input: string;
  selectedOptions: string[];
  formTexts: Record<string, string>;
  formSelections: Record<string, string[]>;
}

export interface DirectoryDraft {
  path: string;
  writable: boolean;
}

export interface HitlCardDrafts {
  clarification: ClarificationDraft;
  directoryRequest: DirectoryDraft;
}

export type HitlCardKind = keyof HitlCardDrafts;

const drafts: { [K in HitlCardKind]: Map<string, HitlCardDrafts[K]> } = {
  clarification: new Map(),
  directoryRequest: new Map(),
};

export function saveHitlCardDraft<K extends HitlCardKind>(kind: K, messageId: string, draft: HitlCardDrafts[K]): void {
  drafts[kind].set(messageId, draft);
}

export function loadHitlCardDraft<K extends HitlCardKind>(kind: K, messageId: string): HitlCardDrafts[K] | undefined {
  return drafts[kind].get(messageId);
}

export function clearHitlCardDraft(kind: HitlCardKind, messageId: string): void {
  drafts[kind].delete(messageId);
}
