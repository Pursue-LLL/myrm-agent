/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { WeChatTroubleshootGuide } from '../WeChatTroubleshootGuide';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();

vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => mockToastSuccess(...args),
    error: (...args: unknown[]) => mockToastError(...args),
  },
}));

describe('WeChatTroubleshootGuide', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders toggle button initially without expanding panel', () => {
    render(<WeChatTroubleshootGuide channelName="wechat" status={null} />);
    expect(screen.getByTestId('wechat-troubleshoot-toggle')).toBeInTheDocument();
    expect(screen.queryByTestId('wechat-troubleshoot-panel')).not.toBeInTheDocument();
  });

  it('toggles panel open to show 4-step checklist on click', () => {
    render(
      <WeChatTroubleshootGuide
        channelName="wechat"
        status={{
          connected: false,
          status: 'stopped',
          qr_code: null,
          bot_id: null,
        }}
      />,
    );
    fireEvent.click(screen.getByTestId('wechat-troubleshoot-toggle'));

    expect(screen.getByTestId('wechat-troubleshoot-panel')).toBeInTheDocument();
    expect(screen.getByText('wechatTroubleshootTitle')).toBeInTheDocument();
    expect(screen.getByText('wechatTroubleshootStep1Title')).toBeInTheDocument();
    expect(screen.getByText('wechatTroubleshootStep2Title')).toBeInTheDocument();
    expect(screen.getByText('wechatTroubleshootStep3Title')).toBeInTheDocument();
    expect(screen.getByText('wechatTroubleshootStep4Title')).toBeInTheDocument();
  });

  it('triggers onRefreshStatus and shows toast on refresh action', async () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    render(
      <WeChatTroubleshootGuide
        channelName="wechat"
        status={{
          connected: false,
          status: 'stopped',
          qr_code: null,
          bot_id: null,
        }}
        onRefreshStatus={onRefresh}
      />,
    );
    fireEvent.click(screen.getByTestId('wechat-troubleshoot-toggle'));

    const refreshBtn = screen.getByRole('button', { name: /wechatTroubleshootActionRefresh/i });
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(onRefresh).toHaveBeenCalledTimes(1);
      expect(mockToastSuccess).toHaveBeenCalledWith('wechatTroubleshootRefreshSuccess');
    });
  });

  it('triggers onTriggerLogin on re-login action', () => {
    const onLogin = vi.fn();
    render(
      <WeChatTroubleshootGuide
        channelName="wechat"
        status={{
          connected: false,
          status: 'stopped',
          qr_code: null,
          bot_id: null,
        }}
        onTriggerLogin={onLogin}
      />,
    );
    fireEvent.click(screen.getByTestId('wechat-troubleshoot-toggle'));

    const loginBtn = screen.getByRole('button', { name: /wechatTroubleshootActionReLogin/i });
    fireEvent.click(loginBtn);
    expect(onLogin).toHaveBeenCalledTimes(1);
  });

  it('copies masked diagnostics report to clipboard and toasts success', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(
      <WeChatTroubleshootGuide
        channelName="wechat_inst1"
        status={{
          connected: true,
          status: 'running',
          qr_code: null,
          bot_id: 'wxid_sensitive123456',
        }}
      />,
    );
    fireEvent.click(screen.getByTestId('wechat-troubleshoot-toggle'));

    const copyBtn = screen.getByTestId('wechat-troubleshoot-copy-btn');
    fireEvent.click(copyBtn);

    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledTimes(1);
      const text = writeTextMock.mock.calls[0][0];
      expect(text).toContain('Channel: wechat_inst1');
      expect(text).toContain('Status: running');
      expect(text).toContain('BotId: wxi***456');
      expect(text).not.toContain('wxid_sensitive123456');
      expect(mockToastSuccess).toHaveBeenCalledWith('wechatTroubleshootReportCopied');
    });
  });
});
