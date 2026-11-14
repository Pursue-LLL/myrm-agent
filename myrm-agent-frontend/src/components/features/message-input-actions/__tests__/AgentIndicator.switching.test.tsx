/**
 * @vitest-environment jsdom
 *
 * [INPUT]
 * - ../AgentIndicator (POS: 输入区的智能体指示器与快切下拉)
 *
 * [OUTPUT]
 * Vitest: 切换预设与自定义智能体（详情可读与不可读两条路径）、较早发起却较晚完成的切换不得覆盖较新的选择、
 * 菜单随选择自动关闭、底部的配置面板与管理入口、加载中与非 agent 模式的表现。
 *
 * [POS]
 * 真实的 Radix 下拉与提示；状态总线、画廊、路由与提示由 agentIndicatorKit 替身，文案是真实英文。
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  customAgent,
  deferred,
  fullAgent,
  kit,
  openMenu,
  preset,
  renderIndicator,
  resetIndicatorKit,
} from './agentIndicatorKit';
import type { AgentConfig } from '@/store/chat/types/sessionConfig';

const menuItem = (name: string) => screen.getByRole('menuitem', { name });
const appliedConfig = (): AgentConfig => {
  expect(kit.chat.setAgentConfig).toHaveBeenCalledOnce();
  return kit.chat.setAgentConfig.mock.calls[0][0];
};

describe('AgentIndicator switching', () => {
  beforeEach(resetIndicatorKit);
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('a built-in preset', () => {
    beforeEach(() => {
      kit.gallery.presets = [preset()];
    });

    it('applies the saved agent behind the preset, keeping the preset identity', async () => {
      kit.fetchAgent.mockResolvedValue(
        fullAgent({
          id: 'coder',
          name: 'Coder',
          skill_ids: ['code_edit', 'web'],
          mcp_ids: ['git'],
          system_prompt: 'Saved.',
        }),
      );
      renderIndicator();
      openMenu();

      fireEvent.click(menuItem('Coder'));

      await waitFor(() => expect(kit.chat.setAgentConfig).toHaveBeenCalledOnce());
      expect(kit.fetchAgent).toHaveBeenCalledExactlyOnceWith('coder');
      expect(appliedConfig()).toMatchObject({
        agentId: 'coder',
        selectedSkillIds: ['code_edit', 'web'],
        selectedMcpNames: ['git'],
        systemPrompt: 'Saved.',
        presetId: 'coder',
        presetName: 'Coder',
        presetIcon: 'Code',
      });
      expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'Agent switched', description: 'Coder' });
    });

    it.each([
      {
        name: 'with its own skills and prompt',
        overrides: {},
        skills: ['code_edit'],
        prompt: 'You are an expert coder.',
      },
      { name: 'without any', overrides: { skillIds: undefined, systemPrompt: undefined }, skills: [], prompt: '' },
    ])(
      'falls back to the preset itself when its details cannot be loaded, $name',
      async ({ overrides, skills, prompt }) => {
        kit.gallery.presets = [preset(overrides)];
        renderIndicator();
        openMenu();

        fireEvent.click(menuItem('Coder'));

        await waitFor(() => expect(kit.chat.setAgentConfig).toHaveBeenCalledOnce());
        expect(appliedConfig()).toEqual({
          agentId: 'coder',
          selectedSkillIds: skills,
          skillConfigs: {},
          selectedMcpNames: [],
          systemPrompt: prompt,
          useGlobalInstruction: true,
          autoRestoreDomains: [],
          presetId: 'coder',
          presetName: 'Coder',
          presetIcon: 'Code',
        });
        expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'Agent switched', description: 'Coder' });
      },
    );

    it('closes the menu once a preset is chosen', async () => {
      renderIndicator();
      openMenu();

      fireEvent.click(menuItem('Coder'));

      await waitFor(() => expect(screen.queryByRole('menu')).toBeNull());
    });
  });

  describe('a custom agent', () => {
    beforeEach(() => {
      kit.gallery.customAgents = [customAgent({ avatar_url: 'gradient:2', skill_ids: ['calc'], mcp_ids: ['sheets'] })];
    });

    it('applies the saved agent as it is stored', async () => {
      kit.fetchAgent.mockResolvedValue(
        fullAgent({ avatar_url: 'gradient:2', skill_ids: ['calc', 'chart'], system_prompt: 'You advise on money.' }),
      );
      renderIndicator();
      openMenu();

      fireEvent.click(menuItem('Finance'));

      await waitFor(() => expect(kit.chat.setAgentConfig).toHaveBeenCalledOnce());
      expect(kit.fetchAgent).toHaveBeenCalledExactlyOnceWith('finance');
      expect(appliedConfig()).toMatchObject({
        agentId: 'finance',
        agentName: 'Finance',
        avatarUrl: 'gradient:2',
        selectedSkillIds: ['calc', 'chart'],
        systemPrompt: 'You advise on money.',
      });
      expect(appliedConfig()).not.toHaveProperty('presetId');
      expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'Agent switched', description: 'Finance' });
    });

    it('falls back to what the list knows when the details cannot be loaded', async () => {
      renderIndicator();
      openMenu();

      fireEvent.click(menuItem('Finance'));

      await waitFor(() => expect(kit.chat.setAgentConfig).toHaveBeenCalledOnce());
      expect(appliedConfig()).toEqual({
        agentId: 'finance',
        agentName: 'Finance',
        avatarUrl: 'gradient:2',
        selectedSkillIds: ['calc'],
        selectedMcpNames: ['sheets'],
        systemPrompt: '',
        useGlobalInstruction: true,
        skillConfigs: {},
        autoRestoreDomains: [],
      });
    });

    it('treats a list entry without skills or connections as having none', async () => {
      kit.gallery.customAgents = [customAgent()];
      renderIndicator();
      openMenu();

      fireEvent.click(menuItem('Finance'));

      await waitFor(() => expect(kit.chat.setAgentConfig).toHaveBeenCalledOnce());
      expect(appliedConfig()).toMatchObject({ selectedSkillIds: [], selectedMcpNames: [] });
    });

    it('closes the menu once an agent is chosen', async () => {
      renderIndicator();
      openMenu();

      fireEvent.click(menuItem('Finance'));

      await waitFor(() => expect(screen.queryByRole('menu')).toBeNull());
    });
  });

  describe('choosing twice in a row', () => {
    it.each([
      { earlier: 'Coder', earlierId: 'coder', later: 'Finance', laterId: 'finance' },
      { earlier: 'Finance', earlierId: 'finance', later: 'Coder', laterId: 'coder' },
    ])(
      'keeps $later when $earlier, chosen first, finishes loading after it',
      async ({ earlier, earlierId, later, laterId }) => {
        kit.gallery.presets = [preset()];
        kit.gallery.customAgents = [customAgent()];
        const slow = deferred<ReturnType<typeof fullAgent> | null>();
        kit.fetchAgent.mockImplementation((agentId) => (agentId === earlierId ? slow.promise : Promise.resolve(null)));
        renderIndicator();

        openMenu();
        fireEvent.click(menuItem(earlier));
        await waitFor(() => expect(screen.queryByRole('menu')).toBeNull());
        openMenu();
        fireEvent.click(menuItem(later));
        await waitFor(() => expect(kit.chat.setAgentConfig).toHaveBeenCalledOnce());

        slow.resolve(fullAgent({ id: earlierId, name: earlier }));
        await Promise.resolve();
        await Promise.resolve();

        expect(kit.chat.setAgentConfig).toHaveBeenCalledOnce();
        expect(appliedConfig().agentId).toBe(laterId);
        expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'Agent switched', description: later });
      },
    );
  });

  describe('the footer entries', () => {
    it('opens the detailed configuration, and closes the menu', async () => {
      renderIndicator();
      openMenu();

      fireEvent.click(menuItem('Detailed Configuration...'));

      expect(kit.chat.toggleConfigPanel).toHaveBeenCalledOnce();
      await waitFor(() => expect(screen.queryByRole('menu')).toBeNull());
    });

    it('goes to the agent list in settings, and closes the menu', async () => {
      renderIndicator();
      openMenu();

      fireEvent.click(menuItem('Manage Agents...'));

      expect(kit.router.push).toHaveBeenCalledExactlyOnceWith('/settings/agents');
      await waitFor(() => expect(screen.queryByRole('menu')).toBeNull());
    });
  });

  describe('the menu contents', () => {
    it('lists presets and custom agents under their own headings', () => {
      kit.gallery.presets = [preset(), preset({ id: 'searcher', name: 'Searcher', icon: 'Search' })];
      kit.gallery.customAgents = [customAgent()];
      renderIndicator();

      const menu = within(openMenu());

      expect(menu.getByText('Built-in Presets')).toBeInTheDocument();
      expect(menu.getByText('My Agents')).toBeInTheDocument();
      expect(menu.getAllByRole('menuitem').map((item) => item.textContent)).toEqual([
        'Coder',
        'Searcher',
        'Finance',
        'Detailed Configuration...',
        'Manage Agents...',
      ]);
    });

    it('shows only the footer entries when there are no agents to pick from', () => {
      renderIndicator();

      const menu = within(openMenu());

      expect(menu.queryByText('Built-in Presets')).toBeNull();
      expect(menu.queryByText('My Agents')).toBeNull();
      expect(menu.getAllByRole('menuitem')).toHaveLength(2);
    });

    it.each([
      { current: { agentId: 'coder' }, marked: 'Coder' },
      { current: { presetId: 'coder' }, marked: 'Coder' },
      { current: { agentId: 'finance' }, marked: 'Finance' },
    ])('marks only the current agent ($current) in the list', ({ current, marked }) => {
      kit.gallery.presets = [preset()];
      kit.gallery.customAgents = [customAgent()];
      kit.chat.agentConfig = {
        selectedSkillIds: [],
        selectedMcpNames: [],
        systemPrompt: '',
        useGlobalInstruction: true,
        ...current,
      };
      renderIndicator();
      openMenu();

      const checked = screen
        .getAllByRole('menuitem')
        .filter((item) => item.querySelector('svg.lucide-check') !== null)
        .map((item) => item.textContent);

      expect(checked).toEqual([marked]);
    });

    it('gives a preset without a known icon the bot placeholder in the list', () => {
      kit.gallery.presets = [preset({ icon: 'NoSuchIcon' })];
      renderIndicator();

      openMenu();

      expect(within(menuItem('Coder')).queryByTestId('icon-Code')).toBeNull();
      expect(menuItem('Coder').querySelector('svg')).not.toBeNull();
    });

    it('shows the icon of a preset when it has a known one', () => {
      kit.gallery.presets = [preset()];
      renderIndicator();

      openMenu();

      expect(within(menuItem('Coder')).getByTestId('icon-Code')).toBeInTheDocument();
    });
  });

  describe('when it can be used', () => {
    it('cannot be opened while a reply is being produced', () => {
      kit.chat.loading = true;
      renderIndicator();

      const trigger = screen.getByRole('button', { name: 'Switch Agent' });
      fireEvent.keyDown(trigger, { key: 'Enter' });

      expect(trigger).toBeDisabled();
      expect(screen.queryByRole('menu')).toBeNull();
    });

    it.each(['fast', 'search'])('is not shown in %s mode', (actionMode) => {
      kit.chat.actionMode = actionMode;

      const { container } = renderIndicator();

      expect(container).toBeEmptyDOMElement();
    });
  });
});
