import { create } from 'zustand';

export interface QuoteData {
  sourceMessageId: string;
  quotedText: string;
}

interface QuoteState {
  quote: QuoteData | null;
  setQuote: (quote: QuoteData) => void;
  clearQuote: () => void;
}

const useQuoteStore = create<QuoteState>((set) => ({
  quote: null,
  setQuote: (quote) => set({ quote }),
  clearQuote: () => set({ quote: null }),
}));

export default useQuoteStore;
