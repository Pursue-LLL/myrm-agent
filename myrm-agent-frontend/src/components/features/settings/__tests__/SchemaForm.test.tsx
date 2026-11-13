/** @vitest-environment jsdom */
/**
 * The schema-driven settings form as a screen-reader user meets it: every control carries the title written next to
 * it, and the title is a real label, so clicking it reaches the control.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { toast } from 'sonner';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SchemaForm } from '../SchemaForm';

const stableT = Object.assign((key: string) => key, { has: () => false });
vi.mock('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

const SCHEMA = {
  type: 'object',
  properties: {
    autoSave: { type: 'boolean', default: false },
    nickname: { type: 'string' },
    apiToken: { type: 'string', 'ui:widget': 'password' },
    theme: { type: 'string', enum: ['light', 'dark'] },
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(SCHEMA) })),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('SchemaForm labels', () => {
  it('names every kind of control after its title', async () => {
    render(<SchemaForm configKey="demo" value={{}} onChange={vi.fn()} />);

    expect(await screen.findByRole('switch', { name: 'autoSave' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'nickname' })).toBeInTheDocument();
    expect(screen.getByLabelText('apiToken')).toHaveAttribute('type', 'password');
    expect(screen.getByRole('combobox', { name: 'theme' })).toBeInTheDocument();
  });

  it('keeps the test ids the controls are located by', async () => {
    render(<SchemaForm configKey="demo" value={{}} onChange={vi.fn()} />);

    await screen.findByRole('switch', { name: 'autoSave' });
    expect(screen.getByTestId('config-autoSave')).toBe(screen.getByRole('switch', { name: 'autoSave' }));
    expect(screen.getByTestId('config-nickname')).toBe(screen.getByRole('textbox', { name: 'nickname' }));
    expect(screen.getByTestId('config-theme')).toBe(screen.getByRole('combobox', { name: 'theme' }));
  });

  it('flips the switch when its title is clicked', async () => {
    const onChange = vi.fn();
    render(<SchemaForm configKey="demo" value={{}} onChange={onChange} />);

    fireEvent.click(await screen.findByText('autoSave'));

    expect(onChange).toHaveBeenCalledExactlyOnceWith({ autoSave: true });
  });

  it('keeps each copy of the form bound to its own controls when one page shows it twice', async () => {
    const onChangeFirst = vi.fn();
    const onChangeSecond = vi.fn();
    render(
      <>
        <SchemaForm configKey="demo" value={{}} onChange={onChangeFirst} />
        <SchemaForm configKey="demo" value={{}} onChange={onChangeSecond} />
      </>,
    );
    await waitFor(() => expect(screen.getAllByText('autoSave')).toHaveLength(2));

    fireEvent.click(screen.getAllByText('autoSave')[1]);

    expect(onChangeSecond).toHaveBeenCalledExactlyOnceWith({ autoSave: true });
    expect(onChangeFirst).not.toHaveBeenCalled();
  });
});

describe('SchemaForm schema loading', () => {
  /** A schema request that stays open until the test settles it. */
  function holdSchemaRequest(): { fail: (reason: Error) => void; fetchMock: ReturnType<typeof vi.fn> } {
    let fail: (reason: Error) => void = () => undefined;
    const fetchMock = vi.fn(
      () =>
        new Promise((_, reject) => {
          fail = reject;
        }),
    );
    vi.stubGlobal('fetch', fetchMock);
    return { fail: (reason) => fail(reason), fetchMock };
  }

  it('tells the user once when the schema cannot be loaded', async () => {
    const { fail } = holdSchemaRequest();
    render(<SchemaForm configKey="demo" value={{}} onChange={vi.fn()} />);

    await act(async () => {
      fail(new Error('network down'));
    });

    expect(toast.error).toHaveBeenCalledExactlyOnceWith('schemaForm.loadFailed');
    expect(screen.getByText('schemaForm.noSchema')).toBeInTheDocument();
  });

  it('stays silent about a load that fails after the form is gone', async () => {
    const { fail } = holdSchemaRequest();
    const { unmount } = render(<SchemaForm configKey="demo" value={{}} onChange={vi.fn()} />);
    unmount();

    await act(async () => {
      fail(new Error('network down'));
    });

    expect(toast.error).not.toHaveBeenCalled();
  });

  it('asks again for the schema of another form when its key changes', async () => {
    const { fetchMock } = holdSchemaRequest();
    const { rerender } = render(<SchemaForm configKey="demo" value={{}} onChange={vi.fn()} />);

    rerender(<SchemaForm configKey="other" value={{}} onChange={vi.fn()} />);

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/config/schema/demo',
      '/api/v1/config/schema/other',
    ]);
  });
});
