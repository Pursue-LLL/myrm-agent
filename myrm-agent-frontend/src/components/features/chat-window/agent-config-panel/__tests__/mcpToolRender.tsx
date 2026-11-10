import { act, fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import { TooltipProvider } from '@/components/primitives/tooltip';
import type { MCPServiceConfig } from '@/store/config/types';
import MCPToolSelector from '../MCPToolSelector';
import { serverConfig } from './mcpToolKit';

interface SelectorProps {
  mcpConfig: MCPServiceConfig;
  serverName: string;
  selectedTools: string[] | undefined;
  onSelectionChange: (serverName: string, tools: string[] | undefined) => void;
  isServerEnabled: boolean;
}

const defaultProps = (): SelectorProps => ({
  mcpConfig: serverConfig(),
  serverName: 'docs',
  selectedTools: undefined,
  onSelectionChange: vi.fn<SelectorProps['onSelectionChange']>(),
  isServerEnabled: true,
});

const tree = (props: SelectorProps) => (
  <TooltipProvider>
    <MCPToolSelector {...props} />
  </TooltipProvider>
);

/** Renders the selector; `update` renders it again with changed props, the way a parent that re-renders does. */
export function renderSelector(overrides: Partial<SelectorProps> = {}) {
  let props: SelectorProps = { ...defaultProps(), ...overrides };
  const view = render(tree(props));
  return {
    view,
    get props() {
      return props;
    },
    update(next: Partial<SelectorProps>) {
      props = { ...props, ...next };
      view.rerender(tree(props));
    },
  };
}

export const filterToggle = () => screen.getByRole('button', { name: /^toolFilter/ });

/** Opens the filter and lets the tool read finish. */
export async function expandFilter(): Promise<void> {
  fireEvent.click(filterToggle());
  await act(async () => undefined);
}

export const toolBox = (name: string) => screen.getByRole('checkbox', { name: new RegExp(`^${name}`) });

/** The names of the listed tools, without the risk each row also reads out to a screen reader. */
export const listedTools = () =>
  screen
    .queryAllByRole('checkbox')
    .map((box) => (box.closest('label')?.textContent ?? '').replace(/(readOnly|writable|destructive)$/, ''));
