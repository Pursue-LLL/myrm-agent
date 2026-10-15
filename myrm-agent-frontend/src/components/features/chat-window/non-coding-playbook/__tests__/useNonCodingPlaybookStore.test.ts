import { describe, it, expect, beforeEach } from 'vitest';
import { useNonCodingPlaybookStore } from '../useNonCodingPlaybookStore';

describe('useNonCodingPlaybookStore', () => {
  beforeEach(() => {
    useNonCodingPlaybookStore.getState().reset();
  });

  it('initializes with 6 preset scenarios and default filter all', () => {
    const state = useNonCodingPlaybookStore.getState();
    expect(state.scenarios.length).toBe(6);
    expect(state.selectedCategory).toBe('all');
    expect(state.searchKeyword).toBe('');
    expect(state.activeScenarioModal).toBeNull();
    expect(state.isComparisonModalOpen).toBe(false);
  });

  it('sets selected category and search keyword', () => {
    const store = useNonCodingPlaybookStore.getState();
    store.setSelectedCategory('legal');
    expect(useNonCodingPlaybookStore.getState().selectedCategory).toBe('legal');

    store.setSearchKeyword('发票');
    expect(useNonCodingPlaybookStore.getState().searchKeyword).toBe('发票');
  });

  it('opens scenario modal and automatically prefills default form values', () => {
    const store = useNonCodingPlaybookStore.getState();
    const invoiceScenario = store.scenarios[0];
    expect(invoiceScenario).toBeDefined();

    if (invoiceScenario) {
      store.openScenarioModal(invoiceScenario);
      const state = useNonCodingPlaybookStore.getState();
      expect(state.activeScenarioModal?.id).toBe(invoiceScenario.id);
      expect(state.formValues['invoice_path']).toBe('./invoices');
      expect(state.formValues['company_title']).toBe('开放智能科技有限公司');
    }
  });

  it('updates form fields and closes scenario modal', () => {
    const store = useNonCodingPlaybookStore.getState();
    const invoiceScenario = store.scenarios[0];

    if (invoiceScenario) {
      store.openScenarioModal(invoiceScenario);
      store.updateFormField('invoice_path', '/custom/invoices');
      expect(
        useNonCodingPlaybookStore.getState().formValues['invoice_path'],
      ).toBe('/custom/invoices');

      store.closeScenarioModal();
      const state = useNonCodingPlaybookStore.getState();
      expect(state.activeScenarioModal).toBeNull();
      expect(state.formValues).toEqual({});
    }
  });

  it('toggles comparison modal state', () => {
    const store = useNonCodingPlaybookStore.getState();
    store.toggleComparisonModal(true);
    expect(useNonCodingPlaybookStore.getState().isComparisonModalOpen).toBe(
      true,
    );

    store.toggleComparisonModal(false);
    expect(useNonCodingPlaybookStore.getState().isComparisonModalOpen).toBe(
      false,
    );
  });
});
