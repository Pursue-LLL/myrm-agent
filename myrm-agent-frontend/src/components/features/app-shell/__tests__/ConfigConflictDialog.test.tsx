/**
 * The question shown when another device changed the same setting.
 *
 * Real scenario: the user sees which setting, which device and both versions, and must pick a side; the sync is
 * waiting for that answer, so nothing but the two buttons may close the dialog.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ConfigConflictDialog, { type ConfigConflictData } from '../ConfigConflictDialog';

vi.mock('@/lib/diff/TextDiffViewer', () => ({
  TextDiffViewer: ({ oldValue, newValue }: { oldValue: string; newValue: string }) => (
    <div data-testid="diff">{`${oldValue}=>${newValue}`}</div>
  ),
}));

const translate = (key: string, values?: Record<string, string>): string =>
  values ? `${key}(${Object.values(values).join(',')})` : key;

const conflict: ConfigConflictData = {
  configKey: 'voice',
  configLabel: 'Voice Settings',
  serverVersion: 'v2',
  localVersion: 'v1',
  deviceId: 'laptop',
  localValue: { speed: 1 },
  serverValue: { speed: 2 },
};

const onKeepLocal = vi.fn<() => void>();
const onUseServer = vi.fn<() => void>();

const renderDialog = (data: ConfigConflictData | null = conflict) =>
  render(
    <ConfigConflictDialog open conflict={data} onKeepLocal={onKeepLocal} onUseServer={onUseServer} t={translate} />,
  );

beforeEach(() => {
  vi.resetAllMocks();
});

describe('ConfigConflictDialog', () => {
  it('names the setting and shows both versions, the other device and what differs', () => {
    renderDialog();

    const dialog = screen.getByRole('alertdialog');
    expect(dialog).toHaveTextContent('description(Voice Settings)');
    expect(dialog).toHaveTextContent('serverVersion:v2');
    expect(dialog).toHaveTextContent('localVersion:v1');
    expect(dialog).toHaveTextContent('device:laptop');
    expect(screen.getByTestId('diff')).toHaveTextContent('{ "speed": 2 }=>{ "speed": 1 }');
  });

  it('leaves out the device when it is unknown, and the diff when either side has no value', () => {
    renderDialog({ ...conflict, deviceId: undefined, serverValue: undefined });

    expect(screen.getByRole('alertdialog')).not.toHaveTextContent('device:');
    expect(screen.queryByTestId('diff')).toBeNull();
  });

  it('hands the choice to the matching handler', () => {
    renderDialog();

    fireEvent.click(screen.getByRole('button', { name: 'useServer' }));
    expect(onUseServer).toHaveBeenCalledOnce();
    expect(onKeepLocal).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'keepLocal' }));
    expect(onKeepLocal).toHaveBeenCalledOnce();
  });

  it('cannot be dismissed without a choice', () => {
    renderDialog();

    fireEvent.keyDown(document, { key: 'Escape' });
    fireEvent.pointerDown(document.body);
    fireEvent.click(document.body);

    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(onKeepLocal).not.toHaveBeenCalled();
    expect(onUseServer).not.toHaveBeenCalled();
  });
});
