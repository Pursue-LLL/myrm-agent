import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { mockIsMobile, renderIndicator, resetIndicatorKit } from './contextUsageIndicatorKit';

// jsdom does no layout, so each contract is asserted through the classes that produce it.
describe('ContextUsageIndicator panel layout', () => {
  beforeEach(resetIndicatorKit);

  async function openPanelContainer(): Promise<HTMLElement> {
    await userEvent.setup().click(screen.getByRole('status'));
    const panel = await screen.findByTestId('context-usage-panel');
    const container = panel.closest<HTMLElement>('[role="dialog"]');
    if (!container) {
      throw new Error('the strategy panel is not inside a dialog');
    }
    return container;
  }

  it('gives the desktop popover a fixed width, so its longest unwrapped line cannot stretch it', async () => {
    renderIndicator();

    const popover = await openPanelContainer();

    expect(popover).toHaveClass('w-80');
    expect(popover).not.toHaveClass('w-auto');
  });

  it('caps the desktop popover at the room above the ring and scrolls inside it, so a short window cannot push the top out of reach', async () => {
    renderIndicator();

    const popover = await openPanelContainer();

    expect(popover).toHaveClass('max-h-[var(--radix-popover-content-available-height)]', 'overflow-y-auto');
  });

  it('lets the phone sheet scroll, so a panel taller than the sheet keeps its compress control reachable', async () => {
    mockIsMobile.value = true;
    renderIndicator();

    const sheet = await openPanelContainer();

    expect(sheet).toHaveClass('overflow-y-auto', 'max-h-[85vh]');
  });
});
