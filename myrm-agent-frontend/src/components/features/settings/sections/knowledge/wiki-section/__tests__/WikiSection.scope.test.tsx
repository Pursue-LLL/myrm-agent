/** @vitest-environment jsdom */
import { cleanup, fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { AgentListItem } from '@/services/agent';
import type { ImportResultResponse, ObsidianImportResultResponse } from '@/services/wikiService';
import { deferred } from '@/test-utils/deferred';
import { expectDefined, expectNonNull } from '@/test-utils/expectDefined';
import { settle } from '@/test-utils/fakeClock';
import {
  apiRequest,
  click,
  listAgents,
  maintainRun,
  metrics,
  resetKit,
  router,
  service,
  toast,
} from './wikiSectionTestKit';
import {
  agentOf,
  compileRunOf,
  fileOf,
  importResultOf,
  obsidianResultOf,
  queryResponseOf,
  snippetOf,
  statsOf,
} from './wikiSectionFixtures';
import { props, renderShell, selectedTab, statsReads } from './wikiShellBench';

vi.mock('../../WikiAgentScopeContext', async () => (await import('./wikiSectionStubs')).scopeProviderModule);

interface HintOptions {
  action: { onClick: () => void };
}

const fileInput = (selector: string): HTMLInputElement => {
  const input = document.querySelector<HTMLInputElement>(selector);
  expectNonNull(input, selector);
  return input;
};
const batchZipInput = () => fileInput('input[type="file"][accept=".zip"]');
const obsidianZipInput = () => fileInput('#wiki-obsidian-import input[type="file"]');
const picker = () => document.querySelector('[data-slot="select"]');

beforeEach(() => {
  resetKit();
  listAgents.mockResolvedValue({ items: [agentOf('a1', 'Alpha'), agentOf('a2', 'Beta')] });
});

afterEach(cleanup);

describe('WikiSection: the scope reaches every layer', () => {
  it('reads the purpose and the statistics of the agent the URL names', async () => {
    await renderShell('agentId=a1');
    const paths = apiRequest.mock.calls.map(([path]) => String(path));
    expect(paths).toContain('/wiki/purpose?agent_id=a1');
    expect(paths).toContain('/wiki/stats?agent_id=a1');
    expect(picker()?.getAttribute('data-value')).toBe('a1');
    expect(props('WikiRawSourceTree').agentScopeId).toBe('a1');
  });

  it('rereads the statistics whenever the overview is entered again', async () => {
    await renderShell('agentId=a1');
    const before = statsReads();
    await click(screen.getByRole('tab', { name: 'tabs.queue' }));
    expect(statsReads()).toBe(before);
    await click(screen.getByRole('tab', { name: 'tabs.overview' }));
    expect(statsReads()).toBe(before + 1);
  });

  it('asks questions in the scope and shows the evidence of that scope', async () => {
    service.queryWiki.mockResolvedValue(
      queryResponseOf({ source_snippets: [snippetOf({ hit_kind: 'asset', asset_filename: 'chart.png' })] }),
    );
    await renderShell('agentId=a1');
    fireEvent.change(screen.getByPlaceholderText('query.placeholder'), { target: { value: 'what is x' } });
    await click(screen.getByRole('button', { name: 'actions.query' }));
    expect(service.queryWiki).toHaveBeenCalledExactlyOnceWith('what is x', 'auto', 'a1');
    expect(metrics.attempt).toHaveBeenCalledExactlyOnceWith('settings', 'agent:a1');
    expect(document.querySelector('img')?.getAttribute('src')).toBe(
      'http://api.test/wiki/assets/chart.png?agent_id=a1',
    );
    expect(props('SourceChunkDrawer').contextKey).toBe('agent:a1');
  });

  it('compiles the wiki of the scope and follows a paused compile to the queue', async () => {
    service.compileWiki.mockResolvedValue({
      pending: 0,
      compile_run: compileRunOf({ state: 'paused', pause_reason: 'Provider quota exhausted' }),
    });
    await renderShell('agentId=a1');
    await click(screen.getByRole('button', { name: 'actions.compile' }));
    expect(service.compileWiki).toHaveBeenCalledExactlyOnceWith('a1');
    expect(maintainRun.scope).toBe('a1');
    expect(selectedTab()).toBe('tabs.queue');
  });

  it('imports an archive into the scope, then goes on to review duplicates', async () => {
    service.importZip.mockResolvedValue(importResultOf());
    await renderShell('agentId=a1');
    const archive = fileOf('notes.zip');
    fireEvent.change(batchZipInput(), { target: { files: [archive] } });
    await settle();
    expect(service.importZip).toHaveBeenCalledExactlyOnceWith(archive, '.md,.txt,.org', true, 'a1');
    expect(selectedTab()).toBe('tabs.duplicateReview');
  });

  it('offers the knowledge graph of the scope after an Obsidian import', async () => {
    service.importObsidianZip.mockResolvedValue(obsidianResultOf());
    await renderShell('agentId=a1');
    fireEvent.change(obsidianZipInput(), { target: { files: [fileOf('vault.zip')] } });
    await settle();
    const hint = toast.message.mock.calls.find(([text]) => text === 'obsidianVault.postWorkflowHint');
    expectDefined(hint, 'the post-import hint');
    (hint[1] as HintOptions).action.onClick();
    expect(router.push).toHaveBeenCalledExactlyOnceWith('/library?tab=graph&agentId=a1');
  });
});

describe('WikiSection: what is still loading', () => {
  it('locks the scope picker until the agents are known', async () => {
    const agents = deferred<{ items: AgentListItem[] }>();
    listAgents.mockReturnValue(agents.promise);
    await renderShell();
    expect(picker()?.getAttribute('data-disabled')).toBe('1');
    agents.resolve({ items: [agentOf('a1', 'Alpha')] });
    await settle();
    expect(picker()?.getAttribute('data-disabled')).toBe('0');
  });

  it('shows a placeholder instead of the purpose until it arrives', async () => {
    const purpose = deferred<{ purpose: string }>();
    apiRequest.mockImplementation(async (path: string) =>
      path.includes('/wiki/purpose') ? purpose.promise : statsOf(),
    );
    await renderShell();
    expect(screen.queryByPlaceholderText('purpose.placeholder')).toBeNull();
    purpose.resolve({ purpose: 'saved purpose' });
    await settle();
    expect(screen.getByPlaceholderText<HTMLTextAreaElement>('purpose.placeholder').value).toBe('saved purpose');
  });

  it('locks the batch import while an archive is being imported', async () => {
    service.importZip.mockReturnValue(deferred<ImportResultResponse>().promise);
    await renderShell();
    fireEvent.change(batchZipInput(), { target: { files: [fileOf('notes.zip')] } });
    await settle();
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'import.urls' }).disabled).toBe(true);
  });

  it('locks the Obsidian import while a vault archive is being imported', async () => {
    service.importObsidianZip.mockReturnValue(deferred<ObsidianImportResultResponse>().promise);
    await renderShell();
    fireEvent.change(obsidianZipInput(), { target: { files: [fileOf('vault.zip')] } });
    await settle();
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'import.importing' }).disabled).toBe(true);
  });
});
