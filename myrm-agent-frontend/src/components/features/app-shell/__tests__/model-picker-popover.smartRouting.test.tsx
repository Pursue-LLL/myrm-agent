import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ModelPickerPopover from '../model-picker-popover';
import useProviderStore from '@/store/useProviderStore';

vi.mock('@/store/useOrgModelPolicyStore', () => ({
  useOrgModelPolicyStore: () => ({
    restricted: false,
    initialized: true,
    loadPolicy: vi.fn(),
    isModelAllowed: () => true,
  }),
}));

vi.mock('@/components/features/settings/model-service/ProviderIcon', () => ({
  default: () => <span data-testid="provider-icon" />,
}));

vi.mock('@/components/features/app-shell/capability-icons', () => ({
  default: () => null,
}));

vi.mock('@/services/llm-config', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/llm-config')>();
  return {
    ...actual,
    fetchModelCapabilitiesBatch: vi.fn().mockResolvedValue({}),
    fetchModelSwitchPreflight: vi.fn().mockResolvedValue({}),
  };
});

vi.mock('@/components/primitives/popover', () => ({
  Popover: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/components/primitives/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

function renderPopover(props: { isSmartRoutingAvailable?: boolean; onSelectSmartRouting?: () => void }) {
  return render(
    <ModelPickerPopover
      currentSelection={null}
      onSelect={vi.fn()}
      trigger={<button type="button">open</button>}
      {...props}
    />,
  );
}

describe('ModelPickerPopover smart routing entry', () => {
  beforeEach(() => {
    useProviderStore.setState({ providers: [] });
  });

  it('hides the entry unless the picker may offer it', () => {
    renderPopover({ isSmartRoutingAvailable: false });

    expect(screen.queryByTestId('smart-routing-option')).not.toBeInTheDocument();
  });

  it('shows the entry with a vector icon and selects smart routing on click', () => {
    const onSelectSmartRouting = vi.fn();
    renderPopover({ isSmartRoutingAvailable: true, onSelectSmartRouting });

    const entry = screen.getByTestId('smart-routing-option');
    expect(entry.querySelector('svg')).not.toBeNull();
    expect(entry.textContent).not.toMatch(/\p{Extended_Pictographic}/u);

    fireEvent.click(entry);
    expect(onSelectSmartRouting).toHaveBeenCalledTimes(1);
  });
});
