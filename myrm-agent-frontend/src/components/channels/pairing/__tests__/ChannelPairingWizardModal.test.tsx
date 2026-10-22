import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { ChannelPairingWizardModal } from '../ChannelPairingWizardModal';
import { ChannelPairingService } from '../channelPairingService';

const stableT = (key: string) => {
  const table: Record<string, string> = {
    'wizard.title': '外部渠道可视化配对向导',
    'wizard.modelAgnosticBadge': '模型无关解耦 · 零命令确定性配对',
    'wizard.antiWorkbuddyNote': '彻底告别手敲 acquire_token',
    'wizard.antiWorkbuddyDesc': '无需切换昂贵模型或在聊天框输入配置命令，点击渠道即可直接生成动态二维码一键连通。',
    'wizard.waitingScan': '请使用对应客户端扫描上方动态二维码...',
    'wizard.sessionExpiry': '凭证有效时长: 300 秒',
    'wizard.bindingSuccess': '渠道鉴权与 Token 绑定成功！',
    'wizard.bindingSuccessDesc': '凭证已安全加密写入本地沙箱，渠道已准备就绪。',
    'wizard.startPairing': '开始扫码配对',
    'wizard.confirmScanned': '模拟完成扫码',
    'wizard.proceedPing': '一键连通性自测',
    'wizard.done': '完成并关闭',
    'platforms.wechat.name': '微信',
    'platforms.wechat.desc': '手机扫码动态配对，零命令下发',
    'platforms.feishu.name': '飞书 / Lark',
    'platforms.feishu.desc': '应用自建机器人与消息卡片',
    'platforms.dingtalk.name': '钉钉',
    'platforms.dingtalk.desc': '群机器人与专属安全推送',
  };
  return table[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('ChannelPairingWizardModal', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = render(<ChannelPairingWizardModal isOpen={false} onClose={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders step 1 platform selection when isOpen is true', () => {
    render(<ChannelPairingWizardModal isOpen={true} onClose={vi.fn()} />);

    expect(screen.getByTestId('channel-pairing-modal')).toBeInTheDocument();
    expect(screen.getByText('外部渠道可视化配对向导')).toBeInTheDocument();
    expect(screen.getByText('模型无关解耦 · 零命令确定性配对')).toBeInTheDocument();
    expect(screen.getByTestId('platform-card-wechat')).toBeInTheDocument();
    expect(screen.getByTestId('platform-card-feishu')).toBeInTheDocument();
    expect(screen.getByTestId('platform-card-dingtalk')).toBeInTheDocument();
    expect(screen.getByTestId('start-pairing-btn')).toBeInTheDocument();
  });

  it('navigates through step 1 to step 2 with dynamic QR code', async () => {
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

    render(<ChannelPairingWizardModal isOpen={true} onClose={vi.fn()} />);

    const startBtn = screen.getByTestId('start-pairing-btn');
    await act(async () => {
      fireEvent.click(startBtn);
    });

    expect(ChannelPairingService.createPairingSession).toHaveBeenCalledWith({
      platform: 'wechat',
      custom_label: 'wechat connection',
    });

    expect(screen.getByTestId('pairing-qr-image')).toBeInTheDocument();
    expect(screen.getByTestId('simulate-scan-btn')).toBeInTheDocument();
  });

  it('completes scan handshake to step 3 and transitions to step 4 health check', async () => {
    const onCompleteMock = vi.fn();

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

    render(
      <ChannelPairingWizardModal
        isOpen={true}
        initialPlatform="feishu"
        onClose={vi.fn()}
        onPairingComplete={onCompleteMock}
      />,
    );

    // Step 1 -> Step 2
    await act(async () => {
      fireEvent.click(screen.getByTestId('start-pairing-btn'));
    });

    // Step 2 -> Step 3
    const simulateScanBtn = screen.getByTestId('simulate-scan-btn');
    await act(async () => {
      fireEvent.click(simulateScanBtn);
    });

    expect(ChannelPairingService.confirmPairing).toHaveBeenCalled();
    expect(onCompleteMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText('渠道鉴权与 Token 绑定成功！')).toBeInTheDocument();
    expect(screen.getByText('feis****8888')).toBeInTheDocument();

    // Step 3 -> Step 4
    const proceedBtn = screen.getByTestId('go-to-healthcheck-btn');
    await act(async () => {
      fireEvent.click(proceedBtn);
    });

    expect(screen.getByTestId('channel-health-check-card')).toBeInTheDocument();
    expect(screen.getByTestId('finish-wizard-btn')).toBeInTheDocument();
  });

  it('triggers onClose when close button is clicked', () => {
    const onCloseMock = vi.fn();
    render(<ChannelPairingWizardModal isOpen={true} onClose={onCloseMock} />);

    const closeBtn = screen.getByTestId('modal-close-button');
    fireEvent.click(closeBtn);
    expect(onCloseMock).toHaveBeenCalledTimes(1);
  });
});
