/** @vitest-environment jsdom */
/** The link embed card as a screen-reader user meets it: the mode select is named by the card row title and described by its text. */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import useEmbedConsentStore from '@/store/useEmbedConsentStore';

import LinkEmbedSettings from '../LinkEmbedSettings';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({ useTranslations: () => stableT }));

beforeEach(() => {
  useEmbedConsentStore.setState({ embedMode: 'ask', allowedProviders: [] });
});

afterEach(cleanup);

describe('LinkEmbedSettings', () => {
  it('names the mode select after the row title and describes it with the row text', () => {
    render(<LinkEmbedSettings />);

    const select = screen.getByRole('combobox', { name: 'linkEmbedsMode' });
    expect(select).toHaveAccessibleDescription('linkEmbedsDesc');
    expect(select).toHaveValue('ask');
  });

  it('stores the mode the user picks', () => {
    render(<LinkEmbedSettings />);

    fireEvent.change(screen.getByRole('combobox', { name: 'linkEmbedsMode' }), { target: { value: 'off' } });

    expect(useEmbedConsentStore.getState().embedMode).toBe('off');
  });

  it('lists the allowed providers only when there are some and forgets them on request', () => {
    const { rerender } = render(<LinkEmbedSettings />);
    expect(screen.queryByRole('button', { name: 'linkEmbedsClear' })).toBeNull();

    useEmbedConsentStore.setState({ allowedProviders: ['youtube', 'spotify'] });
    rerender(<LinkEmbedSettings />);
    expect(screen.getByText(/youtube, spotify/)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'linkEmbedsClear' }));

    expect(useEmbedConsentStore.getState().allowedProviders).toEqual([]);
    expect(screen.queryByRole('button', { name: 'linkEmbedsClear' })).toBeNull();
  });
});
