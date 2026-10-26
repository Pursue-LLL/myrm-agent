import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import TelemetryPostureCard from '../TelemetryPostureCard';
import { systemService, type TelemetryPosture } from '@/services/system';

const translations: Record<string, string> = {
  title: 'OpenTelemetry export',
  notConfigured: 'Not configured',
  noVcsTag: 'No Git repository',
  configured: 'Configured',
  none: 'None',
  contentMetadataOnly: 'Never exported (metadata only)',
  contentIncluded: 'Included in spans (opt-in)',
  metricsExporting: 'Exporting',
  metricsOff: 'Off',
  delivery: 'Delivery',
  exportedSpans: 'Spans exported',
  failedBatches: 'Failed batches',
  withheldSpans: 'Spans withheld',
  never: 'Never',
  'status.ready': 'Ready',
  'status.active': 'Active',
  'status.failing': 'Failing',
  'status.degraded': 'Degraded',
  'status.disabled': 'Disabled',
  'status.noop': 'Off',
  'status.error': 'Probe error',
  'notice.ready': 'Export is set up but nothing has been sent yet. The first batch goes out after the next agent run.',
  'notice.noop': 'Export is off.',
  'notice.disabled': 'Export is switched off by OTEL_SDK_DISABLED.',
  'notice.failing': 'The last export attempt failed.',
  'notice.degraded': 'Export could not start as configured: {reason}',
  'notice.error': 'The export status could not be read.',
};

const stableT = (key: string, values?: Record<string, string>) => {
  const template = translations[key] ?? key;
  return values ? template.replace(/\{(\w+)\}/g, (_, name: string) => values[name] ?? '') : template;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('@/services/system', () => ({
  systemService: {
    getTelemetryPosture: vi.fn(),
  },
}));

const posture = (overrides: Partial<TelemetryPosture>): TelemetryPosture => ({
  status: 'active',
  initialized: true,
  has_sdk: true,
  endpoint: 'http://apm.internal:4318/v1/traces',
  protocol: 'http/protobuf',
  headers_configured: true,
  local_trace_only: false,
  exporter_type: 'otlp_http',
  degraded_reason: null,
  sampler: 'ParentBased(ALWAYS_ON)',
  content_capture: false,
  metrics_exporting: true,
  exported_spans: 128,
  failed_batches: 0,
  withheld_spans: 0,
  last_success_at: Date.now() / 1000 - 125,
  last_failure_at: null,
  git_branch: null,
  git_commit: null,
  ...overrides,
});

const mockPosture = (value: TelemetryPosture) =>
  (systemService.getTelemetryPosture as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(value);

describe('TelemetryPostureCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows no status until the first measurement arrives', () => {
    (systemService.getTelemetryPosture as unknown as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));

    render(<TelemetryPostureCard />);

    expect(screen.queryByText('Off')).toBeNull();
    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.queryByText('Not configured')).toBeNull();
  });

  it('shows the measured delivery of an active exporter', async () => {
    mockPosture(posture({}));

    const { container } = render(<TelemetryPostureCard />);

    await waitFor(() => {
      expect(screen.getByText('Active')).toBeInTheDocument();
      expect(screen.getByText('http://apm.internal:4318/v1/traces')).toBeInTheDocument();
      expect(screen.getByText('HTTP/PROTOBUF')).toBeInTheDocument();
      expect(screen.getByText('ParentBased(ALWAYS_ON)')).toBeInTheDocument();
      expect(screen.getByText('Never exported (metadata only)')).toBeInTheDocument();
      expect(screen.getByText('Exporting')).toBeInTheDocument();
      expect(screen.getByText('128')).toBeInTheDocument();
      expect(screen.getByText('2 minutes ago')).toBeInTheDocument();
      expect(screen.getByText('Never')).toBeInTheDocument();
    });
    expect(container.querySelector('.animate-pulse')).not.toBeNull();
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('says the exporter is ready, not active, until something has been delivered', async () => {
    mockPosture(posture({ status: 'ready', exported_spans: 0, last_success_at: null }));

    const { container } = render(<TelemetryPostureCard />);

    await waitFor(() => {
      expect(screen.getByText('Ready')).toBeInTheDocument();
      expect(screen.getByRole('status')).toHaveTextContent('Export is set up but nothing has been sent yet.');
      expect(screen.getByText('Delivery')).toBeInTheDocument();
      expect(screen.getAllByText('Never')).toHaveLength(2);
    });
    expect(screen.queryByText('Active')).toBeNull();
    expect(container.querySelector('.animate-pulse')).toBeNull();
  });

  it('explains that export is off when nothing is configured and does not pulse', async () => {
    mockPosture(
      posture({
        status: 'noop',
        initialized: false,
        endpoint: null,
        exporter_type: 'none',
        sampler: null,
        metrics_exporting: false,
        headers_configured: false,
        last_success_at: null,
      }),
    );

    const { container } = render(<TelemetryPostureCard />);

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('Export is off.');
      expect(screen.getByText('Not configured')).toBeInTheDocument();
      expect(screen.getByText('No Git repository')).toBeInTheDocument();
    });
    expect(screen.queryByText('Delivery')).toBeNull();
    expect(container.querySelector('.animate-pulse')).toBeNull();
  });

  it('flags failed batches and the last failure when the collector rejects exports', async () => {
    mockPosture(
      posture({
        status: 'failing',
        exported_spans: 12,
        failed_batches: 3,
        withheld_spans: 0,
        last_success_at: null,
        last_failure_at: Date.now() / 1000 - 30,
      }),
    );

    const { container } = render(<TelemetryPostureCard />);

    await waitFor(() => {
      expect(screen.getByText('Failing')).toBeInTheDocument();
      expect(screen.getByRole('status')).toHaveTextContent('The last export attempt failed.');
      expect(screen.getByText('3')).toHaveClass('text-destructive');
      expect(screen.getByText('30 seconds ago')).toBeInTheDocument();
    });
    expect(container.querySelector('.animate-pulse')).toBeNull();
  });

  it('shows why the exporter could not start as configured', async () => {
    mockPosture(
      posture({
        status: 'degraded',
        initialized: false,
        exporter_type: 'none',
        degraded_reason: 'grpc exporter package is not installed',
      }),
    );

    render(<TelemetryPostureCard />);

    await waitFor(() => {
      expect(screen.getByText('Degraded')).toBeInTheDocument();
      expect(screen.getByRole('status')).toHaveTextContent(
        'Export could not start as configured: grpc exporter package is not installed',
      );
    });
    expect(screen.queryByText('Delivery')).toBeNull();
  });

  it('discloses when prompt and reply content is part of the exported spans', async () => {
    mockPosture(posture({ content_capture: true }));

    render(<TelemetryPostureCard />);

    await waitFor(() => {
      expect(screen.getByText('Included in spans (opt-in)')).toBeInTheDocument();
    });
    expect(screen.queryByText('Never exported (metadata only)')).toBeNull();
  });

  it('shows the kill switch as disabled', async () => {
    mockPosture(posture({ status: 'disabled', initialized: false, endpoint: null, exporter_type: 'none' }));

    render(<TelemetryPostureCard />);

    await waitFor(() => {
      expect(screen.getByText('Disabled')).toBeInTheDocument();
      expect(screen.getByRole('status')).toHaveTextContent('Export is switched off by OTEL_SDK_DISABLED.');
    });
  });

  it('renders the VCS branch and commit when available', async () => {
    mockPosture(posture({ git_branch: 'feature/item-12', git_commit: '7a8b9c0' }));

    render(<TelemetryPostureCard />);

    await waitFor(() => {
      expect(screen.getByText('feature/item-12')).toBeInTheDocument();
      expect(screen.getByText('(7a8b9c0)')).toBeInTheDocument();
    });
  });

  it('reports a probe error when the posture cannot be read', async () => {
    (systemService.getTelemetryPosture as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('network down'),
    );

    render(<TelemetryPostureCard />);

    await waitFor(() => {
      expect(screen.getByText('Probe error')).toBeInTheDocument();
      expect(screen.getByRole('status')).toHaveTextContent('The export status could not be read.');
    });
  });
});
