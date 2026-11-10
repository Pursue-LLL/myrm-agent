import { cleanup, fireEvent, screen, within } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { destructiveTool, kit, readOnlyTool, serverConfig, toolsRead, writableTool } from './mcpToolKit';
import { expandFilter, filterToggle, listedTools, renderSelector, toolBox } from './mcpToolRender';

vi.mock('@/services/llm-config', async () => (await import('./mcpToolKit')).llmConfigMock());
vi.mock('next-intl', async () => (await import('./mcpToolKit')).nextIntlMock());

beforeEach(() => {
  kit.fetchMCPTools.mockReset();
});

afterEach(() => {
  cleanup();
});

describe('MCPToolSelector filter toggle', () => {
  it('renders nothing while the server is not selected', () => {
    const { view } = renderSelector({ isServerEnabled: false });

    expect(view.container).toBeEmptyDOMElement();
    expect(kit.fetchMCPTools).not.toHaveBeenCalled();
  });

  it('stays closed and reads nothing until it is opened', async () => {
    kit.fetchMCPTools.mockResolvedValue(toolsRead(readOnlyTool('read')));
    renderSelector();

    expect(filterToggle()).toHaveAttribute('aria-expanded', 'false');
    expect(kit.fetchMCPTools).not.toHaveBeenCalled();
    expect(screen.queryAllByRole('checkbox')).toEqual([]);

    await expandFilter();

    expect(filterToggle()).toHaveAttribute('aria-expanded', 'true');
    expect(kit.fetchMCPTools).toHaveBeenCalledExactlyOnceWith(serverConfig());
    expect(listedTools()).toEqual(['read']);
  });

  it('does not read the tools again when it is closed and opened again', async () => {
    kit.fetchMCPTools.mockResolvedValue(toolsRead(readOnlyTool('read')));
    renderSelector();
    await expandFilter();

    fireEvent.click(filterToggle());
    expect(screen.queryAllByRole('checkbox')).toEqual([]);
    await expandFilter();

    expect(listedTools()).toEqual(['read']);
    expect(kit.fetchMCPTools).toHaveBeenCalledTimes(1);
  });
});

describe('MCPToolSelector tool choice', () => {
  const twoTools = () => kit.fetchMCPTools.mockResolvedValue(toolsRead(readOnlyTool('read'), writableTool('write')));
  const threeTools = () =>
    kit.fetchMCPTools.mockResolvedValue(toolsRead(readOnlyTool('read'), writableTool('write'), writableTool('edit')));

  it('has every tool on while nothing was chosen yet, and counts them', async () => {
    twoTools();
    renderSelector();
    await expandFilter();

    expect(toolBox('read')).toBeChecked();
    expect(toolBox('write')).toBeChecked();
    expect(filterToggle()).toHaveTextContent(/^toolFilter2$/);
    expect(screen.queryByText(/\//)).toBeNull();
  });

  it('turning one off with nothing chosen yet chooses all the others', async () => {
    twoTools();
    const { props } = renderSelector();
    await expandFilter();

    fireEvent.click(toolBox('read'));

    expect(props.onSelectionChange).toHaveBeenCalledExactlyOnceWith('docs', ['write']);
  });

  it('turns a tool of the choice on and off', async () => {
    threeTools();
    const { props } = renderSelector({ selectedTools: ['read'] });
    await expandFilter();

    fireEvent.click(toolBox('write'));
    fireEvent.click(toolBox('read'));

    expect(props.onSelectionChange).toHaveBeenNthCalledWith(1, 'docs', ['read', 'write']);
    expect(props.onSelectionChange).toHaveBeenNthCalledWith(2, 'docs', []);
  });

  it('shows the tools of the choice as on and the rest as off', async () => {
    threeTools();
    renderSelector({ selectedTools: ['write'] });
    await expandFilter();

    expect(toolBox('read')).not.toBeChecked();
    expect(toolBox('write')).toBeChecked();
    expect(toolBox('edit')).not.toBeChecked();
  });

  it('counts the tools that are on out of those the server offers', async () => {
    threeTools();
    renderSelector({ selectedTools: ['read'] });
    await expandFilter();

    expect(filterToggle()).toHaveTextContent(/^toolFilter1\/3$/);
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
  });

  it('an empty choice leaves every tool off', async () => {
    twoTools();
    renderSelector({ selectedTools: [] });
    await expandFilter();

    expect(toolBox('read')).not.toBeChecked();
    expect(toolBox('write')).not.toBeChecked();
    expect(filterToggle()).toHaveTextContent(/^toolFilter0\/2$/);
  });

  it('a choice that covers every tool goes back to no choice', async () => {
    twoTools();
    const { props } = renderSelector({ selectedTools: ['read'] });
    await expandFilter();

    fireEvent.click(toolBox('write'));

    expect(props.onSelectionChange).toHaveBeenCalledExactlyOnceWith('docs', undefined);
  });

  it('a tool the server no longer offers neither counts nor keeps the choice from covering everything', async () => {
    twoTools();
    const { props } = renderSelector({ selectedTools: ['read', 'gone'] });
    await expandFilter();

    expect(filterToggle()).toHaveTextContent(/^toolFilter1\/2$/);
    expect(screen.getByText('1 / 2')).toBeInTheDocument();

    fireEvent.click(toolBox('write'));

    expect(props.onSelectionChange).toHaveBeenCalledExactlyOnceWith('docs', undefined);
  });

  it('select all drops the choice', async () => {
    twoTools();
    const { props } = renderSelector({ selectedTools: ['read'] });
    await expandFilter();

    fireEvent.click(screen.getByRole('button', { name: 'selectAll' }));

    expect(props.onSelectionChange).toHaveBeenCalledExactlyOnceWith('docs', undefined);
  });

  it('reports the choice under the name of its own server', async () => {
    twoTools();
    const { props } = renderSelector({ serverName: 'web', mcpConfig: serverConfig('web') });
    await expandFilter();

    fireEvent.click(toolBox('read'));

    expect(props.onSelectionChange).toHaveBeenCalledExactlyOnceWith('web', ['write']);
  });
});

describe('MCPToolSelector destructive tools', () => {
  const mixed = () =>
    kit.fetchMCPTools.mockResolvedValue(
      toolsRead(readOnlyTool('read'), destructiveTool('wipe'), destructiveTool('drop')),
    );

  it('says how many destructive tools the choice leaves off', async () => {
    mixed();
    renderSelector({ selectedTools: ['read'] });
    await expandFilter();

    expect(screen.getByText('dangerDisabled {"count":2}')).toBeInTheDocument();
  });

  it('counts only the destructive tools that are off', async () => {
    mixed();
    renderSelector({ selectedTools: ['read', 'wipe'] });
    await expandFilter();

    expect(screen.getByText('dangerDisabled {"count":1}')).toBeInTheDocument();
  });

  it('says nothing when every destructive tool is on', async () => {
    mixed();
    renderSelector({ selectedTools: ['wipe', 'drop'] });
    await expandFilter();

    expect(screen.queryByText(/dangerDisabled/)).toBeNull();
  });

  it('says nothing while nothing was chosen', async () => {
    mixed();
    renderSelector();
    await expandFilter();

    expect(screen.queryByText(/dangerDisabled/)).toBeNull();
  });
});

describe('MCPToolSelector risk', () => {
  beforeAll(() => {
    // The tooltip arrow measures itself.
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
  });

  const mixedRisk = () =>
    kit.fetchMCPTools.mockResolvedValue(
      toolsRead(
        readOnlyTool('look'),
        writableTool('edit'),
        destructiveTool('wipe'),
        readOnlyTool('put', { readOnlyHint: false }),
        readOnlyTool('peek', { idempotentHint: false }),
      ),
    );

  const riskOf = (name: string) => {
    const label = toolBox(name).closest('label') as HTMLElement;
    return within(label).getByText(/^(readOnly|writable|destructive)$/).textContent;
  };

  it('tells a tool that only reads, one that writes and one that destroys apart', async () => {
    mixedRisk();
    renderSelector();
    await expandFilter();

    expect(riskOf('look')).toBe('readOnly');
    expect(riskOf('edit')).toBe('writable');
    expect(riskOf('wipe')).toBe('destructive');
  });

  it('reads the risk out once, and leaves the icon itself to those who see it', async () => {
    mixedRisk();
    renderSelector();
    await expandFilter();

    const label = toolBox('edit').closest('label') as HTMLElement;

    expect(within(label).getAllByText('writable')).toHaveLength(1);
    expect(label.querySelector('svg[data-state]')).toHaveAttribute('aria-hidden', 'true');
  });

  it('counts a read that cannot be repeated as safe', async () => {
    mixedRisk();
    renderSelector();
    await expandFilter();

    expect(riskOf('peek')).toBe('readOnly');
  });

  it('counts a repeatable write as safe, and a destructive hint over everything else', async () => {
    kit.fetchMCPTools.mockResolvedValue(
      toolsRead(readOnlyTool('put', { readOnlyHint: false }), readOnlyTool('both', { destructiveHint: true })),
    );
    renderSelector();
    await expandFilter();

    expect(riskOf('put')).toBe('readOnly');
    expect(riskOf('both')).toBe('destructive');
  });

  const focusRiskOf = (name: string) => {
    const icon = toolBox(name).closest('label')?.querySelector('svg[data-state]');
    fireEvent.focus(icon as SVGElement);
    return screen.findByRole('tooltip');
  };

  it('explains the risk and the description of a tool on focus', async () => {
    kit.fetchMCPTools.mockResolvedValue(toolsRead(destructiveTool('wipe')));
    renderSelector();
    await expandFilter();

    expect(await focusRiskOf('wipe')).toHaveTextContent('destructivewipe description');
  });

  it('cuts the description at 120 characters', async () => {
    kit.fetchMCPTools.mockResolvedValue(toolsRead(readOnlyTool('long', { description: `${'x'.repeat(120)}TAIL` })));
    renderSelector();
    await expandFilter();

    const tip = await focusRiskOf('long');

    expect(tip.textContent).toBe(`readOnly${'x'.repeat(120)}`);
  });

  it('shows no description line for a tool without one', async () => {
    kit.fetchMCPTools.mockResolvedValue(toolsRead(readOnlyTool('quiet', { description: '' })));
    renderSelector();
    await expandFilter();

    const tip = await focusRiskOf('quiet');

    expect(tip.querySelectorAll('p')).toHaveLength(1);
  });
});
