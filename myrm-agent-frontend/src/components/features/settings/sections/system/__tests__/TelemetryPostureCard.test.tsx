import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import TelemetryPostureCard from '../TelemetryPostureCard';
import { systemService } from '@/services/system';

const translations: Record<string, string> = {
  title: 'OpenTelemetry Trace Posture',
  description: 'Inspect real-time OTLP exporter connectivity',
  refresh: 'Refresh',
  copyEnv: 'Copy Env',
  copied: 'Copied',
  protocol: 'Protocol',
  endpoint: 'OTLP Endpoint',
  headers: 'Auth Headers',
  environment: 'VCS Environment',
  noVcsTag: 'Non-Git Workspace',
  features: 'Capabilities',
  configured: 'Configured',
  none: 'None',
  notConfigured: 'Not configured (Local NoOp)',
  threeTierReady: '3-Tier GenAI Spans Ready',
  'status.active': 'Active',
  'status.noop': 'Standby (NoOp)',
  'status.degradedConsole': 'Degraded (Console)',
  degradedWarning: 'OTLP export degraded to console output to prevent task blocking.',
  degradedHelp: 'Reason: connection refused. Check your OTLP collector network reachability or credentials.',
};

const stableT = (key: string) => translations[key] || key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/system', () => ({
  systemService: {
    getTelemetryPosture: vi.fn(),
  },
}));

describe('TelemetryPostureCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders active telemetry posture correctly', async () => {
    (systemService.getTelemetryPosture as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: 'active',
      initialized: true,
      has_sdk: true,
      endpoint: 'http://apm.internal:4318',
      protocol: 'http/protobuf',
      headers_configured: true,
      local_trace_only: false,
      three_tier_semantics: true,
      prompt_cache_metering: true,
    });

    render(<TelemetryPostureCard />);

    await waitFor(() => {
      expect(screen.getByText('OpenTelemetry Trace Posture')).toBeInTheDocument();
      expect(screen.getByText('HTTP/PROTOBUF')).toBeInTheDocument();
      expect(screen.getByText('http://apm.internal:4318')).toBeInTheDocument();
      expect(screen.getByText('Non-Git Workspace')).toBeInTheDocument();
      expect(screen.getByText('3-Tier GenAI Spans Ready')).toBeInTheDocument();
    });
  });

  it('renders noop standby posture when not configured', async () => {
    (systemService.getTelemetryPosture as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: 'noop',
      initialized: false,
      has_sdk: true,
      endpoint: null,
      protocol: 'http/protobuf',
      headers_configured: false,
      local_trace_only: false,
      three_tier_semantics: true,
      prompt_cache_metering: true,
    });

    render(<TelemetryPostureCard />);

    await waitFor(() => {
      expect(screen.getByText('Not configured (Local NoOp)')).toBeInTheDocument();
      expect(screen.getByText('Non-Git Workspace')).toBeInTheDocument();
    });
  });

  it('renders degraded console warning banner when status is degraded_console', async () => {
    (systemService.getTelemetryPosture as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: 'degraded_console',
      initialized: true,
      has_sdk: true,
      endpoint: 'http://broken.internal:4318',
      protocol: 'http/protobuf',
      headers_configured: false,
      local_trace_only: false,
      exporter_type: 'console',
      degraded_reason: 'connection refused',
      three_tier_semantics: true,
      prompt_cache_metering: true,
    });

    render(<TelemetryPostureCard />);

    await waitFor(() => {
      expect(screen.getByText('Degraded (Console)')).toBeInTheDocument();
      expect(
        screen.getByText('OTLP export degraded to console output to prevent task blocking.'),
      ).toBeInTheDocument();
    });
  });

  it('renders VCS git branch and commit badge when available', async () => {
    (systemService.getTelemetryPosture as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: 'active',
      initialized: true,
      has_sdk: true,
      endpoint: 'http://apm.internal:4318',
      protocol: 'http/protobuf',
      headers_configured: true,
      local_trace_only: false,
      git_branch: 'feature/item-12',
      git_commit: '7a8b9c0',
      three_tier_semantics: true,
      prompt_cache_metering: true,
    });

    render(<TelemetryPostureCard />);

    await waitFor(() => {
      expect(screen.getByText('feature/item-12')).toBeInTheDocument();
      expect(screen.getByText('(7a8b9c0)')).toBeInTheDocument();
    });
  });
});


