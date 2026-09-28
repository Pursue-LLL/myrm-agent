/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SSHVaultPanel } from '../SSHVaultPanel';
import type { SSHAssetSummary, SSHProbeResult, BreakGlassResponse } from '@/services/sshVault';

const mockGetSSHVaultSummary = vi.hoisted(() => vi.fn());
const mockProbeSSHHost = vi.hoisted(() => vi.fn());
const mockUpdateHostPolicy = vi.hoisted(() => vi.fn());
const mockRequestBreakGlassToken = vi.hoisted(() => vi.fn());
const mockToast = vi.hoisted(() => vi.fn());

const translations: Record<string, string> = {
  title: 'SSH 主机与 SFTP 凭据管理',
  source: '配置来源',
  refresh: '刷新主机列表',
  noHosts: '未发现已配置的 SSH 主机。可在 ~/.ssh/config 中添加配置或在设置中配置凭据。',
  probing: '正在探测连通性...',
  probe: '测试连接',
  statusUntested: '未测试',
  copyPrompt: '复制 Agent 调用提示词',
  copied: '已复制！',
  useInPrompt: '在对话中使用此主机',
  readOnlyBadge: '只读安全锁',
  writableBadge: '读写模式',
  readOnlyDesc: '生产级受保护隔离，拦截所有高危破坏性与写命令',
  breakGlassAction: '申请变更破窗',
  breakGlassModalTitle: '受保护变更窗口破窗申请',
  breakGlassReason: '变更原因',
  breakGlassReasonPlaceholder: '说明在受保护节点上执行变更的必要性与工单号...',
  breakGlassCommand: '变更命令',
  breakGlassTtl: '窗口有效期 (秒)',
  breakGlassSubmit: '签发单次破窗令牌',
  breakGlassSuccess: '破窗令牌已签发并可单次执行',
  policyUpdated: '安全策略更新成功',
  tierProd: '生产环境',
  tierStaging: '预发环境',
  tierDev: '开发环境',
};

const stableT = (key: string) => translations[key] || key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/sshVault', () => ({
  getSSHVaultSummary: () => mockGetSSHVaultSummary(),
  probeSSHHost: (host: string) => mockProbeSSHHost(host),
  updateHostPolicy: (host: string, update: unknown) => mockUpdateHostPolicy(host, update),
  requestBreakGlassToken: (payload: unknown) => mockRequestBreakGlassToken(payload),
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: (args: unknown) => mockToast(args),
}));

const mockSummary: SSHAssetSummary = {
  total_hosts: 2,
  config_path: '~/.ssh/config',
  hosts: [
    {
      host_alias: 'prod-cluster-01',
      hostname: '10.0.0.1',
      user: 'root',
      port: 22,
      is_read_only: true,
      environment_tier: 'production',
      require_confirm_on_write: true,
      source: 'ssh_config',
    },
    {
      host_alias: 'dev-box',
      hostname: '192.168.1.50',
      user: 'developer',
      port: 2222,
      is_read_only: false,
      environment_tier: 'development',
      require_confirm_on_write: false,
      source: 'ssh_config',
    },
  ],
};

describe('SSHVaultPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetSSHVaultSummary.mockResolvedValue(mockSummary);
    mockProbeSSHHost.mockResolvedValue({
      host_alias: 'prod-cluster-01',
      reachable: true,
      latency_ms: 12.4,
    } as SSHProbeResult);
    mockUpdateHostPolicy.mockResolvedValue({ status: 'ok', host_alias: 'prod-cluster-01' });
    mockRequestBreakGlassToken.mockResolvedValue({
      token: 'bg_tok_test_nonce_9999',
      host_alias: 'prod-cluster-01',
      reason: 'Urgent hotfix',
      expires_at: Date.now() / 1000 + 300,
    } as BreakGlassResponse);
  });

  it('renders SSH hosts list with read-only badge and environments', async () => {
    render(<SSHVaultPanel />);

    await waitFor(() => {
      expect(screen.getByText('prod-cluster-01')).toBeInTheDocument();
      expect(screen.getByText('dev-box')).toBeInTheDocument();
    });

    expect(screen.getByText(/10\.0\.0\.1/)).toBeInTheDocument();
    expect(screen.getByText(/192\.168\.1\.50:2222/)).toBeInTheDocument();
    expect(screen.getByText('生产环境')).toBeInTheDocument();
    expect(screen.getByText('开发环境')).toBeInTheDocument();
  });

  it('probes SSH host connectivity and displays latency', async () => {
    render(<SSHVaultPanel />);

    await waitFor(() => {
      expect(screen.getByText('prod-cluster-01')).toBeInTheDocument();
    });

    const probeButtons = screen.getAllByRole('button', { name: /测试连接/i });
    fireEvent.click(probeButtons[0]);

    await waitFor(() => {
      expect(mockProbeSSHHost).toHaveBeenCalledWith('prod-cluster-01');
      expect(screen.getByText(/12\.4ms/i)).toBeInTheDocument();
    });
  });

  it('toggles read-only gate policy', async () => {
    render(<SSHVaultPanel />);

    await waitFor(() => {
      expect(screen.getByText('prod-cluster-01')).toBeInTheDocument();
    });

    const readOnlyButton = screen.getByRole('button', { name: /只读安全锁/i });
    fireEvent.click(readOnlyButton);

    await waitFor(() => {
      expect(mockUpdateHostPolicy).toHaveBeenCalledWith('prod-cluster-01', {
        is_read_only: false,
      });
    });
  });

  it('opens break-glass modal and requests single-use token', async () => {
    render(<SSHVaultPanel />);

    await waitFor(() => {
      expect(screen.getByText('prod-cluster-01')).toBeInTheDocument();
    });

    const breakGlassBtn = screen.getByRole('button', { name: /申请变更破窗/i });
    fireEvent.click(breakGlassBtn);

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    const cmdInput = screen.getByPlaceholderText(/e\.g\. systemctl restart nginx/i);
    const reasonInput = screen.getByPlaceholderText(/说明在受保护节点上执行变更的必要性/i);

    fireEvent.change(cmdInput, { target: { value: 'systemctl restart nginx' } });
    fireEvent.change(reasonInput, { target: { value: 'Emergency hotfix' } });

    const submitBtn = screen.getByRole('button', { name: /签发单次破窗令牌/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockRequestBreakGlassToken).toHaveBeenCalledWith({
        host_alias: 'prod-cluster-01',
        command: 'systemctl restart nginx',
        reason: 'Emergency hotfix',
        ttl_seconds: 300,
      });
      expect(screen.getByText('bg_tok_test_nonce_9999')).toBeInTheDocument();
    });
  });

  it('renders offline status when host probe indicates unreachable', async () => {
    mockProbeSSHHost.mockResolvedValueOnce({
      host_alias: 'prod-cluster-01',
      is_reachable: false,
      latency_ms: 0,
      error_message: 'Connection timed out',
    } as SSHProbeResult);

    render(<SSHVaultPanel />);

    await waitFor(() => {
      expect(screen.getByText('prod-cluster-01')).toBeInTheDocument();
    });

    const probeButtons = screen.getAllByRole('button', { name: /测试连接/i });
    fireEvent.click(probeButtons[0]);

    await waitFor(() => {
      expect(screen.getByText(/Offline/i)).toBeInTheDocument();
    });
  });

  it('displays custom config_source path in header', async () => {
    mockGetSSHVaultSummary.mockResolvedValueOnce({
      total_hosts: 1,
      config_source: '/etc/ssh/ssh_config.d/custom.conf',
      hosts: [
        {
          host_alias: 'custom-node',
          hostname: '10.10.10.1',
          user: 'ops',
          port: 22,
          is_read_only: true,
          environment_tier: 'staging',
          require_confirm_on_write: true,
          source: 'custom',
        },
      ],
    });

    render(<SSHVaultPanel />);

    await waitFor(() => {
      expect(screen.getByText(/\/etc\/ssh\/ssh_config\.d\/custom\.conf/i)).toBeInTheDocument();
    });
  });

  it('renders empty hosts message when summary returns no hosts', async () => {
    mockGetSSHVaultSummary.mockResolvedValueOnce({
      total_hosts: 0,
      hosts: [],
      config_source: '~/.ssh/config',
    });

    render(<SSHVaultPanel />);

    await waitFor(() => {
      expect(screen.getByText(/未发现已配置的 SSH 主机/i)).toBeInTheDocument();
    });
  });

  it('shows error toast when probe fails with network exception', async () => {
    mockProbeSSHHost.mockRejectedValueOnce(new Error('Network error 500'));

    render(<SSHVaultPanel />);

    await waitFor(() => {
      expect(screen.getByText('prod-cluster-01')).toBeInTheDocument();
    });

    const probeButtons = screen.getAllByRole('button', { name: /测试连接/i });
    fireEvent.click(probeButtons[0]);

    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith(
        expect.objectContaining({
          variant: 'destructive',
          title: expect.stringContaining('Network error 500'),
        }),
      );
    });
  });
});
