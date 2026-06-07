/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('next-intl', () => ({
  useTranslations: (ns: string) => (key: string) => (ns === 'settings.communication.desc' ? `desc.${key}` : key),
}));

const searchParams = new URLSearchParams();

vi.mock('next/navigation', () => ({
  useSearchParams: () => searchParams,
}));

vi.mock('@/hooks/useSettingsSubTabUrl', () => ({
  useSettingsSubTabUrl: () => ({ handleTabChange: vi.fn() }),
  defaultSubTabResolver: () => () => 'channels',
}));

vi.mock('../sections/integration/channels/ChannelsSection', () => ({
  default: () => <div data-testid="channels-section" />,
}));
vi.mock('../sections/integration/channels/ChannelRoutingSection', () => ({
  default: () => <div data-testid="routing-section" />,
}));
vi.mock('../sections/integration/channels/VoiceSection', () => ({
  default: () => <div data-testid="voice-section" />,
}));

import CommunicationSection from '../sections/integration/CommunicationSection';

describe('CommunicationSection', () => {
  beforeEach(() => {
    searchParams.delete('sub');
  });

  it('mounts channels tab shell by default', () => {
    render(<CommunicationSection />);
    expect(screen.getByRole('heading', { name: 'menu.channels' })).toBeInTheDocument();
    expect(screen.getByText('desc.channels')).toBeInTheDocument();
    expect(screen.getByTestId('channels-section')).toBeInTheDocument();
  });

  it('selects routing sub-tab from search params', () => {
    searchParams.set('sub', 'routing');
    render(<CommunicationSection />);
    expect(screen.getByTestId('routing-section')).toBeInTheDocument();
  });
});
