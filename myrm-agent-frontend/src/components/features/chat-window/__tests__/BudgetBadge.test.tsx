import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { deferred } from '@/test-utils/deferred';
import type { BudgetStatus } from '@/services/budget';
import BudgetBadge from '../BudgetBadge';

const kit = vi.hoisted(() => ({
  /** Keys with their values appended, so the tooltip shows what it was filled with. */
  t: (key: string, values?: Record<string, string>) => (values ? `${key}|${Object.values(values).join(',')}` : key),
  getBudgetStatus: vi.fn<() => Promise<BudgetStatus>>(),
}));

vi.mock('next-intl', () => ({ useTranslations: () => kit.t }));
vi.mock('@/services/budget', () => ({ getBudgetStatus: kit.getBudgetStatus }));

const budget = (overrides: Partial<BudgetStatus> = {}): BudgetStatus => ({
  enabled: true,
  daily_limit_usd: 10,
  session_limit_usd: 2,
  today_cost_usd: 1.23456,
  session_cost_usd: 0.1,
  remaining_usd: 8.76544,
  usage_pct: 12.3,
  status: 'ok',
  ...overrides,
});

async function mount() {
  const view = render(<BudgetBadge />);
  await act(async () => undefined);
  return view;
}

const announce = (event: string) => act(async () => void window.dispatchEvent(new Event(event)));
const badge = (container: HTMLElement) => container.firstElementChild;

beforeEach(() => {
  kit.getBudgetStatus.mockResolvedValue(budget());
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('BudgetBadge visibility', () => {
  it('shows nothing until the budget is known', () => {
    kit.getBudgetStatus.mockReturnValue(new Promise(() => undefined));
    const { container } = render(<BudgetBadge />);

    expect(container).toBeEmptyDOMElement();
  });

  it.each([
    ['budget control is off', { enabled: false }],
    ['the budget is reported as disabled', { status: 'disabled' as const }],
  ])('shows nothing when %s', async (_why, overrides) => {
    kit.getBudgetStatus.mockResolvedValue(budget(overrides));
    const { container } = await mount();

    expect(container).toBeEmptyDOMElement();
  });

  it('shows nothing when the budget cannot be read', async () => {
    kit.getBudgetStatus.mockRejectedValue(new Error('offline'));
    const { container } = await mount();

    expect(container).toBeEmptyDOMElement();
  });
});

describe('BudgetBadge reading', () => {
  it.each([
    [12.3, '12%'],
    [12.5, '13%'],
    [99.6, '100%'],
    [0, '0%'],
  ])('rounds %s percent used to %s', async (usage, text) => {
    kit.getBudgetStatus.mockResolvedValue(budget({ usage_pct: usage }));
    await mount();

    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it('tells session and daily spending, to four decimals, in the user language', async () => {
    const { container } = await mount();

    expect(badge(container)).toHaveAttribute('title', 'budgetCostSummary|0.1000,1.2346');
  });

  it.each([
    ['ok', 'text-muted-foreground'],
    ['warning', 'text-amber-500'],
    ['finalization', 'text-orange-500'],
    ['exceeded', 'text-red-500'],
  ] as const)('is coloured for the %s status', async (status, colour) => {
    kit.getBudgetStatus.mockResolvedValue(budget({ status }));
    const { container } = await mount();

    expect(badge(container)).toHaveClass(colour);
  });

  it('shows a credit card and no eco message while the budget is fine', async () => {
    const { container } = await mount();

    expect(container.querySelector('.text-green-500')).toBeNull();
    expect(badge(container)).toHaveAttribute('title', expect.not.stringContaining('ecoModeActive'));
  });

  it.each([['warning'], ['finalization'], ['exceeded']] as const)(
    'shows the eco shield and says so in the tooltip for the %s status',
    async (status) => {
      kit.getBudgetStatus.mockResolvedValue(budget({ status }));
      const { container } = await mount();

      expect(container.querySelector('.text-green-500')).not.toBeNull();
      expect(badge(container)).toHaveAttribute('title', 'ecoModeActive\nbudgetCostSummary|0.1000,1.2346');
    },
  );
});

describe('BudgetBadge keeping up', () => {
  it('reads the budget when it appears', async () => {
    await mount();

    expect(kit.getBudgetStatus).toHaveBeenCalledTimes(1);
  });

  it.each([['budget_updated'], ['budget_alert']])('reads it again on %s', async (event) => {
    const { container } = await mount();
    kit.getBudgetStatus.mockResolvedValue(budget({ usage_pct: 55, status: 'warning' }));

    await announce(event);

    expect(screen.getByText('55%')).toBeInTheDocument();
    expect(badge(container)).toHaveClass('text-amber-500');
  });

  it('goes away when a later read fails', async () => {
    const { container } = await mount();
    kit.getBudgetStatus.mockRejectedValue(new Error('offline'));

    await announce('budget_updated');

    expect(container).toBeEmptyDOMElement();
  });

  it('stops listening when it goes away', async () => {
    const { unmount } = await mount();
    unmount();
    kit.getBudgetStatus.mockClear();

    await announce('budget_updated');
    await announce('budget_alert');

    expect(kit.getBudgetStatus).not.toHaveBeenCalled();
  });

  it('keeps the newest reading when an older read finishes last', async () => {
    const older = deferred<BudgetStatus>();
    kit.getBudgetStatus.mockReturnValueOnce(older.promise);
    render(<BudgetBadge />);
    kit.getBudgetStatus.mockResolvedValue(budget({ usage_pct: 80 }));
    await announce('budget_updated');

    await act(async () => older.resolve(budget({ usage_pct: 20 })));

    expect(screen.getByText('80%')).toBeInTheDocument();
  });
});
