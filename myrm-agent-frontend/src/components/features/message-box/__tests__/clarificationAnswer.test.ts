import { describe, expect, it } from 'vitest';

import { buildStructuredClarificationAnswer } from '../clarificationAnswer';
import type { ClarificationForm } from '@/store/chat/types';

const sampleForm: ClarificationForm = {
  title: 'Framework choice',
  questions: [
    {
      id: 'framework',
      prompt: 'Which AI framework?',
      options: [
        { id: 'langchain', label: 'LangChain' },
        { id: 'llamaindex', label: 'LlamaIndex' },
      ],
    },
  ],
};

describe('buildStructuredClarificationAnswer', () => {
  it('returns option ids keyed by question id (not labels)', () => {
    const answer = buildStructuredClarificationAnswer(
      sampleForm,
      { framework: ['langchain'] },
      {},
    );
    expect(answer).toEqual({ framework: 'langchain' });
  });

  it('supports multiple selections per question', () => {
    const answer = buildStructuredClarificationAnswer(
      {
        questions: [
          {
            id: 'scope',
            prompt: 'Pick scopes',
            allowMultiple: true,
            options: [
              { id: 'api', label: 'API' },
              { id: 'ui', label: 'UI' },
            ],
          },
        ],
      },
      { scope: ['api', 'ui'] },
      {},
    );
    expect(answer).toEqual({ scope: ['api', 'ui'] });
  });

  it('appends free text after selected option ids', () => {
    const answer = buildStructuredClarificationAnswer(
      sampleForm,
      { framework: ['langchain'] },
      { framework: 'prefer v0.3' },
    );
    expect(answer).toEqual({ framework: ['langchain', 'prefer v0.3'] });
  });

  it('returns null when no question has an answer', () => {
    expect(buildStructuredClarificationAnswer(sampleForm, {}, {})).toBeNull();
  });
});
