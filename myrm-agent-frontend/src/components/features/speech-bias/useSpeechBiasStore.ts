import { create } from 'zustand';
import {
  CorrectionRecord,
  DevTermCategory,
  DevTermItem,
  DictationStatus,
  SpeechBiasState,
} from './speechBiasTypes';
import {
  DEFAULT_DEV_LEXICON,
  correctSpeechTranscript,
  extractContextTerms,
  ContextExtractionInput,
} from './speechBiasEngine';

export interface SpeechBiasActions {
  startListening: () => void;
  appendTranscriptChunk: (chunk: string) => void;
  finalizeTranscript: (rawText?: string) => void;
  injectContextTerms: (input: ContextExtractionInput) => void;
  addCustomTerm: (term: string, aliases: string[], category?: DevTermCategory) => void;
  removeTerm: (id: string) => void;
  toggleAutoCorrect: (enabled?: boolean) => void;
  setDrawerOpen: (open: boolean) => void;
  revertCorrection: (correctionId: string) => void;
  reset: () => void;
}

export type SpeechBiasStore = SpeechBiasState & SpeechBiasActions;

const INITIAL_STATE: SpeechBiasState = {
  status: 'idle',
  rawTranscript: '',
  correctedTranscript: '',
  activeCorrections: [],
  lexicon: DEFAULT_DEV_LEXICON,
  isAutoCorrectEnabled: true,
  isDrawerOpen: false,
  activeBranchName: '',
  recentAstSymbols: [],
  installedSkills: [],
  lastError: null,
};

export const useSpeechBiasStore = create<SpeechBiasStore>((set, get) => ({
  ...INITIAL_STATE,

  startListening: () => {
    set({
      status: 'listening',
      rawTranscript: '',
      correctedTranscript: '',
      activeCorrections: [],
      lastError: null,
    });
  },

  appendTranscriptChunk: (chunk: string) => {
    const current = get().rawTranscript;
    const updated = current ? `${current} ${chunk}` : chunk;
    set({ rawTranscript: updated });
  },

  finalizeTranscript: (overrideRaw?: string) => {
    const raw = overrideRaw !== undefined ? overrideRaw : get().rawTranscript;
    const { lexicon, isAutoCorrectEnabled } = get();

    if (!raw || raw.trim() === '') {
      set({
        status: 'idle',
        rawTranscript: '',
        correctedTranscript: '',
        activeCorrections: [],
      });
      return;
    }

    set({ status: 'correcting' });

    if (!isAutoCorrectEnabled) {
      set({
        status: 'ready',
        rawTranscript: raw,
        correctedTranscript: raw,
        activeCorrections: [],
      });
      return;
    }

    const result = correctSpeechTranscript(raw, lexicon);

    set({
      status: 'ready',
      rawTranscript: raw,
      correctedTranscript: result.correctedText,
      activeCorrections: result.corrections,
    });
  },

  injectContextTerms: (input: ContextExtractionInput) => {
    const extracted = extractContextTerms(input);
    const existing = get().lexicon;

    // 按 id 或 term 查重合并
    const existingTermSet = new Set(existing.map((item) => item.term.toLowerCase()));
    const newItems = extracted.filter((item) => !existingTermSet.has(item.term.toLowerCase()));

    set({
      lexicon: [...existing, ...newItems],
      activeBranchName: input.branch || get().activeBranchName,
      recentAstSymbols: input.astSymbols || get().recentAstSymbols,
      installedSkills: input.skills || get().installedSkills,
    });
  },

  addCustomTerm: (term: string, aliases: string[], category: DevTermCategory = 'custom') => {
    const trimmed = term.trim();
    if (!trimmed) {
      return;
    }

    const newItem: DevTermItem = {
      id: `custom-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`,
      term: trimmed,
      aliases: aliases.map((a) => a.trim()).filter((a) => a.length > 0),
      category,
      weight: 10,
      source: 'User Custom',
    };

    set((state) => ({
      lexicon: [newItem, ...state.lexicon],
    }));
  },

  removeTerm: (id: string) => {
    set((state) => ({
      lexicon: state.lexicon.filter((item) => item.id !== id),
    }));
  },

  toggleAutoCorrect: (enabled?: boolean) => {
    set((state) => ({
      isAutoCorrectEnabled: enabled !== undefined ? enabled : !state.isAutoCorrectEnabled,
    }));
  },

  setDrawerOpen: (open: boolean) => {
    set({ isDrawerOpen: open });
  },

  revertCorrection: (correctionId: string) => {
    const target = get().activeCorrections.find((c) => c.id === correctionId);
    if (!target) {
      return;
    }

    const currentText = get().correctedTranscript;
    // 将纠偏词逆向替换回原词
    const revertedText = currentText.replace(target.corrected, target.original);

    set((state) => ({
      correctedTranscript: revertedText,
      activeCorrections: state.activeCorrections.filter((c) => c.id !== correctionId),
    }));
  },

  reset: () => {
    set(INITIAL_STATE);
  },
}));
