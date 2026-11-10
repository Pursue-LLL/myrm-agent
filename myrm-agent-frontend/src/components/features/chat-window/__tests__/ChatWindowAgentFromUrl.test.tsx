/**
 * @vitest-environment jsdom
 *
 * [INPUT]
 * - ../ChatWindow (POS: 聊天窗口，把 URL 里的 agent_id 应用为会话配置)
 * - ./chatWindowMocks (POS: 子组件替身与路由替身)
 *
 * [OUTPUT]
 * Vitest: agent_id / agentId 两种写法都按会话恢复的同一映射应用智能体并切到智能代理模式，随后清掉查询参数；
 * 依赖失效时提示但仍应用；加载失败、用户已离开该会话、同一智能体只应用一次。
 *
 * [POS]
 * getAgent 与 toast 为替身，窗口、聊天 / 技能 / 配置 store 为真实实现。
 */
import { act, render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { navigation, openChatInStore } from './chatWindowMocks';
import type { Agent } from '@/services/agent';
import { buildAgentConfig } from '@/lib/utils/agent-config';
import { deferred } from '@/test-utils/deferred';
import { useSkillStore } from '@/store/skill';
import useChatStore from '@/store/useChatStore';
import useConfigStore from '@/store/useConfigStore';
import ChatWindow from '../ChatWindow';

const mocks = vi.hoisted(() => ({
  getAgent: vi.fn<(agentId: string) => Promise<Agent>>(),
  toast: vi.fn<(options: { title: string; description: string; variant: string }) => void>(),
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

    it('stays quiet when every skill and tool still exists', async () => {
      render(<ChatWindow id="session-1" />);

      await waitFor(() => expect(useChatStore.getState().agentConfig?.agentId).toBe(SKILL_AUTHOR.id));

      expect(mocks.toast).not.toHaveBeenCalled();
    });
  });

  describe('when it cannot be applied', () => {
    it('logs the failure and leaves the chat, its mode and the address as they were', async () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
      const failure = new Error('agent service down');
      mocks.getAgent.mockRejectedValue(failure);
      render(<ChatWindow id="session-1" />);

      await waitFor(() => expect(warn).toHaveBeenCalledWith(expect.any(String), failure));

      expect(useChatStore.getState().agentConfig).toBeNull();
      expect(useChatStore.getState().actionMode).toBe('fast');
      expect(navigation.replace).not.toHaveBeenCalled();
      warn.mockRestore();
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
