/**
 * The five summary cards of the agent configuration panel.
 *
 * Real scenario: the user glances at what the agent is equipped with - skills, MCP servers, built-in tools, subagents and
 * the instruction - and opens the one to change. Each card shows how many are configured and a short preview.
 */
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { BUILTIN_TOOL_IDS } from '@/store/chat/types';

import de from '../../../../../../locales/de.json';
import en from '../../../../../../locales/en.json';
import ja from '../../../../../../locales/ja.json';
import ko from '../../../../../../locales/ko.json';
import zh from '../../../../../../locales/zh.json';
import zhTW from '../../../../../../locales/zh-TW.json';
import AgentConfigCards, { type ConfigCardType } from '../AgentConfigCards';
import { mcp, skill } from './editDialogKit';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));

const CARD_TYPES: ConfigCardType[] = ['skills', 'mcp', 'builtin_tools', 'subagents', 'instruction'];

function renderCards(overrides: Partial<ComponentProps<typeof AgentConfigCards>> = {}) {
  const onCardClick = vi.fn<(type: ConfigCardType) => void>();
  const view = render(
    <AgentConfigCards
      selectedSkills={[]}
      selectedMcps={[]}
      systemPrompt=""
      useGlobalInstruction={false}
      enabledBuiltinTools={[]}
      onCardClick={onCardClick}
      {...overrides}
    />,
  );
  return { ...view, onCardClick };
}

const card = (type: ConfigCardType) => screen.getByTestId(`agent-config-card-${type}`);

describe('AgentConfigCards empty configuration', () => {
  it('lists the five cards in order, each saying nothing is set', () => {
    renderCards();

    const cards = screen.getAllByTestId(/^agent-config-card-/);
    expect(cards.map((el) => el.dataset.testid)).toEqual(CARD_TYPES.map((type) => `agent-config-card-${type}`));
    expect(card('skills')).toHaveTextContent('Skills');
    expect(card('skills')).toHaveTextContent('No skills equipped (Pure instruction mode)');
    expect(card('mcp')).toHaveTextContent('MCP');
    expect(card('builtin_tools')).toHaveTextContent('Built-in Tools');
    expect(card('subagents')).toHaveTextContent('Subagents');
    for (const type of ['mcp', 'builtin_tools', 'subagents'] as const) {
      expect(card(type)).toHaveTextContent('Not selected');
    }
    expect(card('instruction')).toHaveTextContent('Instruction');
    expect(card('instruction')).toHaveTextContent('No instruction set');
    for (const type of CARD_TYPES) {
      expect(within(card(type)).queryByText(/^\d+$/)).toBeNull();
    }
  });

  it.each(CARD_TYPES)('reports which card was opened: %s', (type) => {
    const { onCardClick } = renderCards();

    fireEvent.click(card(type));

    expect(onCardClick).toHaveBeenCalledExactlyOnceWith(type);
  });

  it('lets the parent add classes to the grid', () => {
    const { container } = renderCards({ className: 'extra-class' });

    expect(container.firstElementChild).toHaveClass('extra-class', 'grid');
  });
});

type CardsProps = ComponentProps<typeof AgentConfigCards>;

const NAMES: [string, string, string] = ['Alpha', 'Beta', 'Gamma'];

const LISTED_CARDS: Array<{
  type: ConfigCardType;
  props: (count: number) => Partial<CardsProps>;
  shown: [string, string, string];
}> = [
  {
    type: 'skills',
    props: (count) => ({ selectedSkills: NAMES.slice(0, count).map((name) => skill(name, { name })) }),
    shown: NAMES,
  },
  { type: 'mcp', props: (count) => ({ selectedMcps: NAMES.slice(0, count).map(mcp) }), shown: NAMES },
  {
    type: 'builtin_tools',
    props: (count) => ({ enabledBuiltinTools: (['web_search', 'memory', 'wiki'] as const).slice(0, count) }),
    shown: ['Web Search', 'Memory', 'Knowledge Base'],
  },
  {
    type: 'subagents',
    props: (count) => ({
      ephemeralSubagents: Object.fromEntries(NAMES.slice(0, count).map((name) => [name, {}])),
    }),
    shown: NAMES,
  },
];

describe.each(LISTED_CARDS)('AgentConfigCards $type card', ({ type, props, shown }) => {
  it.each([
    { count: 1, preview: () => shown[0] },
    { count: 2, preview: () => `${shown[0]}, ${shown[1]}` },
    { count: 3, preview: () => `${shown[0]}, ${shown[1]}...` },
  ])('counts $count and previews at most the first two names', ({ count, preview }) => {
    renderCards(props(count));

    expect(within(card(type)).getByText(preview())).toBeInTheDocument();
    expect(within(card(type)).getByText(String(count))).toBeInTheDocument();
    expect(card(type)).not.toHaveTextContent(shown[2]);
  });
});

describe('AgentConfigCards tint and defaults', () => {
  it('tints a configured card with the theme surface rather than a fixed colour', () => {
    renderCards({ selectedSkills: [skill('a')] });

    expect(card('skills')).toHaveClass('bg-card/30');
    expect(card('skills')).not.toHaveAttribute('style');
    expect(card('mcp')).toHaveClass('bg-transparent');
    expect(card('mcp')).not.toHaveClass('bg-card/30');
  });

  it('treats a missing subagent map as none', () => {
    renderCards({ ephemeralSubagents: undefined });

    expect(card('subagents')).toHaveTextContent('Not selected');
  });
});

describe('AgentConfigCards instruction card', () => {
  it('counts one instruction and previews all of a short prompt', () => {
    renderCards({ systemPrompt: 'Be brief.' });

    expect(card('instruction')).toHaveTextContent('Be brief.');
    expect(within(card('instruction')).getByText('1')).toBeInTheDocument();
  });

  it('cuts a long prompt at thirty characters, and only a longer one', () => {
    const exactly30 = 'x'.repeat(30);
    const { unmount } = renderCards({ systemPrompt: exactly30 });
    expect(card('instruction')).toHaveTextContent(new RegExp(`^1Instruction${exactly30}$`));
    unmount();

    renderCards({ systemPrompt: `${exactly30}y` });

    expect(card('instruction')).toHaveTextContent(new RegExp(`^1Instruction${exactly30}\\.\\.\\.$`));
  });

  it.each([
    ['no prompt and the global instruction on', '', true, 'Using global instructions'],
    ['no prompt and the global instruction off', '', false, 'No instruction set'],
    ['only whitespace and the global instruction on', '  \n ', true, 'Using global instructions'],
  ])('says so when there is %s', (_what, systemPrompt, useGlobalInstruction, preview) => {
    renderCards({ systemPrompt, useGlobalInstruction });

    expect(card('instruction')).toHaveTextContent(preview);
    expect(within(card('instruction')).queryByText('1')).toBeNull();
  });
});

describe('AgentConfigCards copy', () => {
  const bundles = { en, zh, 'zh-TW': zhTW, ja, ko, de };

  it.each(Object.entries(bundles))('names every switchable built-in tool in %s', (_locale, bundle) => {
    const names = bundle.agent.configPanel.builtinToolNames as Record<string, string>;

    for (const id of BUILTIN_TOOL_IDS) {
      expect(names[id], id).toBeTruthy();
    }
  });
});
