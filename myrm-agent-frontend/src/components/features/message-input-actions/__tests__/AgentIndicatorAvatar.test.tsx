/**
 * @vitest-environment jsdom
 *
 * [INPUT]
 * - ../AgentIndicatorAvatar (POS: 指示器按钮里的智能体头像)
 *
 * [OUTPUT]
 * Vitest: 自定义头像的各种来源（内置图标、渐变、网址与上传的图片、emoji）及其失效时的降级、
 * 渐变序号越界时回到第一组、占位图块在选择前后的配色与图标、预设渐变由 id 稳定决定。
 *
 * [POS]
 * 头像地址解析是真实的；内置图标换成带标记的替身；预设图标解析与文案由 agentIndicatorKit 提供。
 */
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { kit, resetIndicatorKit } from './agentIndicatorKit';
import { AgentIndicatorAvatar } from '../AgentIndicatorAvatar';
import type { AgentConfig } from '@/store/chat/types/sessionConfig';

vi.mock('@/components/agent/agent-icons', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/components/agent/agent-icons')>()),
  AgentIcon: ({ iconId }: { iconId: string }) => <span data-testid="agent-icon">{iconId}</span>,
}));

const config = (overrides: Partial<AgentConfig> = {}): AgentConfig => ({
  selectedSkillIds: [],
  selectedMcpNames: [],
  systemPrompt: '',
  useGlobalInstruction: true,
  ...overrides,
});

const renderAvatar = (overrides: Partial<AgentConfig> | null, hasSelectedAgent = true) =>
  render(
    <AgentIndicatorAvatar
      agentConfig={overrides === null ? null : config(overrides)}
      hasSelectedAgent={hasSelectedAgent}
    />,
  );

const tile = (container: HTMLElement) => container.firstElementChild as HTMLElement;
const gradientOf = (element: HTMLElement) => /from-\S+ to-\S+/.exec(element.className)?.[0];

describe('AgentIndicatorAvatar', () => {
  beforeEach(resetIndicatorKit);
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('a custom avatar', () => {
    it('shows a built-in icon', () => {
      renderAvatar({ avatarUrl: 'icon:general' });

      expect(screen.getByTestId('agent-icon')).toHaveTextContent('general');
    });

    it('falls back to the placeholder for an icon that is not built in', () => {
      const { container } = renderAvatar({ avatarUrl: 'icon:not-built-in' });

      expect(screen.queryByTestId('agent-icon')).toBeNull();
      expect(tile(container).querySelector('svg')).not.toBeNull();
    });

    it.each([
      { url: 'gradient:0', pair: 'from-primary to-violet-500' },
      { url: 'gradient:2', pair: 'from-emerald-500 to-teal-500' },
      { url: 'gradient:5', pair: 'from-indigo-500 to-purple-500' },
      { url: 'gradient:6', pair: 'from-primary to-violet-500' },
      { url: 'gradient:99', pair: 'from-primary to-violet-500' },
      { url: 'gradient:-1', pair: 'from-primary to-violet-500' },
    ])('paints $url as $pair', ({ url, pair }) => {
      const { container } = renderAvatar({ avatarUrl: url });

      expect(gradientOf(tile(container))).toBe(pair);
    });

    it('falls back to the placeholder for a gradient index that is not a number', () => {
      const { container } = renderAvatar({ avatarUrl: 'gradient:abc' }, false);

      expect(tile(container)).toHaveClass('bg-muted-foreground/20');
    });

    it('shows a picture from a web address, described by the agent name', () => {
      renderAvatar({ avatarUrl: 'https://cdn.example.com/a.png', agentName: 'Finance' });

      const picture = screen.getByRole('img', { name: 'Finance' });
      expect(picture).toHaveAttribute('src', 'https://cdn.example.com/a.png');
    });

    it('serves an uploaded picture through the files of the agent that owns it', () => {
      renderAvatar({ avatarUrl: 'home://avatar.png', agentId: 'finance', agentName: 'Finance' });

      expect(screen.getByRole('img', { name: 'Finance' })).toHaveAttribute(
        'src',
        '/api/v1/user-agents/finance/files/avatar.png',
      );
    });

    it('has no uploaded picture to show without the agent that owns it', () => {
      renderAvatar({ avatarUrl: 'home://avatar.png' });

      expect(screen.queryByRole('img')).toBeNull();
    });

    it.each([
      { locale: 'en', label: 'Agent' },
      { locale: 'zh', label: '智能体' },
    ] as const)('describes a picture of an unnamed agent as "$label" in $locale', ({ locale, label }) => {
      kit.locale = locale;

      renderAvatar({ avatarUrl: 'https://cdn.example.com/a.png' });

      expect(screen.getByRole('img', { name: label })).toBeInTheDocument();
    });

    it('shows an emoji', () => {
      renderAvatar({ avatarUrl: 'emoji:🚀' });

      expect(screen.getByText('🚀')).toBeInTheDocument();
    });
  });

  describe('the placeholder', () => {
    it('shows the icon of the preset when it is a known one', () => {
      renderAvatar({ presetId: 'coder', presetIcon: 'Code' });

      expect(screen.getByTestId('icon-Code')).toBeInTheDocument();
    });

    it.each([
      { case: 'the preset icon is not known', overrides: { presetId: 'coder', presetIcon: 'NoSuchIcon' } },
      { case: 'there is no preset', overrides: {} },
      { case: 'there is no configuration', overrides: null },
    ])('shows the bot when $case', ({ overrides }) => {
      const { container } = renderAvatar(overrides);

      expect(screen.queryByTestId('icon-Code')).toBeNull();
      expect(tile(container).querySelector('svg')).not.toBeNull();
    });

    it('is colored with a white icon once an agent is selected', () => {
      const { container } = renderAvatar({ presetId: 'coder', presetIcon: 'Code' });

      expect(gradientOf(tile(container))).toBeDefined();
      expect(screen.getByTestId('icon-Code')).toHaveClass('text-white');
    });

    it('is gray with a gray icon while no agent is selected', () => {
      const { container } = renderAvatar({ presetId: 'coder', presetIcon: 'Code' }, false);

      expect(tile(container)).toHaveClass('bg-muted-foreground/20');
      expect(gradientOf(tile(container))).toBeUndefined();
      expect(screen.getByTestId('icon-Code')).toHaveClass('text-muted-foreground');
    });

    it('takes the first gradient when there is no preset to tell by', () => {
      const { container } = renderAvatar({ agentId: 'finance' });

      expect(gradientOf(tile(container))).toBe('from-primary to-violet-500');
    });

    it('colors a preset the same way every time, and different presets differently', () => {
      const ids = ['coder', 'searcher', 'writer', 'analyst', 'builtin-general', 'builtin-cli_visual'];
      const pairs = ids.map((presetId) => {
        const { container, unmount } = renderAvatar({ presetId });
        const pair = gradientOf(tile(container));
        unmount();
        return pair;
      });

      const again = renderAvatar({ presetId: ids[0] });

      expect(gradientOf(tile(again.container))).toBe(pairs[0]);
      expect(new Set(pairs).size).toBeGreaterThan(1);
    });
  });
});
