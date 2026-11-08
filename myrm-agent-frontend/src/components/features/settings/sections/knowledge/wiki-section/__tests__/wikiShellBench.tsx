import { act, render, screen } from '@testing-library/react';

import { settle } from '@/test-utils/fakeClock';
import { apiRequest, setQuery } from './wikiSectionTestKit';
import { stubProps } from './wikiSectionStubs';
import { WikiSection } from '../../WikiSection';
import type { WikiStats } from '../types';

type Props = Record<string, unknown>;
type Callback = (...args: unknown[]) => void;

/** 在给定的 URL 查询串上渲染整个面板并等首轮加载结束；调用方须自行 mock `../../WikiAgentScopeContext`。 */
export async function renderShell(query = ''): Promise<void> {
  setQuery(query);
  render(<WikiSection />);
  await settle();
}

/** 调用某个替身收到的回调 prop，并等到由此触发的更新结束。 */
export const call = async (name: string, prop: string, ...args: unknown[]) => {
  await act(async () => (stubProps(name)[prop] as Callback)(...args));
  await settle();
};

export const props = (name: string): Props => stubProps(name);
export const selectedTab = () => screen.getByRole('tab', { selected: true }).textContent;
export const statsReads = () => apiRequest.mock.calls.filter(([path]) => String(path).includes('/wiki/stats')).length;

/** 统计接口给出 `outcome`（或失败），目的接口给出固定文本。 */
export function serveStats(outcome: WikiStats | Error) {
  apiRequest.mockImplementation(async (path: string, init?: RequestInit) => {
    if (path.includes('/wiki/purpose')) {
      return init ? {} : { purpose: 'saved purpose' };
    }
    if (outcome instanceof Error) {
      throw outcome;
    }
    return outcome;
  });
}
