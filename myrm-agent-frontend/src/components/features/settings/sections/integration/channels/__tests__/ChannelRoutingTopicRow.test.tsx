/** @vitest-environment jsdom */
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import type { TopicBinding } from '@/services/channels';

const configState = vi.hoisted(() => ({
  _configStoreReady: true,
  personalSettings: { notificationDeliveries: [] as { channel: string; target: string }[] },
}));

const stableT = (key: string, values?: Record<string, unknown>) =>
  values && 'minutes' in values ? `${key}:${values.minutes}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a>,
}));

vi.mock('@/store/useConfigStore', () => ({
  default: (selector: (state: typeof configState) => unknown) => selector(configState),
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconAlertCircle: () => <span data-testid="icon-alert" />,
  IconLoader: () => <span data-testid="icon-loader" />,
  IconUser: () => <span data-testid="icon-user" />,
}));

vi.mock('@/components/agent/builtin-agent-i18n', () => ({
  getBuiltinAgentName: (_agentId: string, name: string) => name,
}));

import { ChannelRoutingTopicRow } from '../ChannelRoutingTopicRow';

const baseTopic: TopicBinding = {
  topicId: 'topic-1',
  agentId: null,
  displayName: 'Sales chat',
  avatarUrl: null,
  threadSharingMode: 'isolated',
  replyMode: 'draft_review',
  draftTimeoutMinutes: 5,
  draftTimeoutAction: 'auto_reject',
  identityScope: 'inherit',
  identityId: null,
  identityName: null,
  identityRevoked: false,
  completionReceipts: true,
  stallNudge: false,
};

function renderRow(topic: Partial<TopicBinding> = {}) {
  const onSetDraftTimeout = vi.fn();
  render(
    <ChannelRoutingTopicRow
      agents={[]}
      projects={[]}
      isSaving={false}
      onBindTopic={vi.fn()}
      onBindTopicWorkspace={vi.fn()}
      onSetDraftTimeout={onSetDraftTimeout}
      onSetReplyMode={vi.fn()}
      onSetThreadSharingMode={vi.fn()}
      onSetIdentity={vi.fn()}
      onRevokeIdentity={vi.fn()}
      onSetFollowUp={vi.fn()}
      topic={{ ...baseTopic, ...topic }}
    />,
  );
  return { onSetDraftTimeout };
}

describe('ChannelRoutingTopicRow draft review', () => {
  beforeEach(() => {
    configState._configStoreReady = true;
    configState.personalSettings = { notificationDeliveries: [] };
  });

  it('words every timeout option through the translations, spelling out the one-hour option', () => {
    renderRow();

    const timeout = screen.getByDisplayValue('replyMode.timeoutMinutes:5');
    const labels = Array.from(timeout.querySelectorAll('option')).map((option) => option.textContent);
    expect(labels).toEqual([
      'replyMode.timeoutMinutes:1',
      'replyMode.timeoutMinutes:3',
      'replyMode.timeoutMinutes:5',
      'replyMode.timeoutMinutes:10',
      'replyMode.timeoutMinutes:15',
      'replyMode.timeoutMinutes:30',
      'replyMode.timeoutHour',
    ]);
  });

  it('reports the chosen timeout together with the current expiry action', () => {
    const { onSetDraftTimeout } = renderRow({ draftTimeoutAction: 'auto_send' });

    fireEvent.change(screen.getByDisplayValue('replyMode.timeoutMinutes:5'), { target: { value: '30' } });

    expect(onSetDraftTimeout).toHaveBeenCalledWith('topic-1', 30, 'auto_send');
  });

  it('warns when replies wait for review but no notification delivery could tell the owner', () => {
    renderRow();

    expect(screen.getByText('replyMode.noNotifyChannel')).toBeTruthy();
    expect(screen.getByText('replyMode.noNotifyChannelLink').closest('a')?.getAttribute('href')).toBe(
      '/settings/preferences',
    );
  });

  it('stays quiet once a notification delivery is configured', () => {
    configState.personalSettings = { notificationDeliveries: [{ channel: 'telegram', target: '123456789' }] };

    renderRow();

    expect(screen.queryByText('replyMode.noNotifyChannel')).toBeNull();
  });

  it('stays quiet until the settings have loaded', () => {
    configState._configStoreReady = false;

    renderRow();

    expect(screen.queryByText('replyMode.noNotifyChannel')).toBeNull();
  });

  it('shows neither the timeout controls nor the warning for auto-send topics', () => {
    renderRow({ replyMode: 'auto' });

    expect(screen.queryByText('replyMode.timeout:')).toBeNull();
    expect(screen.queryByText('replyMode.noNotifyChannel')).toBeNull();
  });

  it.each(['threadSharing.label:', 'replyMode.label:'])(
    'lets the %s row and its buttons wrap, so long translations are not clipped on a narrow screen',
    (labelText) => {
      renderRow();

      const label = screen.getByText(labelText);
      expect(label.parentElement?.className).toContain('flex-wrap');
      expect(label.nextElementSibling?.className).toContain('flex-wrap');
    },
  );

  it('lets the agent select shrink and the identity scope buttons wrap, so a long translation never leaves the card', () => {
    renderRow();

    expect(screen.getByDisplayValue('inheritGlobalDefault').className).toContain('min-w-0');
    expect(screen.getByText('identity.inherit').parentElement?.className).toContain('flex-wrap');
  });
});
