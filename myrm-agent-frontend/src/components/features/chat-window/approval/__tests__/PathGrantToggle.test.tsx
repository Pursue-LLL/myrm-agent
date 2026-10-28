import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import PathGrantToggle from '../PathGrantToggle';

const messages: Record<string, string> = {
  grantDirectory: 'Also grant folder access',
  grantDirectoryDesc: 'Allow the agent to access the folders listed below',
  grantDirectoryReadOnly: 'Read only',
  grantDirectoryReadWrite: 'Read and write',
};
const stableT = (key: string) => messages[key] ?? key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const directories = [
  { path: '/Users/me/Downloads', writable: false },
  { path: '/Users/me/reports', writable: true },
];

describe('PathGrantToggle', () => {
  it('lists every folder with the access it would get', () => {
    render(<PathGrantToggle directories={directories} checked={false} onCheckedChange={vi.fn()} />);

    expect(screen.getByText('/Users/me/Downloads')).toBeTruthy();
    expect(screen.getByText('/Users/me/reports')).toBeTruthy();
    expect(screen.getByText('Read only')).toBeTruthy();
    expect(screen.getByText('Read and write')).toBeTruthy();
  });

  it('reports the new state when the checkbox is clicked', () => {
    const onCheckedChange = vi.fn();
    render(<PathGrantToggle directories={directories} checked={false} onCheckedChange={onCheckedChange} />);

    fireEvent.click(screen.getByRole('checkbox', { name: 'Also grant folder access' }));

    expect(onCheckedChange).toHaveBeenCalledWith(true);
  });

  it('toggles from the label as well', () => {
    const onCheckedChange = vi.fn();
    render(<PathGrantToggle directories={directories} checked onCheckedChange={onCheckedChange} />);

    fireEvent.click(screen.getByText('Also grant folder access'));

    expect(onCheckedChange).toHaveBeenCalledWith(false);
  });

  it('cannot be toggled while disabled', () => {
    const onCheckedChange = vi.fn();
    render(<PathGrantToggle directories={directories} checked={false} onCheckedChange={onCheckedChange} disabled />);

    fireEvent.click(screen.getByRole('checkbox'));

    expect(onCheckedChange).not.toHaveBeenCalled();
  });
});
