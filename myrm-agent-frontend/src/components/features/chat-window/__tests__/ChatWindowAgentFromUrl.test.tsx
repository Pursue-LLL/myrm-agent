/**
 * @vitest-environment jsdom
 *
 * [INPUT]
 * - ../ChatWindow (POS: 聊天窗口，把 URL 里的 agent_id 应用为会话配置)
 * - ./chatWindowMocks (POS: 子组件替身与路由替身)
 *
 * [OUTPUT]
 * Vitest: agent_id / agentId 两种写法都按会话恢复的同一映射应用智能体并切到智能代理模式，随后清掉查询参数；
 * 依赖失效时按技能加载完成时的工具列表判断，提示但仍应用；加载失败时记录、提示并清掉参数（再点同一链接即重试）；
 * 用户已离开该会话不应用；同一智能体只应用一次（加载期间配置到达也一样），地址清掉参数后再次使用则重新应用。
 *
 * [POS]
 * getAgent 与 toast 为替身，窗口、聊天 / 技能 / 配置 store 为真实实现。
 */
import { StrictMode } from 'react';
import { act, render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { navigation, openChatInStore } from './chatWindowMocks';
import type { Agent } from '@/services/agent';
import type { MCPServiceConfig } from '@/store/config/types';
import { buildAgentConfig } from '@/lib/utils/agent-config';
import { deferred } from '@/test-utils/deferred';
import { useSkillStore } from '@/store/skill';
import type { Skill } from '@/store/skill/types';
import useChatStore from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';
import ChatWindow from '../ChatWindow';

const mocks = vi.hoisted(() => ({
  getAgent: vi.fn<(agentId: string) => Promise<Agent>>(),
  toast: vi.fn<(options: { title: string; description?: string; variant: string }) => void>(),
}));

vi.mock('@/services/agent', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/agent')>()),
  getAgent: mocks.getAgent,
}));
vi.mock('@/hooks/shared/useToast', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/hooks/shared/useToast')>()),
  toast: mocks.toast,
}));

const SKILL_AUTHOR: Agent = {
  id: 'agent-skill-author',
  user_id: 'user-1',
  name: 'Skill Author',
  description: 'Writes reusable skills',
  system_prompt: 'You author skills.',
  skill_ids: [],
  mcp_ids: [],
  enabled_builtin_tools: ['skill_manage', 'web_search'],
  model_selection: { providerId: 'openai', model: 'gpt-4o' },
  engine_params: { temperature: 0.2 },
  created_at: '2024-01-01',
  updated_at: '2024-01-01',
};

const DOCS_SERVICE: MCPServiceConfig = { name: 'docs', type: 'sse', description: '', enabled: true };
const skill = (id: string) => ({ id, name: id }) as unknown as Skill;

/** Lets the agent fetch, the skill loads and the effects that follow them finish, so "nothing happened" is real. */
async function settle(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
}

describe('ChatWindow agent URL entry', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigation.searchParams = new URLSearchParams({ agentId: SKILL_AUTHOR.id });
    mocks.getAgent.mockResolvedValue(SKILL_AUTHOR);
    useSkillStore.setState({
      fetchMarketSkills: vi.fn().mockResolvedValue(undefined),
      fetchLocalSkills: vi.fn().mockResolvedValue(undefined),
      marketSkills: [],
      localSkills: [],
    });
    useConfigStore.setState({ mcpConfigs: [] });
    openChatInStore('session-1', { actionMode: 'fast' });
  });

  it.each(['agent_id', 'agentId'])(
    'applies the agent named by ?%s= with the same mapping as session restore, in agent mode',
    async (param) => {
      navigation.searchParams = new URLSearchParams({ [param]: SKILL_AUTHOR.id });
      render(<ChatWindow id="session-1" />);

      await waitFor(() => {
        expect(useChatStore.getState().agentConfig?.agentId).toBe(SKILL_AUTHOR.id);
      });

      const applied = useChatStore.getState().agentConfig;
      expect(applied?.enabledBuiltinTools).toEqual(['skill_manage', 'web_search']);
      expect(applied?.modelSelection).toEqual({ providerId: 'openai', model: 'gpt-4o' });
      expect(applied?.engineParams).toEqual({ temperature: 0.2 });
      expect(applied).toMatchObject(buildAgentConfig(SKILL_AUTHOR));
      expect(useChatStore.getState().actionMode).toBe('agent');
      expect(navigation.replace).toHaveBeenCalledExactlyOnceWith('/session-1', { scroll: false });
      expect(mocks.getAgent).toHaveBeenCalledExactlyOnceWith(SKILL_AUTHOR.id);
    },
  );

  it('refreshes the skill lists before judging whether the agent can run', async () => {
    const { fetchMarketSkills, fetchLocalSkills } = useSkillStore.getState();
    render(<ChatWindow id="session-1" />);

    await waitFor(() => expect(useChatStore.getState().agentConfig?.agentId).toBe(SKILL_AUTHOR.id));

    expect(fetchMarketSkills).toHaveBeenCalledExactlyOnceWith(true);
    expect(fetchLocalSkills).toHaveBeenCalledOnce();
  });

  it('goes back to the home route, not a chat route, when it was opened without a chat id', async () => {
    openChatInStore('c-held-for-home');
    render(<ChatWindow />);

    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith('/', { scroll: false }));
    expect(useChatStore.getState().agentConfig?.agentId).toBe(SKILL_AUTHOR.id);
  });

  it('applies each agent once even when what the effect depends on changes afterwards', async () => {
    render(<ChatWindow id="session-1" />);
    await waitFor(() => expect(useChatStore.getState().agentConfig?.agentId).toBe(SKILL_AUTHOR.id));

    act(() => useConfigStore.setState({ mcpConfigs: [] }));
    await settle();

    expect(mocks.getAgent).toHaveBeenCalledOnce();
    expect(navigation.replace).toHaveBeenCalledOnce();
  });

  it('applies the agent once when the saved configuration arrives while it is still loading', async () => {
    const pending = deferred<Agent>();
    mocks.getAgent.mockReturnValue(pending.promise);
    render(<ChatWindow id="session-1" />);

    act(() => useConfigStore.setState({ mcpConfigs: [] }));
    await act(async () => {
      pending.resolve(SKILL_AUTHOR);
    });
    await settle();

    expect(mocks.getAgent).toHaveBeenCalledOnce();
    expect(navigation.replace).toHaveBeenCalledOnce();
    expect(useChatStore.getState().agentConfig?.agentId).toBe(SKILL_AUTHOR.id);
  });

  it('applies the agent once even when React replays the effects', async () => {
    render(
      <StrictMode>
        <ChatWindow id="session-1" />
      </StrictMode>,
    );
    await waitFor(() => expect(useChatStore.getState().agentConfig?.agentId).toBe(SKILL_AUTHOR.id));
    await settle();

    expect(mocks.getAgent).toHaveBeenCalledOnce();
    expect(navigation.replace).toHaveBeenCalledOnce();
  });

  it('applies the same agent again when its link is used after the address was cleaned', async () => {
    const view = render(<ChatWindow id="session-1" />);
    await waitFor(() => expect(useChatStore.getState().agentConfig?.agentId).toBe(SKILL_AUTHOR.id));

    // The router dropped the parameter; the user then changed the setup and followed the expert link again.
    navigation.searchParams = new URLSearchParams();
    view.rerender(<ChatWindow id="session-1" />);
    act(() => useChatStore.setState({ agentConfig: null, actionMode: 'fast' }));
    navigation.searchParams = new URLSearchParams({ agentId: SKILL_AUTHOR.id });
    view.rerender(<ChatWindow id="session-1" />);

    await waitFor(() => expect(useChatStore.getState().agentConfig?.agentId).toBe(SKILL_AUTHOR.id));
    expect(mocks.getAgent).toHaveBeenCalledTimes(2);
    expect(useChatStore.getState().actionMode).toBe('agent');
  });

  describe('dependencies the agent needs', () => {
    it('warns about missing skills and tools but still applies the agent', async () => {
      mocks.getAgent.mockResolvedValue({ ...SKILL_AUTHOR, skill_ids: ['gone-skill'], mcp_ids: ['gone-mcp'] });
      render(<ChatWindow id="session-1" />);

      await waitFor(() => expect(useChatStore.getState().agentConfig?.agentId).toBe(SKILL_AUTHOR.id));

      expect(mocks.toast).toHaveBeenCalledExactlyOnceWith({
        title: 'validation.dependencyInvalid',
        description: 'validation.missingSkills、validation.missingMcps。validation.pleaseEdit',
        variant: 'destructive',
      });
    });

    it('counts the skills of both lists, the market and the local one', async () => {
      mocks.getAgent.mockResolvedValue({ ...SKILL_AUTHOR, skill_ids: ['market-skill', 'local-skill'] });
      useSkillStore.setState({ marketSkills: [skill('market-skill')], localSkills: [skill('local-skill')] });
      render(<ChatWindow id="session-1" />);

      await waitFor(() => expect(useChatStore.getState().agentConfig?.agentId).toBe(SKILL_AUTHOR.id));

      expect(mocks.toast).not.toHaveBeenCalled();
    });

    it('judges the agent against the tools that exist once its skills are loaded', async () => {
      mocks.getAgent.mockResolvedValue({ ...SKILL_AUTHOR, mcp_ids: [DOCS_SERVICE.name] });
      const skillsLoaded = deferred<void>();
      const fetchLocalSkills = vi.fn(() => skillsLoaded.promise);
      useSkillStore.setState({ fetchLocalSkills });
      render(<ChatWindow id="session-1" />);
      await waitFor(() => expect(fetchLocalSkills).toHaveBeenCalled());

      // The saved tool list is read while the skills are still loading.
      act(() => useConfigStore.setState({ mcpConfigs: [DOCS_SERVICE] }));
      await act(async () => {
        skillsLoaded.resolve();
      });
      await waitFor(() => expect(useChatStore.getState().agentConfig?.agentId).toBe(SKILL_AUTHOR.id));

      expect(mocks.toast).not.toHaveBeenCalled();
    });

    it('stays quiet when every skill and tool still exists', async () => {
      render(<ChatWindow id="session-1" />);

      await waitFor(() => expect(useChatStore.getState().agentConfig?.agentId).toBe(SKILL_AUTHOR.id));

      expect(mocks.toast).not.toHaveBeenCalled();
    });
  });

  describe('when it cannot be applied', () => {
    it('logs and announces the failure, cleans the address and leaves the chat and its mode as they were', async () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
      const failure = new Error('agent service down');
      mocks.getAgent.mockRejectedValue(failure);
      render(<ChatWindow id="session-1" />);

      await waitFor(() => expect(warn).toHaveBeenCalledWith(expect.any(String), failure));

      expect(mocks.toast).toHaveBeenCalledExactlyOnceWith({ title: 'loadAgentFailed', variant: 'destructive' });
      expect(useChatStore.getState().agentConfig).toBeNull();
      expect(useChatStore.getState().actionMode).toBe('fast');
      expect(navigation.replace).toHaveBeenCalledExactlyOnceWith('/session-1', { scroll: false });
      warn.mockRestore();
    });

    it('tries again when the link is followed again after a failure', async () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
      mocks.getAgent.mockRejectedValueOnce(new Error('agent service down')).mockResolvedValue(SKILL_AUTHOR);
      const view = render(<ChatWindow id="session-1" />);
      await waitFor(() => expect(mocks.toast).toHaveBeenCalledOnce());

      navigation.searchParams = new URLSearchParams();
      view.rerender(<ChatWindow id="session-1" />);
      navigation.searchParams = new URLSearchParams({ agentId: SKILL_AUTHOR.id });
      view.rerender(<ChatWindow id="session-1" />);

      await waitFor(() => expect(useChatStore.getState().agentConfig?.agentId).toBe(SKILL_AUTHOR.id));
      expect(mocks.getAgent).toHaveBeenCalledTimes(2);
      warn.mockRestore();
    });

    it('does not apply it when the user opens another chat while the skill lists are refreshing', async () => {
      const skillsLoaded = deferred<void>();
      const fetchLocalSkills = vi.fn(() => skillsLoaded.promise);
      useSkillStore.setState({ fetchLocalSkills });
      render(<ChatWindow id="session-1" />);
      await waitFor(() => expect(fetchLocalSkills).toHaveBeenCalled());

      act(() => useChatStore.setState({ chatId: 'session-2' }));
      await act(async () => {
        skillsLoaded.resolve();
      });
      await settle();

      expect(useChatStore.getState().agentConfig).toBeNull();
      expect(useChatStore.getState().actionMode).toBe('fast');
      expect(mocks.toast).not.toHaveBeenCalled();
      expect(navigation.replace).not.toHaveBeenCalled();
    });

    it('does not apply it to a chat the user has already left', async () => {
      const pending = deferred<Agent>();
      mocks.getAgent.mockReturnValue(pending.promise);
      render(<ChatWindow id="session-1" />);

      act(() => useChatStore.setState({ chatId: 'session-2' }));
      await act(async () => {
        pending.resolve(SKILL_AUTHOR);
      });
      await settle();

      expect(useChatStore.getState().agentConfig).toBeNull();
      expect(useChatStore.getState().actionMode).toBe('fast');
      expect(navigation.replace).not.toHaveBeenCalled();
    });
  });
});
