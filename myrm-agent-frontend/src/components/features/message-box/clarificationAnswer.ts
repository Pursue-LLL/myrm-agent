import type { ClarificationForm } from '@/store/chat/types';

export function buildStructuredClarificationAnswer(
  form: ClarificationForm | undefined,
  formSelections: Record<string, string[]>,
  formTexts: Record<string, string>,
): Record<string, string | string[]> | null {
  const answers: Record<string, string | string[]> = {};

  for (const question of form?.questions ?? []) {
    const selected = formSelections[question.id] ?? [];
    const text = (formTexts[question.id] ?? '').trim();
    const parts = [...selected];
    if (text) {
      parts.push(text);
    }

    if (parts.length === 0) {
      continue;
    }
    answers[question.id] = parts.length === 1 ? parts[0] : parts;
  }

  return Object.keys(answers).length > 0 ? answers : null;
}
