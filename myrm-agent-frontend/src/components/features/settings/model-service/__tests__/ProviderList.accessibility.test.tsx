import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { ProviderConfig } from '@/store/config/providerTypes';
import { expectDefined } from '@/test-utils/expectDefined';
import ProviderList from '../ProviderList';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'zh'));

vi.mock('../ProviderIcon', () => ({ default: () => null }));

const provider = (id: string, name: string): ProviderConfig => ({
  id,
  routingProfile: id,
  name,
  isBuiltIn: true,
  isEnabled: true,
  apiKeys: [],
  apiUrl: '',
  enabledModels: [],
  availableModels: [],
});

describe('ProviderList keyboard reordering', () => {
  it('announces provider names in the UI language, never the provider id', async () => {
    const user = userEvent.setup();
    render(
      <ProviderList
        providers={[provider('prov-7f3a', 'OpenAI'), provider('prov-9c1d', 'Anthropic')]}
        selectedId="prov-7f3a"
        onSelect={vi.fn()}
        onAddProvider={vi.fn()}
        onRemoveProvider={vi.fn()}
      />,
    );

    const [handle] = screen.getAllByRole('button', { name: '拖动调整顺序' });
    expectDefined(handle, 'first drag handle');
    expect(handle).toHaveAttribute('aria-roledescription', '可拖动项');

    await act(async () => handle.focus());
    await user.keyboard(' ');

    const liveRegion = screen.getByRole('status');
    expect(liveRegion).toHaveTextContent('已拾起“OpenAI”。');
    expect(liveRegion).not.toHaveTextContent('prov-7f3a');
  });
});
