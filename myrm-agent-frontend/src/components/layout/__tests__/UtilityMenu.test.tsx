/** @vitest-environment jsdom */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { UtilityMenu } from '../UtilityMenu';
import { useWorkbenchStore } from '@/store/useWorkbenchStore';

vi.mock('next-intl', () => ({
  useTranslations: (namespace?: string) => (key: string) => (namespace ? `${namespace}.${key}` : key),
}));

vi.mock('@/components/primitives/popover', () => ({
  Popover: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  PopoverContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/components/primitives/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));

describe('UtilityMenu', () => {
  beforeEach(() => {
    useWorkbenchStore.setState({ isOpen: false });
  });

  it('lists every secondary tool with its label and shortcut', () => {
    render(<UtilityMenu />);

    expect(screen.getByLabelText('nav.tools')).toBeDefined();
    for (const label of [
      'workbench.hudTrigger',
      'sessionMap.hudTrigger',
      'presentation.menuLabel',
      'toolPicker.menuLabel',
      'systemAssistant.assistantName',
    ]) {
      expect(screen.getByText(label)).toBeDefined();
    }
    // Every shortcut is read from its own namespace, so a locale can never drift from the key binding it documents.
    for (const namespace of ['workbench', 'sessionMap', 'presentation', 'toolPicker', 'systemAssistant']) {
      expect(screen.getByText(`${namespace}.shortcutHint`)).toBeDefined();
    }
  });

  it('marks the workbench entry pressed only while the docked workbench is open', () => {
    const entry = () => screen.getByText('workbench.hudTrigger').closest('button');

    const { rerender } = render(<UtilityMenu />);
    expect(entry()?.getAttribute('aria-pressed')).toBe('false');

    act(() => {
      useWorkbenchStore.setState({ isOpen: true });
    });
    rerender(<UtilityMenu />);
    expect(entry()?.getAttribute('aria-pressed')).toBe('true');

    // The other panels are modal and cover the menu while open, so they carry no pressed state.
    for (const label of [
      'sessionMap.hudTrigger',
      'presentation.menuLabel',
      'toolPicker.menuLabel',
      'systemAssistant.assistantName',
    ]) {
      expect(screen.getByText(label).closest('button')?.hasAttribute('aria-pressed')).toBe(false);
    }
  });

  it('opens the workbench through its store', () => {
    render(<UtilityMenu />);
    fireEvent.click(screen.getByText('workbench.hudTrigger'));
    expect(useWorkbenchStore.getState().isOpen).toBe(true);
  });

  it('dispatches the panel events for the remaining entries', () => {
    const events = [
      'myrm:open-session-map',
      'myrm:open-presentation',
      'myrm:open-tool-picker',
      'myrm:open-system-assistant',
    ];
    const listeners = events.map((name) => {
      const listener = vi.fn();
      window.addEventListener(name, listener);
      return { name, listener };
    });

    render(<UtilityMenu />);
    for (const [label, event] of [
      ['sessionMap.hudTrigger', 'myrm:open-session-map'],
      ['presentation.menuLabel', 'myrm:open-presentation'],
      ['toolPicker.menuLabel', 'myrm:open-tool-picker'],
      ['systemAssistant.assistantName', 'myrm:open-system-assistant'],
    ] as const) {
      fireEvent.click(screen.getByText(label));
      expect(listeners.find((entry) => entry.name === event)?.listener).toHaveBeenCalledTimes(1);
    }
  });
});
