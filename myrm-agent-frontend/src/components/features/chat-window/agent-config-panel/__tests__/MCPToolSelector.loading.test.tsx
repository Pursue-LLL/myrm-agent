import { act, cleanup, fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { deferred } from '@/test-utils/deferred';
import type { FetchMCPToolsResult } from '@/services/llm-config';
import { destructiveTool, failedRead, kit, readOnlyTool, serverConfig, toolsRead, writableTool } from './mcpToolKit';
import { expandFilter, filterToggle, listedTools, renderSelector } from './mcpToolRender';

vi.mock('@/services/llm-config', async () => (await import('./mcpToolKit')).llmConfigMock());
vi.mock('next-intl', async () => (await import('./mcpToolKit')).nextIntlMock());

beforeEach(() => {
  kit.fetchMCPTools.mockReset();
});

afterEach(() => {
  cleanup();
});

const settle = () => act(async () => undefined);

describe('MCPToolSelector reading the tools', () => {
  it('shows progress while the tools are on their way, then lists them in the order the server gave', async () => {
    const read = deferred<FetchMCPToolsResult>();
    kit.fetchMCPTools.mockReturnValue(read.promise);
    renderSelector();

    await expandFilter();

    expect(screen.getByText('loading')).toBeInTheDocument();
    expect(screen.queryByText('noTools')).toBeNull();

    await act(async () => read.resolve(toolsRead(writableTool('write'), readOnlyTool('read'))));

    expect(screen.queryByText('loading')).toBeNull();
    expect(listedTools()).toEqual(['write', 'read']);
  });

  it('reads with the configuration the parent has when the filter is opened', async () => {
    kit.fetchMCPTools.mockResolvedValue(toolsRead(readOnlyTool('read')));
    const selector = renderSelector();
    selector.update({ mcpConfig: serverConfig('moved') });

    await expandFilter();

    expect(kit.fetchMCPTools).toHaveBeenCalledExactlyOnceWith(serverConfig('moved'));
  });

  it('says so when the server offers no tools', async () => {
    kit.fetchMCPTools.mockResolvedValue(toolsRead());
    renderSelector();

    await expandFilter();

    expect(screen.getByText('noTools')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /retry/ })).toBeNull();
    expect(filterToggle()).toHaveTextContent(/^toolFilter$/);
  });

  it('offers a retry when the tools cannot be read, and a retry that works replaces the message', async () => {
    kit.fetchMCPTools.mockResolvedValueOnce(failedRead).mockResolvedValueOnce(toolsRead(readOnlyTool('read')));
    renderSelector();

    await expandFilter();

    expect(screen.getByText('loadFailed')).toBeInTheDocument();
    expect(screen.queryByText('noTools')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /retry/ }));
    await settle();

    expect(kit.fetchMCPTools).toHaveBeenCalledTimes(2);
    expect(screen.queryByText('loadFailed')).toBeNull();
    expect(listedTools()).toEqual(['read']);
  });

  it('shows progress again while a retry is on its way', async () => {
    const retry = deferred<FetchMCPToolsResult>();
    kit.fetchMCPTools.mockResolvedValueOnce(failedRead).mockReturnValueOnce(retry.promise);
    renderSelector();
    await expandFilter();

    fireEvent.click(screen.getByRole('button', { name: /retry/ }));

    expect(screen.getByText('loading')).toBeInTheDocument();
    expect(screen.queryByText('loadFailed')).toBeNull();
  });

  it('forgets the tools, closes and reads again when the server is switched off and on', async () => {
    kit.fetchMCPTools.mockResolvedValue(toolsRead(readOnlyTool('read')));
    const selector = renderSelector();
    await expandFilter();

    selector.update({ isServerEnabled: false });
    expect(screen.queryByRole('button', { name: /^toolFilter/ })).toBeNull();
    selector.update({ isServerEnabled: true });

    expect(filterToggle()).toHaveAttribute('aria-expanded', 'false');
    await expandFilter();
    expect(kit.fetchMCPTools).toHaveBeenCalledTimes(2);
    expect(listedTools()).toEqual(['read']);
  });
});

describe('MCPToolSelector with a parent that renders again', () => {
  it('reads once while the answer is on its way, however often the parent hands in new objects', async () => {
    const read = deferred<FetchMCPToolsResult>();
    kit.fetchMCPTools.mockReturnValue(read.promise);
    const selector = renderSelector();
    await expandFilter();

    selector.update({ mcpConfig: serverConfig(), onSelectionChange: vi.fn() });
    selector.update({ mcpConfig: serverConfig(), onSelectionChange: vi.fn() });
    await act(async () => read.resolve(toolsRead(readOnlyTool('read'))));

    expect(kit.fetchMCPTools).toHaveBeenCalledTimes(1);
    expect(listedTools()).toEqual(['read']);
  });

  it('does not try a failed read again by itself', async () => {
    kit.fetchMCPTools.mockResolvedValue(failedRead);
    const selector = renderSelector();
    await expandFilter();

    selector.update({ mcpConfig: serverConfig(), onSelectionChange: vi.fn() });
    await settle();

    expect(kit.fetchMCPTools).toHaveBeenCalledTimes(1);
    expect(screen.getByText('loadFailed')).toBeInTheDocument();
  });

  it('reads once when it is closed and opened again while the answer is on its way', async () => {
    const read = deferred<FetchMCPToolsResult>();
    kit.fetchMCPTools.mockReturnValue(read.promise);
    renderSelector();
    await expandFilter();

    fireEvent.click(filterToggle());
    fireEvent.click(filterToggle());
    await act(async () => read.resolve(toolsRead(readOnlyTool('read'))));

    expect(kit.fetchMCPTools).toHaveBeenCalledTimes(1);
    expect(listedTools()).toEqual(['read']);
  });

  it('reports to the callback the parent has now', async () => {
    const read = deferred<FetchMCPToolsResult>();
    kit.fetchMCPTools.mockReturnValue(read.promise);
    const first = vi.fn();
    const latest = vi.fn();
    const selector = renderSelector({ onSelectionChange: first });
    await expandFilter();
    selector.update({ onSelectionChange: latest });

    await act(async () => read.resolve(toolsRead(readOnlyTool('read'), destructiveTool('wipe'))));

    expect(first).not.toHaveBeenCalled();
    expect(latest).toHaveBeenCalledExactlyOnceWith('docs', ['read']);
  });
});

describe('MCPToolSelector answers that arrive too late', () => {
  it('ignores the answer when the server was switched off meanwhile', async () => {
    const read = deferred<FetchMCPToolsResult>();
    kit.fetchMCPTools.mockReturnValueOnce(read.promise).mockResolvedValue(toolsRead(readOnlyTool('fresh')));
    const selector = renderSelector();
    await expandFilter();

    selector.update({ isServerEnabled: false });
    await act(async () => read.resolve(toolsRead(readOnlyTool('stale'), destructiveTool('wipe'))));

    expect(selector.props.onSelectionChange).not.toHaveBeenCalled();

    selector.update({ isServerEnabled: true });
    await expandFilter();

    expect(kit.fetchMCPTools).toHaveBeenCalledTimes(2);
    expect(listedTools()).toEqual(['fresh']);
  });

  it('does not report anything once the selector is gone', async () => {
    const read = deferred<FetchMCPToolsResult>();
    kit.fetchMCPTools.mockReturnValue(read.promise);
    const selector = renderSelector();
    await expandFilter();

    selector.view.unmount();
    await act(async () => read.resolve(toolsRead(readOnlyTool('read'), destructiveTool('wipe'))));

    expect(selector.props.onSelectionChange).not.toHaveBeenCalled();
  });
});

describe('MCPToolSelector first read of a server with destructive tools', () => {
  it('chooses the tools that are not destructive', async () => {
    kit.fetchMCPTools.mockResolvedValue(
      toolsRead(readOnlyTool('read'), destructiveTool('wipe'), writableTool('write')),
    );
    const { props } = renderSelector();

    await expandFilter();

    expect(props.onSelectionChange).toHaveBeenCalledExactlyOnceWith('docs', ['read', 'write']);
  });

  it('chooses nothing when every tool is destructive', async () => {
    kit.fetchMCPTools.mockResolvedValue(toolsRead(destructiveTool('wipe'), destructiveTool('drop')));
    const { props } = renderSelector();

    await expandFilter();

    expect(props.onSelectionChange).toHaveBeenCalledExactlyOnceWith('docs', []);
  });

  it('leaves a server without destructive tools unchosen', async () => {
    kit.fetchMCPTools.mockResolvedValue(toolsRead(readOnlyTool('read'), writableTool('write')));
    const { props } = renderSelector();

    await expandFilter();

    expect(props.onSelectionChange).not.toHaveBeenCalled();
  });

  it('leaves a choice that was made before alone', async () => {
    kit.fetchMCPTools.mockResolvedValue(toolsRead(readOnlyTool('read'), destructiveTool('wipe')));
    const { props } = renderSelector({ selectedTools: ['read', 'wipe'] });

    await expandFilter();

    expect(props.onSelectionChange).not.toHaveBeenCalled();
  });

  it('leaves a choice that was made while the answer was on its way alone', async () => {
    const read = deferred<FetchMCPToolsResult>();
    kit.fetchMCPTools.mockReturnValue(read.promise);
    const selector = renderSelector();
    await expandFilter();
    selector.update({ selectedTools: ['read', 'wipe'] });

    await act(async () => read.resolve(toolsRead(readOnlyTool('read'), destructiveTool('wipe'))));

    expect(selector.props.onSelectionChange).not.toHaveBeenCalled();
  });

  it('chooses only once, however often the filter is opened', async () => {
    kit.fetchMCPTools.mockResolvedValue(toolsRead(readOnlyTool('read'), destructiveTool('wipe')));
    const { props } = renderSelector();
    await expandFilter();

    fireEvent.click(filterToggle());
    await expandFilter();

    expect(props.onSelectionChange).toHaveBeenCalledTimes(1);
  });

  it('chooses nothing when the tools cannot be read', async () => {
    kit.fetchMCPTools.mockResolvedValue(failedRead);
    const { props } = renderSelector();

    await expandFilter();

    expect(props.onSelectionChange).not.toHaveBeenCalled();
  });
});
