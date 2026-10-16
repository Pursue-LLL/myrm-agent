/**
 * [INPUT]
 * - ./types::HitlAnswerRecord / ClarificationForm (POS: the record kept on a settled card and the form it answered)
 *
 * [OUTPUT]
 * - isHitlAnswerRecord: type guard for a record arriving from the server
 * - summarizeClarificationRecord: what a settled card shows, or null to fall back to the plain answered label
 * - clarificationAnswerAsText: the user's answer as the message they would send, or '' when there is nothing to send
 *
 * [POS]
 * Store-free reading of the record a clarification card keeps after it is settled. The record is persisted data, so
 * every value is checked against the card it sits on before it is shown.
 */

import type { ClarificationForm, HitlAnswerRecord } from './types';

export interface AnswerLine {
  key: string;
  prompt?: string;
  text: string;
}

export type ClarificationOutcome =
  { kind: 'timeout' } | { kind: 'skipped' } | { kind: 'answered'; lines: AnswerLine[] };

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const isTextAnswer = (value: unknown): value is string | string[] =>
  typeof value === 'string' || (Array.isArray(value) && value.every((item) => typeof item === 'string'));

export function isHitlAnswerRecord(value: unknown): value is HitlAnswerRecord {
  return isRecord(value) && (value.by === 'user' || value.by === 'timeout') && 'value' in value;
}

const joinAnswer = (answer: string | string[]): string => (Array.isArray(answer) ? answer.join(', ') : answer).trim();

export function summarizeClarificationRecord(
  record: HitlAnswerRecord | undefined,
  form: ClarificationForm | undefined,
): ClarificationOutcome | null {
  if (!record) {
    return null;
  }
  if (record.by === 'timeout') {
    return { kind: 'timeout' };
  }
  const { value } = record;
  if (isTextAnswer(value)) {
    const text = joinAnswer(value);
    return text ? { kind: 'answered', lines: [{ key: 'answer', text }] } : { kind: 'skipped' };
  }
  if (!isRecord(value)) {
    return null;
  }
  if (Object.keys(value).length === 0) {
    return { kind: 'skipped' };
  }
  const lines = (form?.questions ?? []).flatMap((question): AnswerLine[] => {
    const answer = value[question.id];
    if (!isTextAnswer(answer)) {
      return [];
    }
    const labels = (Array.isArray(answer) ? answer : [answer]).map(
      (optionId) => question.options?.find((option) => option.id === optionId)?.label ?? optionId,
    );
    const text = joinAnswer(labels);
    return text ? [{ key: question.id, prompt: question.prompt, text }] : [];
  });
  return lines.length > 0 ? { kind: 'answered', lines } : null;
}

export function clarificationAnswerAsText(value: unknown, form: ClarificationForm | undefined): string {
  const outcome = summarizeClarificationRecord({ by: 'user', value }, form);
  if (outcome?.kind !== 'answered') {
    return '';
  }
  return outcome.lines.map((line) => (line.prompt ? `${line.prompt}: ${line.text}` : line.text)).join('\n');
}
