/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import DeferredAppInitializers from '../deferred-app-initializers';

vi.mock('../deferred-mount', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div data-testid="deferred-mount">{children}</div>,
}));

vi.mock('../update-handoff-notifier', () => ({
  UpdateHandoffNotifier: () => <div data-testid="update-handoff-notifier" />,
}));

describe('DeferredAppInitializers Component', () => {
  it('renders deferred initializers including UpdateHandoffNotifier', () => {
    const { getByTestId } = render(<DeferredAppInitializers />);
    expect(getByTestId('deferred-mount')).toBeInTheDocument();
  });
});
