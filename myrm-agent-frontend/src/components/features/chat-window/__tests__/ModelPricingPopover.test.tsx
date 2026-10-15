// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ModelPricingPopover } from '../ModelPricingPopover';
import { fetchModelPricing, type ModelPricingItem } from '@/services/pricing';

// 带参数回显：同时验证翻译键与插值参数
const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key}:${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/pricing', () => ({
  fetchModelPricing: vi.fn(),
}));

const priceItem = (model: string, overrides: Partial<ModelPricingItem> = {}): ModelPricingItem => ({
  model,
  input_cost_per_mtoken: 3,
  output_cost_per_mtoken: 15,
  cache_read_cost_per_mtoken: 0.3,
  cache_write_cost_per_mtoken: 3.75,
  cache_read_discount: 0.9,
  supports_prompt_caching: true,
  ...overrides,
});

const openPopover = () => {
  render(
    <ModelPricingPopover currentModel="model-a">
      <button type="button">trigger</button>
    </ModelPricingPopover>,
  );
  fireEvent.click(screen.getByText('trigger'));
};

describe('ModelPricingPopover', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the translated loading state until pricing arrives', async () => {
    vi.mocked(fetchModelPricing).mockReturnValue(new Promise(() => undefined));

    openPopover();

    expect(await screen.findByText('title')).toBeDefined();
    expect(screen.getByText('sourceBadge')).toBeDefined();
    expect(screen.getByText('loading')).toBeDefined();
  });

  it('renders the active model card and the comparison list through translation keys', async () => {
    vi.mocked(fetchModelPricing).mockResolvedValue({
      models: { 'model-a': priceItem('model-a'), 'model-b': priceItem('model-b', { input_cost_per_mtoken: 1.5 }) },
    });

    openPopover();

    await waitFor(() => expect(screen.getByText('supportsCache')).toBeDefined());
    for (const key of ['inputPrice', 'outputPrice', 'cacheReadPrice', 'savings', 'compareTitle', 'footnote']) {
      expect(screen.getByText(key)).toBeDefined();
    }
    expect(screen.getByText('inPrice:{"price":"$1.50"}')).toBeDefined();
    expect(screen.getByText('outPrice:{"price":"$15.00"}')).toBeDefined();
    expect(screen.getByText('90%')).toBeDefined();
  });
});
