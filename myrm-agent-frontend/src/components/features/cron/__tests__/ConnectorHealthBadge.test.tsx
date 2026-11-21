/** @vitest-environment jsdom */
import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ConnectorHealthBadge from '../ConnectorHealthBadge';
import { getConnectorsHealth } from '@/services/cron';
import type { ConnectorHealthItem, ConnectorsHealthListResponse, CronJob } from '@/services/cron';

vi.mock('@/components/primitives/popover', () => ({
  Popover: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const stableT = (key: string, values?: Record<string, unknown>) =>
  values ? `${key}:${Object.values(values).join(',')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('@/services/cron', () => ({
  getConnectorsHealth: vi.fn(),
}));

type BadgeJob = Pick<CronJob, 'id' | 'delivery' | 'last_run_at'>;

const JOB: BadgeJob = {
  id: 'job-1',
  delivery: { channel: 'webhook', target: 'https://hooks.example.com/a' },
  last_run_at: '2026-06-17T08:30:00Z',
};

function item(overrides: Partial<ConnectorHealthItem> = {}): ConnectorHealthItem {
  return {
    target: 'https://hooks.example.com/a',
    channel: 'webhook',
    status: 'healthy',
    total_deliveries: 4,
    failed_deliveries: 0,
    consecutive_failures: 0,
    bound_job_ids: ['job-1'],
    ...overrides,
  };
}

function response(...items: ConnectorHealthItem[]): ConnectorsHealthListResponse {
  return { items, total: items.length, degraded_count: 0, down_count: 0 };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe('ConnectorHealthBadge', () => {
  const healthMock = vi.mocked(getConnectorsHealth);

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows nothing until the destination has been judged', () => {
    healthMock.mockReturnValue(new Promise(() => undefined));

    const { container } = render(<ConnectorHealthBadge job={JOB} />);

    expect(container).toBeEmptyDOMElement();
  });

  it.each([
    ['another job delivers there', response(item({ bound_job_ids: ['job-2'] }))],
    ['nothing has been delivered yet', response(item({ total_deliveries: 0 }))],
    ['the destination is not an outbound one', response()],
  ])('shows nothing when %s', async (_case, answer) => {
    healthMock.mockResolvedValue(answer);

    const { container } = render(<ConnectorHealthBadge job={JOB} />);
    await act(async () => undefined);

    expect(healthMock).toHaveBeenCalledTimes(1);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows a healthy destination as a plain pill with nothing to explain', async () => {
    healthMock.mockResolvedValue(response(item()));

    render(<ConnectorHealthBadge job={JOB} />);

    expect(await screen.findByTestId('connector-health-badge')).toHaveTextContent('connectorStatusHealthy');
    expect(screen.getByText(/connectorHealthStatus/)).toHaveClass('sr-only');
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it.each([
    ['degraded', 'connectorStatusDegraded'],
    ['down', 'connectorStatusDown'],
  ] as const)('explains a %s destination: the streak, why and when', async (status, label) => {
    healthMock.mockResolvedValue(
      response(
        item({
          status,
          consecutive_failures: 3,
          failed_deliveries: 3,
          last_error_category: 'timeout',
          last_error_message: 'ReadTimeout',
          last_failed_at: '2026-06-17T08:30:00Z',
        }),
      ),
    );

    render(<ConnectorHealthBadge job={JOB} />);

    // The name is the hidden prefix plus the verdict; spacing between the two depends on layout, which jsdom lacks.
    const pill = await screen.findByRole('button', { name: new RegExp(`^connectorHealthStatus:\\s*${label}$`) });
    expect(pill).toHaveTextContent(label);
    expect(screen.getByText('connectorFailureStreak:3')).toBeInTheDocument();
    expect(screen.getByText('connectorCategoryTimeout')).toBeInTheDocument();
    expect(screen.getByText('ReadTimeout')).toBeInTheDocument();
    expect(screen.getByText(/^connectorLastFailedAt:.*2026/)).toBeInTheDocument();
  });

  it('words a category the server is not known to record as unknown', async () => {
    healthMock.mockResolvedValue(
      response(item({ status: 'degraded', consecutive_failures: 1, last_error_category: 'brand_new_category' })),
    );

    render(<ConnectorHealthBadge job={JOB} />);

    expect(await screen.findByText('connectorCategoryUnknown')).toBeInTheDocument();
  });

  it('shows nothing when the verdict cannot be loaded', async () => {
    healthMock.mockRejectedValue(new Error('offline'));

    const { container } = render(<ConnectorHealthBadge job={JOB} />);
    await act(async () => undefined);

    expect(healthMock).toHaveBeenCalledTimes(1);
    expect(container).toBeEmptyDOMElement();
  });

  it('reloads after the job has run again', async () => {
    healthMock.mockResolvedValue(response(item()));

    const { rerender } = render(<ConnectorHealthBadge job={JOB} />);
    await screen.findByTestId('connector-health-badge');
    rerender(<ConnectorHealthBadge job={{ ...JOB, last_run_at: '2026-06-17T09:30:00Z' }} />);

    await waitFor(() => expect(healthMock).toHaveBeenCalledTimes(2));
  });

  it('judges the new destination when the job is pointed elsewhere and drops the answer for the old one', async () => {
    const earlier = deferred<ConnectorsHealthListResponse>();
    healthMock
      .mockReturnValueOnce(earlier.promise)
      .mockResolvedValueOnce(response(item({ status: 'down', consecutive_failures: 3 })));

    const { rerender } = render(<ConnectorHealthBadge job={JOB} />);
    rerender(
      <ConnectorHealthBadge job={{ ...JOB, delivery: { channel: 'webhook', target: 'https://hooks.example.com/b' } }} />,
    );
    expect(await screen.findByRole('button')).toHaveTextContent('connectorStatusDown');

    await act(async () => {
      earlier.resolve(response(item({ status: 'healthy' })));
    });

    expect(screen.getByRole('button')).toHaveTextContent('connectorStatusDown');
    expect(healthMock).toHaveBeenCalledTimes(2);
  });
});
