/**
 * @vitest-environment jsdom
 *
 * [INPUT]
 * - ../AgentIndicator (POS: 输入区的智能体指示器按钮)
 *
 * [OUTPUT]
 * Vitest: 按钮旁的名称（来源优先级、截断、内置智能体按语言翻译、没有名称时的默认称呼）、
 * 什么样的会话配置算「已选择智能体」、悬停提示。
 *
 * [POS]
 * 真实的 Radix 提示；状态总线、画廊、路由与提示由 agentIndicatorKit 替身，文案是真实语言包。
 * 切换与菜单见 AgentIndicator.switching.test.tsx，头像见 AgentIndicatorAvatar.test.tsx。
 */
import { fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { kit, renderIndicator, resetIndicatorKit } from './agentIndicatorKit';
import type { AgentConfig } from '@/store/chat/types/sessionConfig';

const config = (overrides: Partial<AgentConfig> = {}): AgentConfig => ({
  selectedSkillIds: [],
  selectedMcpNames: [],
  systemPrompt: '',
  useGlobalInstruction: true,
  ...overrides,
});

describe('AgentIndicator display', () => {
  beforeEach(resetIndicatorKit);
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('the name next to the avatar', () => {
    it.each([
      { source: 'a short preset name', overrides: { presetId: 'p', presetName: 'Coder' }, shown: 'Coder' },
      { source: 'a long preset name', overrides: { presetId: 'p', presetName: 'Code Expert' }, shown: 'Code ...' },
      {
        source: 'a long saved name',
        overrides: { agentId: 'finance', agentName: 'Finance Advisor' },
        shown: 'Finan...',
      },
      {
        source: 'a name cut next to an emoji',
        overrides: { agentId: 'x', agentName: 'abcd🚀xyz' },
        shown: 'abcd🚀...',
      },
      {
        source: 'a preset on top of a built-in agent',
        overrides: { agentId: 'builtin-general', presetName: 'Coder' },
        shown: 'Coder',
      },
      { source: 'no name at all', overrides: { agentId: 'x' }, shown: 'Agent' },
    ])('reads $shown for $source', ({ overrides, shown }) => {
      kit.chat.agentConfig = config(overrides);

      renderIndicator();

      expect(screen.getByText(shown)).toBeInTheDocument();
    });

    it.each([
      { locale: 'en', shown: 'Gener...' },
      { locale: 'zh', shown: '通用助手' },
    ] as const)('shows a built-in agent in $locale as $shown', ({ locale, shown }) => {
      kit.locale = locale;
      kit.chat.agentConfig = config({ agentId: 'builtin-general', agentName: 'Whatever the server called it' });

      renderIndicator();

      expect(screen.getByText(shown)).toBeInTheDocument();
    });
  });

  describe('whether an agent counts as selected', () => {
    it.each([
      { when: 'there is no configuration', current: null, selected: false },
      { when: 'the configuration is empty', current: config(), selected: false },
      { when: 'it only has an agent id', current: config({ agentId: 'a' }), selected: true },
      { when: 'it only has a preset id', current: config({ presetId: 'p' }), selected: true },
      { when: 'it only has a skill', current: config({ selectedSkillIds: ['web'] }), selected: true },
      { when: 'it only has a connection', current: config({ selectedMcpNames: ['git'] }), selected: true },
      { when: 'it only has an instruction', current: config({ systemPrompt: 'Be brief.' }), selected: true },
      { when: 'its instruction is blank', current: config({ systemPrompt: '   ' }), selected: false },
    ])('is $selected when $when', ({ current, selected }) => {
      kit.chat.agentConfig = current;

      renderIndicator();

      expect(screen.queryAllByText('Agent')).toHaveLength(selected ? 1 : 0);
    });
  });

  describe('the hint', () => {
    it('explains what the button is for when it is focused', async () => {
      renderIndicator();

      fireEvent.focus(screen.getByRole('button', { name: 'Switch Agent' }));

      const hint = await screen.findByRole('tooltip');
      expect(hint).toHaveTextContent('Configure capabilities or use saved agents');
      expect(hint).toHaveTextContent('Unleash your creativity to build powerful AI agents!');
    });
  });
});
