import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { TailscaleAccessCard } from '../TailscaleAccessCard';
import { remoteAccessService, type TailscaleStatus } from '@/services/remoteAccess';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { toast } from '@/lib/utils/toast';

const translations: Record<string, string> = {
  'tailscale.title': 'Tailscale 零信任远程访问',
  'tailscale.badge': '零信任安全',
  'tailscale.description': '通过 Tailscale 私有网格直接安全互联，流量全链路端到端 WireGuard 加密',
  'tailscale.statusActive': '已连接 Tailnet',
  'tailscale.statusInactive': 'Tailscale 未运行或未连接',
  'tailscale.statusNotInstalled': '未检测到 Tailscale 客户端',
  'tailscale.ipLabel': 'Tailscale IP 地址',
  'tailscale.magicDnsLabel': 'MagicDNS 域名',
  'tailscale.nodeLabel': '节点名',
  'tailscale.userLabel': '认证用户',
  'tailscale.modeHttps': 'HTTPS 安全通道',
  'tailscale.modeDirect': '内网直连',
  'tailscale.serveHint': '提示：在终端执行 tailscale serve --bg http://localhost:{port} 即可启用 MagicDNS HTTPS 域名',
  'tailscale.scanHint': '在同一 Tailnet 内的手机扫码即可直接直连',
  'tailscale.qrAlt': 'Tailscale 访问二维码',
  'tailscale.learnMore': '了解 Tailscale 零信任网络',
  copied: '已复制',
  open: '在新标签页打开',
  copy: '复制链接',
};

const stableT = (key: string) => translations[key] || key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/remoteAccess', () => ({
  remoteAccessService: {
    getTailscaleStatus: vi.fn(),
  },
}));

vi.mock('@/lib/utils/clipboardUtils', () => ({
  writeToClipboard: vi.fn(),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe('TailscaleAccessCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders not installed state when Tailscale is not found', async () => {
    (remoteAccessService.getTailscaleStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      installed: false,
      running: false,
      backend_state: 'NoState',
      ips: [],
      nodeName: null,
      magicDns: false,
      fqdn: null,
      tailnet: null,
      user: null,
      serveUrl: null,
    } satisfies TailscaleStatus);

    render(<TailscaleAccessCard webuiPort={3000} />);

    await waitFor(() => {
      expect(screen.getByText('Tailscale 零信任远程访问')).toBeInTheDocument();
      expect(screen.getByText('零信任安全')).toBeInTheDocument();
      expect(screen.getByText('未检测到 Tailscale 客户端')).toBeInTheDocument();
      expect(screen.getByText('了解 Tailscale 零信任网络')).toBeInTheDocument();
    });
  });

  it('renders inactive state when Tailscale is installed but daemon is stopped', async () => {
    (remoteAccessService.getTailscaleStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      installed: true,
      running: false,
      backend_state: 'Stopped',
      ips: [],
      nodeName: null,
      magicDns: false,
      fqdn: null,
      tailnet: null,
      user: null,
      serveUrl: null,
    } satisfies TailscaleStatus);

    render(<TailscaleAccessCard webuiPort={3000} />);

    await waitFor(() => {
      expect(screen.getByText('Tailscale 未运行或未连接')).toBeInTheDocument();
    });
  });

  it('renders active state with HTTPS serve URL when serve is active', async () => {
    (remoteAccessService.getTailscaleStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      installed: true,
      running: true,
      backend_state: 'Running',
      ips: ['100.64.1.2'],
      nodeName: 'macbook-dev',
      magicDns: true,
      fqdn: 'macbook-dev.tailnet.ts.net',
      tailnet: 'tailnet.ts.net',
      user: 'alice@example.com',
      serveUrl: 'https://macbook-dev.tailnet.ts.net',
    } satisfies TailscaleStatus);

    render(<TailscaleAccessCard webuiPort={3000} />);

    await waitFor(() => {
      expect(screen.getByText('已连接 Tailnet')).toBeInTheDocument();
      expect(screen.getByText('HTTPS 安全通道')).toBeInTheDocument();
      expect(screen.getByText('https://macbook-dev.tailnet.ts.net')).toBeInTheDocument();
      expect(screen.getByText('(macbook-dev @ tailnet.ts.net)')).toBeInTheDocument();
      expect(screen.getByText('100.64.1.2')).toBeInTheDocument();
      expect(screen.getByText('macbook-dev.tailnet.ts.net')).toBeInTheDocument();
      expect(screen.getByText('alice@example.com')).toBeInTheDocument();
      expect(screen.queryByText(/tailscale serve --bg/)).not.toBeInTheDocument();
    });
  });

  it('renders active state with Direct HTTP mode when serve is not active', async () => {
    (remoteAccessService.getTailscaleStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      installed: true,
      running: true,
      backend_state: 'Running',
      ips: ['100.64.1.2'],
      nodeName: 'macbook-dev',
      magicDns: true,
      fqdn: 'macbook-dev.tailnet.ts.net',
      tailnet: 'tailnet.ts.net',
      user: 'bob@example.com',
      serveUrl: null,
    } satisfies TailscaleStatus);

    render(<TailscaleAccessCard webuiPort={3000} />);

    await waitFor(() => {
      expect(screen.getByText('已连接 Tailnet')).toBeInTheDocument();
      expect(screen.getByText('内网直连')).toBeInTheDocument();
      expect(screen.getByText('http://macbook-dev.tailnet.ts.net:3000')).toBeInTheDocument();
      expect(screen.getByText(/tailscale serve --bg http:\/\/localhost:3000/)).toBeInTheDocument();
    });
  });

  it('falls back to IP URL when fqdn is missing and serveUrl is null', async () => {
    (remoteAccessService.getTailscaleStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      installed: true,
      running: true,
      backend_state: 'Running',
      ips: ['100.100.1.5'],
      nodeName: null,
      magicDns: false,
      fqdn: null,
      tailnet: null,
      user: null,
      serveUrl: null,
    } satisfies TailscaleStatus);

    render(<TailscaleAccessCard webuiPort={8080} />);

    await waitFor(() => {
      expect(screen.getByText('http://100.100.1.5:8080')).toBeInTheDocument();
    });
  });

  it('handles refresh button click by fetching status again', async () => {
    const mockGetStatus = (remoteAccessService.getTailscaleStatus as unknown as ReturnType<typeof vi.fn>);
    mockGetStatus.mockResolvedValue({
      installed: true,
      running: true,
      backend_state: 'Running',
      ips: ['100.64.1.2'],
      nodeName: 'macbook-dev',
      magicDns: true,
      fqdn: 'macbook-dev.tailnet.ts.net',
      tailnet: null,
      user: null,
      serveUrl: null,
    } satisfies TailscaleStatus);

    render(<TailscaleAccessCard webuiPort={3000} />);

    await waitFor(() => {
      expect(mockGetStatus).toHaveBeenCalledTimes(1);
    });

    const refreshBtn = screen.getByTitle('Refresh Tailscale status');
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(mockGetStatus).toHaveBeenCalledTimes(2);
    });
  });

  it('handles copy button click and displays copied feedback', async () => {
    (remoteAccessService.getTailscaleStatus as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      installed: true,
      running: true,
      backend_state: 'Running',
      ips: ['100.64.1.2'],
      nodeName: 'macbook-dev',
      magicDns: true,
      fqdn: 'macbook-dev.tailnet.ts.net',
      tailnet: null,
      user: null,
      serveUrl: 'https://macbook-dev.tailnet.ts.net',
    } satisfies TailscaleStatus);

    render(<TailscaleAccessCard webuiPort={3000} />);

    await waitFor(() => {
      expect(screen.getByText('https://macbook-dev.tailnet.ts.net')).toBeInTheDocument();
    });

    const copyBtn = screen.getByTitle('复制链接');
    fireEvent.click(copyBtn);

    expect(writeToClipboard).toHaveBeenCalledWith('https://macbook-dev.tailnet.ts.net');
    expect(toast.success).toHaveBeenCalledWith('已复制');
  });
});
