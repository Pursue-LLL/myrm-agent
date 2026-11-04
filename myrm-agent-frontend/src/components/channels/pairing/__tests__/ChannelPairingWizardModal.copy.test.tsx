/** @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { MockLocale } from '@/test-utils/realIntl';
import en from '../../../../../locales/en.json';
import zh from '../../../../../locales/zh.json';

const intl = vi.hoisted(() => ({ locale: 'en' as MockLocale }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => intl.locale));

import { ChannelPairingWizardModal } from '../ChannelPairingWizardModal';
import { ChannelPairingService } from '../channelPairingService';

// A key the language pack lacks renders as its path (`channelPairing.common.cancel`), so any text shaped like one
// is a missing translation.
const KEY_PATH_TEXT = /^(channelPairing|common|wizard|platforms)\./;

describe('ChannelPairingWizardModal copy through the real language pack', () => {
  afterEach(() => {
    cleanup();
    intl.locale = 'en';
    vi.restoreAllMocks();
  });

  it('shows translated platform cards and the cancel button on the first step', () => {
    render(<ChannelPairingWizardModal isOpen onClose={vi.fn()} />);

    expect(screen.getByText(en.channelPairing.wizard.title)).toBeInTheDocument();
    expect(screen.getByText(en.channelPairing.platforms.wechat.name)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: en.common.cancel })).toBeInTheDocument();
    expect(screen.queryByText(KEY_PATH_TEXT)).toBeNull();
  });

  it('follows the interface language', () => {
    intl.locale = 'zh';
    render(<ChannelPairingWizardModal isOpen onClose={vi.fn()} />);

    expect(screen.getByText(zh.channelPairing.wizard.title)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: zh.common.cancel })).toBeInTheDocument();
    expect(screen.queryByText(KEY_PATH_TEXT)).toBeNull();
  });

  it('shows the translated back button on the scan step', async () => {
    vi.spyOn(ChannelPairingService, 'createPairingSession').mockResolvedValueOnce({
      session_id: 'pair_wx_12345678',
      platform: 'wechat',
      status: 'pending',
      qr_code: {
        pairing_url: 'myrm://channels/handshake?session_id=pair_wx_12345678',
        qr_matrix_base64: 'data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=',
        expires_in_seconds: 300,
      },
      bound_token_masked: null,
      user_identity: null,
      created_at_epoch_ms: 1700000000,
      error_message: null,
    });

    render(<ChannelPairingWizardModal isOpen onClose={vi.fn()} />);
    await act(async () => {
      fireEvent.click(screen.getByTestId('start-pairing-btn'));
    });

    expect(screen.getByRole('button', { name: en.common.back })).toBeInTheDocument();
    expect(screen.queryByText(KEY_PATH_TEXT)).toBeNull();
  });

  it('shows translated summary labels on the success step and the health check card after it', async () => {
    vi.spyOn(ChannelPairingService, 'createPairingSession').mockResolvedValueOnce({
      session_id: 'pair_feishu_8888',
      platform: 'feishu',
      status: 'pending',
      qr_code: {
        pairing_url: 'myrm://channels/handshake?session_id=pair_feishu_8888',
        qr_matrix_base64: 'data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=',
        expires_in_seconds: 300,
      },
      bound_token_masked: null,
      user_identity: null,
      created_at_epoch_ms: 1700000000,
      error_message: null,
    });
    vi.spyOn(ChannelPairingService, 'confirmPairing').mockResolvedValueOnce({
      session_id: 'pair_feishu_8888',
      platform: 'feishu',
      status: 'authenticated',
      persisted: true,
      message: 'Channel feishu successfully authenticated.',
    });
    vi.spyOn(ChannelPairingService, 'getPairingSessionStatus').mockResolvedValueOnce({
      session_id: 'pair_feishu_8888',
      platform: 'feishu',
      status: 'authenticated',
      qr_code: null,
      bound_token_masked: 'feis****8888',
      user_identity: 'ou_feishu_agent_1',
      created_at_epoch_ms: 1700000000,
      error_message: null,
    });

    render(<ChannelPairingWizardModal isOpen initialPlatform="feishu" onClose={vi.fn()} />);
    await act(async () => {
      fireEvent.click(screen.getByTestId('start-pairing-btn'));
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('simulate-scan-btn'));
    });

    const { wizard, healthCheck } = en.channelPairing;
    expect(screen.getByText(wizard.summaryPlatform)).toBeInTheDocument();
    expect(screen.getByText(wizard.summaryIdentity)).toBeInTheDocument();
    expect(screen.getByText(wizard.summaryCredential)).toBeInTheDocument();
    expect(screen.queryByText(KEY_PATH_TEXT)).toBeNull();

    await act(async () => {
      fireEvent.click(screen.getByTestId('go-to-healthcheck-btn'));
    });

    expect(screen.getByText(healthCheck.title)).toBeInTheDocument();
    expect(screen.getByText(healthCheck.sendPing)).toBeInTheDocument();
    expect(screen.queryByText(KEY_PATH_TEXT)).toBeNull();
  });
});
