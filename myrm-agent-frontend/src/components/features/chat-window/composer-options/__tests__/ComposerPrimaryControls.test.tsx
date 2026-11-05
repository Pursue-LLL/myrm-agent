import { fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ComposerPrimaryControls } from '../ComposerPrimaryControls';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'zh'));

/** The props the action-mode picker last received. */
const received = vi.hoisted(() => ({ searchMode: undefined as Record<string, unknown> | undefined }));

vi.mock('@/components/features/message-input-actions/SearchModeSelector', () => ({
  default: (props: Record<string, unknown>) => {
    received.searchMode = props;
    return <span data-testid="search-mode" />;
  },
}));
vi.mock('@/components/features/message-input-actions/BaseModelSelector', () => ({
  default: () => <span data-testid="model" />,
}));
vi.mock('../../thinking-permission', () => ({
  PermissionModeTierSwitcher: ({ className }: { className?: string }) => (
    <span data-testid="permission" className={className} />
  ),
}));

function renderControls(props: Partial<ComponentProps<typeof ComposerPrimaryControls>> = {}) {
  const handlers = { onToggleOptions: vi.fn(), setActionMode: vi.fn(), onToggleEditor: vi.fn() };
  render(
    <ComposerPrimaryControls
      optionsExpanded={false}
      optionsRegionId="options-region"
      actionMode="agent"
      editorExpanded={false}
      {...handlers}
      {...props}
    />,
  );
  return { ...handlers, row: screen.getByTestId('composer-primary-controls') };
}

describe('desktop composer primary controls', () => {
  beforeEach(() => {
    received.searchMode = undefined;
  });

  it('holds exactly the five controls every message uses, in order', () => {
    const { row } = renderControls();

    expect(Array.from(row.children).map((control) => control.getAttribute('data-testid'))).toEqual([
      'composer-options-toggle',
      'search-mode',
      'model',
      'permission',
      'composer-editor-toggle',
    ]);
  });

  it('stays on one line without a scroller, and is left to the phone sheet below the sm breakpoint', () => {
    const { row } = renderControls();

    const classes = row.className.split(/\s+/);
    expect(classes).toEqual(expect.arrayContaining(['hidden', 'sm:flex', 'flex-nowrap', 'min-w-0']));
    expect(classes.filter((token) => token.includes('overflow'))).toEqual([]);
  });

  it('lets only the model name shorten, so a squeezed row never wraps another control onto two lines', () => {
    renderControls();

    for (const testId of ['composer-options-toggle', 'permission', 'composer-editor-toggle']) {
      expect(screen.getByTestId(testId).className.split(/\s+/)).toContain('shrink-0');
    }
  });

  it('wires the options toggle to the region it controls', () => {
    const { onToggleOptions } = renderControls({ optionsExpanded: true });

    const toggle = screen.getByTestId('composer-options-toggle');
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(toggle).toHaveAttribute('aria-controls', 'options-region');
    fireEvent.click(toggle);
    expect(onToggleOptions).toHaveBeenCalledTimes(1);
  });

  it('hands the action-mode picker the mode and its setter', () => {
    const { setActionMode } = renderControls({ actionMode: 'fast' });

    expect(received.searchMode).toEqual({ actionMode: 'fast', setActionMode });
  });

  it('names the editor expander after what it will do', () => {
    const { onToggleEditor } = renderControls();

    const expander = screen.getByTestId('composer-editor-toggle');
    expect(expander).toHaveAccessibleName('展开编辑器（Ctrl/⌘+Shift+Enter）');
    fireEvent.click(expander);
    expect(onToggleEditor).toHaveBeenCalledTimes(1);
  });

  it('names the editor expander after what it will do once the editor is expanded', () => {
    renderControls({ editorExpanded: true });

    expect(screen.getByTestId('composer-editor-toggle')).toHaveAccessibleName('收起编辑器（Ctrl/⌘+Shift+Enter）');
  });
});
