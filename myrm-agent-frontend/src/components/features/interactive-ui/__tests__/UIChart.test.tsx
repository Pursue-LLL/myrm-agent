/** @vitest-environment jsdom */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { UIChart } from '../components/UIChart';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}));

const makeProps = (overrides: Record<string, unknown> = {}) => ({
  id: 'chart-1',
  props: { type: 'bar' as const, ...overrides },
  bindings: { data: '$.items' },
  events: {},
  data: {
    items: [
      { label: 'A', value: 10 },
      { label: 'B', value: 20 },
      { label: 'C', value: 30 },
    ],
  },
  onDataChange: vi.fn(),
  onAction: vi.fn(),
});

describe('UIChart', () => {
  it('renders empty state when data is missing', () => {
    render(<UIChart {...makeProps()} data={{}} />);
    expect(screen.getByText('noData')).toBeInTheDocument();
  });

  // === Bar chart ===

  it('renders bar chart labels and values', () => {
    render(<UIChart {...makeProps()} />);
    expect(screen.getByText('A')).toBeInTheDocument();
    expect(screen.getByText('B')).toBeInTheDocument();
    expect(screen.getByText('C')).toBeInTheDocument();
    expect(screen.getByText('10')).toBeInTheDocument();
    expect(screen.getByText('20')).toBeInTheDocument();
    expect(screen.getByText('30')).toBeInTheDocument();
  });

  it('hides values when showValues is false', () => {
    render(<UIChart {...makeProps({ showValues: false })} />);
    expect(screen.queryByText('10')).not.toBeInTheDocument();
  });

  // === Pie chart — Bug #1: totalValue=0 NaN protection ===

  it('renders allZero message for pie chart when all values are 0', () => {
    render(
      <UIChart
        {...makeProps({ type: 'pie' })}
        data={{
          items: [
            { label: 'X', value: 0 },
            { label: 'Y', value: 0 },
          ],
        }}
      />,
    );
    expect(screen.getByText('allZero')).toBeInTheDocument();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('renders allZero message for donut chart when all values are 0', () => {
    render(<UIChart {...makeProps({ type: 'donut' })} data={{ items: [{ label: 'X', value: 0 }] }} />);
    expect(screen.getByText('allZero')).toBeInTheDocument();
  });

  it('renders pie chart normally when values are positive', () => {
    const { container } = render(
      <UIChart
        {...makeProps({ type: 'pie' })}
        data={{
          items: [
            { label: 'X', value: 50 },
            { label: 'Y', value: 50 },
          ],
        }}
      />,
    );
    const svg = container.querySelector('svg');
    expect(svg).toBeTruthy();
    const paths = svg!.querySelectorAll('path');
    expect(paths.length).toBe(2);
  });

  it('renders pie legend with correct percentages', () => {
    const { container } = render(
      <UIChart
        {...makeProps({ type: 'pie' })}
        data={{
          items: [
            { label: 'Half', value: 50 },
            { label: 'Other', value: 50 },
          ],
        }}
      />,
    );
    expect(screen.getByText('Half')).toBeInTheDocument();
    const legendSpans = container.querySelectorAll('.text-gray-500');
    const texts = Array.from(legendSpans).map((el) => el.textContent);
    expect(texts.some((t) => t?.includes('50.0%'))).toBe(true);
  });

  // === Line chart — Bug #2: data points use HTML divs (not SVG circles) to avoid deformation ===

  it('renders line chart with HTML data points instead of SVG circles', () => {
    const { container } = render(
      <UIChart
        {...makeProps({ type: 'line' })}
        data={{
          items: [
            { label: 'Jan', value: 10 },
            { label: 'Feb', value: 30 },
          ],
        }}
      />,
    );
    const svg = container.querySelector('svg');
    expect(svg).toBeTruthy();

    expect(svg!.querySelectorAll('circle').length).toBe(0);

    const dots = container.querySelectorAll('.rounded-full');
    expect(dots.length).toBe(2);
    dots.forEach((dot) => {
      const style = (dot as HTMLElement).style;
      expect(style.left).toMatch(/%$/);
      expect(style.top).toMatch(/%$/);
      expect(style.width).toBe('8px');
      expect(style.height).toBe('8px');
    });

    const path = svg!.querySelector('path');
    expect(path).toBeTruthy();
  });

  it('renders line chart x-axis labels', () => {
    render(
      <UIChart
        {...makeProps({ type: 'line' })}
        data={{
          items: [
            { label: 'Q1', value: 100 },
            { label: 'Q2', value: 200 },
          ],
        }}
      />,
    );
    expect(screen.getByText('Q1')).toBeInTheDocument();
    expect(screen.getByText('Q2')).toBeInTheDocument();
  });

  // === Title rendering ===

  it('renders title when provided', () => {
    render(<UIChart {...makeProps({ title: 'Revenue' })} />);
    expect(screen.getByText('Revenue')).toBeInTheDocument();
  });

  it('does not render title when not provided', () => {
    const { container } = render(<UIChart {...makeProps()} />);
    expect(container.querySelector('h4')).not.toBeInTheDocument();
  });

  // === Custom className ===

  it('applies custom className', () => {
    const { container } = render(<UIChart {...makeProps({ className: 'custom-class' })} />);
    expect(container.firstChild).toHaveClass('custom-class');
  });

  // === Data binding from props.data ===

  it('falls back to props.data when bindings are empty', () => {
    render(
      <UIChart
        id="chart-2"
        props={{
          type: 'bar',
          data: [{ label: 'Direct', value: 42 }],
        }}
        bindings={{}}
        events={{}}
        data={{}}
        onDataChange={vi.fn()}
        onAction={vi.fn()}
      />,
    );
    expect(screen.getByText('Direct')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  // === Pie chart: single item 100% renders correctly ===

  it('renders single-item pie chart with valid arc path', () => {
    const { container } = render(
      <UIChart {...makeProps({ type: 'pie' })} data={{ items: [{ label: 'Only', value: 100 }] }} />,
    );
    const svg = container.querySelector('svg');
    expect(svg).toBeTruthy();
    const paths = svg!.querySelectorAll('path');
    expect(paths.length).toBe(1);
    const d = paths[0].getAttribute('d')!;
    expect(d).not.toContain('NaN');
    const coords = d.match(/[\d.]+/g)!.map(Number);
    const hasDistinctPoints = coords.some((v, i) => i > 0 && Math.abs(v - coords[i - 1]) > 0.001);
    expect(hasDistinctPoints).toBe(true);
  });

  // === Single data point edge case (line chart division by zero) ===

  it('handles single data point in line chart without error', () => {
    const { container } = render(
      <UIChart {...makeProps({ type: 'line' })} data={{ items: [{ label: 'Only', value: 5 }] }} />,
    );
    const dots = container.querySelectorAll('.rounded-full');
    expect(dots.length).toBe(1);
  });
});
