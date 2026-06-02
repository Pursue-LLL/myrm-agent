import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import UIComponentErrorBoundary from '../UIComponentErrorBoundary';

function ThrowError({ error }: { error: Error }): React.ReactNode {
  throw error;
}

describe('UIComponentErrorBoundary', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  it('renders children normally when no error', () => {
    render(
      <UIComponentErrorBoundary componentType="text" componentId="test-1">
        <div data-testid="child">Hello</div>
      </UIComponentErrorBoundary>,
    );
    expect(screen.getByTestId('child')).toBeInTheDocument();
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });

  it('catches render error and shows fallback with component type', () => {
    render(
      <UIComponentErrorBoundary componentType="chart" componentId="chart-1">
        <ThrowError error={new Error('data is not iterable')} />
      </UIComponentErrorBoundary>,
    );
    expect(screen.getByText(/Component "chart" render failed/)).toBeInTheDocument();
    expect(screen.getByText(/data is not iterable/)).toBeInTheDocument();
  });

  it('does not crash sibling components when one child throws', () => {
    render(
      <div>
        <UIComponentErrorBoundary componentType="table" componentId="tbl-1">
          <ThrowError error={new Error('crash')} />
        </UIComponentErrorBoundary>
        <div data-testid="sibling">Still alive</div>
      </div>,
    );
    expect(screen.getByTestId('sibling')).toBeInTheDocument();
    expect(screen.getByText('Still alive')).toBeInTheDocument();
    expect(screen.getByText(/Component "table" render failed/)).toBeInTheDocument();
  });

  it('logs error with component type and id via componentDidCatch', () => {
    vi.restoreAllMocks();
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <UIComponentErrorBoundary componentType="select" componentId="sel-42">
        <ThrowError error={new Error('boom')} />
      </UIComponentErrorBoundary>,
    );

    const loggedCall = consoleSpy.mock.calls.find(
      (call) => typeof call[0] === 'string' && call[0].includes('[InteractiveUI]'),
    );
    expect(loggedCall).toBeDefined();
    expect(loggedCall![0]).toContain('select');
    expect(loggedCall![0]).toContain('sel-42');
  });

  it('shows fallback without error message when error.message is empty', () => {
    const emptyError = new Error('');

    render(
      <UIComponentErrorBoundary componentType="slider" componentId="s-1">
        <ThrowError error={emptyError} />
      </UIComponentErrorBoundary>,
    );

    expect(screen.getByText(/Component "slider" render failed/)).toBeInTheDocument();
  });

  it('resets error state when key changes (via React reconciliation)', () => {
    const { rerender } = render(
      <UIComponentErrorBoundary key="v1" componentType="text" componentId="t-1">
        <ThrowError error={new Error('v1 error')} />
      </UIComponentErrorBoundary>,
    );

    expect(screen.getByText(/render failed/)).toBeInTheDocument();

    rerender(
      <UIComponentErrorBoundary key="v2" componentType="text" componentId="t-1">
        <div data-testid="recovered">OK</div>
      </UIComponentErrorBoundary>,
    );

    expect(screen.getByTestId('recovered')).toBeInTheDocument();
    expect(screen.queryByText(/render failed/)).not.toBeInTheDocument();
  });

  it('isolates errors between multiple ErrorBoundary instances', () => {
    render(
      <div>
        <UIComponentErrorBoundary componentType="chart" componentId="chart-err">
          <ThrowError error={new Error('chart crash')} />
        </UIComponentErrorBoundary>
        <UIComponentErrorBoundary componentType="table" componentId="tbl-ok">
          <div data-testid="table-content">Table renders fine</div>
        </UIComponentErrorBoundary>
        <UIComponentErrorBoundary componentType="select" componentId="sel-err">
          <ThrowError error={new Error('select crash')} />
        </UIComponentErrorBoundary>
      </div>,
    );

    expect(screen.getByText(/Component "chart" render failed/)).toBeInTheDocument();
    expect(screen.getByTestId('table-content')).toBeInTheDocument();
    expect(screen.getByText(/Component "select" render failed/)).toBeInTheDocument();
  });

  it('displays error message containing special characters', () => {
    render(
      <UIComponentErrorBoundary componentType="text" componentId="t-special">
        <ThrowError error={new Error('Cannot read properties of undefined (reading "map")')} />
      </UIComponentErrorBoundary>,
    );
    expect(screen.getByText(/Cannot read properties of undefined/)).toBeInTheDocument();
  });
});
