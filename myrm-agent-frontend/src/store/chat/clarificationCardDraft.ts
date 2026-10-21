/**
 * [OUTPUT]
 * - ClarificationDraft: what the clarification card keeps of the user's unsent input
 * - saveClarificationDraft / loadClarificationDraft / clearClarificationDraft: per-card draft, held in memory only
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

const drafts = new Map<string, ClarificationDraft>();

export function saveClarificationDraft(messageId: string, draft: ClarificationDraft): void {
  drafts.set(messageId, draft);
}

export function loadClarificationDraft(messageId: string): ClarificationDraft | undefined {
  return drafts.get(messageId);
}

export function clearClarificationDraft(messageId: string): void {
  drafts.delete(messageId);
}
