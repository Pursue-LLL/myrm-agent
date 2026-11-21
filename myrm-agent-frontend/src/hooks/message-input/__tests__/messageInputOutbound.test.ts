import { beforeEach, describe, expect, it } from 'vitest';
import { parseExplicitSkillActivation } from '@/lib/utils/messageUtils';
import useChatStore from '@/store/useChatStore';
import { useScopedArtifactStore } from '@/store/useScopedArtifactStore';
import { composeOutboundUserMessage } from '../messageInputOutbound';

const SCOPE_HEADER = '[针对工件 "report.md" 的局部范围 (L1-L3) 定向编辑]';
const SCOPE_WITH_SNIPPET = `${SCOPE_HEADER}\n\`\`\`\nline one\n\`\`\`\n`;

const armSkill = (instruction: string | null = null) =>
  useChatStore.setState({ pendingExplicitSkillActivation: { skillNames: ['writer_skill'], instruction } });

const selectInArtifact = (selectedSnippet?: string) =>
  useScopedArtifactStore.getState().setTarget({
    artifactId: 'a1',
    artifactName: 'report.md',
    scopeLabel: 'L1-L3',
    selectedSnippet,
  });

describe('composeOutboundUserMessage', () => {
  beforeEach(() => {
    useChatStore.setState({ pendingExplicitSkillActivation: null });
    useScopedArtifactStore.getState().clearTarget();
  });

  it('sends the text untouched when no skill is armed and nothing is selected', () => {
    expect(composeOutboundUserMessage('hello')).toBe('hello');
  });

  it('puts the armed skill tag, with its instruction, in front of the text', () => {
    armSkill('be brief');

    expect(composeOutboundUserMessage('hello')).toBe('[use writer_skill] [instruction: be brief] hello');
  });

  it.each([
    ['with the selected snippet', 'line one', `${SCOPE_WITH_SNIPPET}\nshorten this`],
    ['without a snippet', undefined, `${SCOPE_HEADER}\nshorten this`],
  ])('puts the artifact selection %s in front of the text and consumes it', (_name, snippet, expected) => {
    selectInArtifact(snippet);

    expect(composeOutboundUserMessage('shorten this')).toBe(expected);
    expect(useScopedArtifactStore.getState().target).toBeNull();
  });

  it('keeps the skill tag at the very start when an artifact selection rides along', () => {
    armSkill();
    selectInArtifact('line one');

    const outbound = composeOutboundUserMessage('shorten this');

    // The agent reads a tag only at the start of the text, so nothing may precede it.
    expect(outbound.startsWith('[use writer_skill] ')).toBe(true);
    expect(parseExplicitSkillActivation(outbound)).toMatchObject({
      skillNames: ['writer_skill'],
      userText: `${SCOPE_WITH_SNIPPET}\nshorten this`,
    });
  });
});
