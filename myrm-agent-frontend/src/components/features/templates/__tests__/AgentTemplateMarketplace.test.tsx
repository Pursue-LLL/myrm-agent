/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { AgentTemplateMarketplace } from '../AgentTemplateMarketplace';
import { useTemplateMarketplaceStore } from '../useTemplateMarketplaceStore';

describe('AgentTemplateMarketplace refresh control', () => {
  const fetchTemplates = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    fetchTemplates.mockClear();
    useTemplateMarketplaceStore.setState({
      templates: [],
      isLoading: false,
      error: null,
      searchQuery: '',
      selectedCategory: 'all',
      fetchTemplates,
    });
  });

  it('labels the refresh button from translations and refetches on click', () => {
    render(<AgentTemplateMarketplace />);
    fetchTemplates.mockClear();

    fireEvent.click(screen.getByRole('button', { name: 'refresh' }));

    expect(fetchTemplates).toHaveBeenCalledTimes(1);
  });
});
