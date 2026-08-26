/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: API request utility)
 * zustand::create
 *
 * [OUTPUT]
 * useDesktopRecordingStore: Zustand store for Desktop Workflow Skill Recording Wizard.
 *
 * [POS]
 * Manages desktop workflow recording session state, event trace, synthesizer draft,
 * and publishing to local skills store.
 */

import { create } from 'zustand';
import { apiRequest } from '@/lib/api';

export type DesktopRecordingStatus = 'idle' | 'recording' | 'stopped' | 'synthesizing' | 'draft_ready' | 'published';

export interface DesktopRecordedStep {
  seq: number;
  action: string;
  app_name: string;
  bundle_id?: string | null;
  window_title: string;
  dref_id?: string | null;
  element_role?: string | null;
  element_title?: string | null;
  value?: string | null;
  is_password: boolean;
  modifiers?: string[];
  screenshot_b64?: string | null;
}

export interface SynthesizedStep {
  seq: number;
  description: string;
  action_type: string;
  target_app: string;
  tool_name: string;
  parameters: Record<string, string>;
  variables: string[];
}

export interface SynthesizedDraft {
  skill_name: string;
  description: string;
  triggers: string[];
  parameters: Array<{ name: string; type: string; description: string; default_value?: string }>;
  steps: SynthesizedStep[];
  markdown_content: string;
  tool_lifting_applied: boolean;
  created_at: number;
}

interface DesktopRecordingState {
  isOpen: boolean;
  status: DesktopRecordingStatus;
  sessionId: string | null;
  appScope: string;
  steps: DesktopRecordedStep[];
  draft: SynthesizedDraft | null;
  publishedSkillId: string | null;
  error: string | null;

  toggleDrawer: () => void;
  openDrawer: () => void;
  closeDrawer: () => void;
  startRecording: (appScope?: string) => Promise<void>;
  addEvent: (event: Omit<DesktopRecordedStep, 'seq'>) => Promise<void>;
  stopRecording: () => Promise<void>;
  synthesizeDraft: (skillName: string, description?: string) => Promise<void>;
  deleteStep: (seq: number) => void;
  updateDraftMarkdown: (content: string) => void;
  publishSkill: (skillName: string) => Promise<string | null>;
  reset: () => void;
}

export const useDesktopRecordingStore = create<DesktopRecordingState>((set, get) => ({
  isOpen: false,
  status: 'idle',
  sessionId: null,
  appScope: 'all',
  steps: [],
  draft: null,
  publishedSkillId: null,
  error: null,

  toggleDrawer: () => set((state) => ({ isOpen: !state.isOpen })),
  openDrawer: () => set({ isOpen: true }),
  closeDrawer: () => set({ isOpen: false }),

  startRecording: async (appScope = 'all') => {
    const sessionId = `rec_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
    set({ status: 'recording', sessionId, appScope, steps: [], draft: null, publishedSkillId: null, error: null });

    try {
      await apiRequest('/api/skills/desktop-recorder/start', {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId, app_scope: appScope }),
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to start desktop recording session';
      set({ error: msg, status: 'idle' });
    }
  },

  addEvent: async (eventData) => {
    const { sessionId, steps, status } = get();
    if (!sessionId || status !== 'recording') return;

    const nextSeq = steps.length + 1;
    const newStep: DesktopRecordedStep = { ...eventData, seq: nextSeq };
    set({ steps: [...steps, newStep] });

    try {
      await apiRequest('/api/skills/desktop-recorder/event', {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId, ...newStep }),
      });
    } catch (err: unknown) {
      console.warn('Failed to stream desktop recording event to backend:', err);
    }
  },

  stopRecording: async () => {
    const { sessionId } = get();
    if (!sessionId) return;

    set({ status: 'stopped' });
    try {
      await apiRequest('/api/skills/desktop-recorder/stop', {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId }),
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to stop desktop recording';
      set({ error: msg });
    }
  },

  synthesizeDraft: async (skillName: string, description = '') => {
    const { sessionId } = get();
    if (!sessionId) return;

    set({ status: 'synthesizing', error: null });
    try {
      const response = await apiRequest<SynthesizedDraft>('/api/skills/desktop-recorder/synthesize', {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId, skill_name: skillName, description }),
      });
      set({ draft: response, status: 'draft_ready' });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to synthesize skill from recording';
      set({ error: msg, status: 'stopped' });
    }
  },

  deleteStep: (seq: number) => {
    set((state) => {
      const updated = state.steps.filter((s) => s.seq !== seq).map((s, idx) => ({ ...s, seq: idx + 1 }));
      return { steps: updated };
    });
  },

  updateDraftMarkdown: (content: string) => {
    set((state) => {
      if (!state.draft) return state;
      return { draft: { ...state.draft, markdown_content: content } };
    });
  },

  publishSkill: async (skillName: string) => {
    const { sessionId, draft } = get();
    if (!sessionId || !draft) return null;

    try {
      const response = await apiRequest<{ skill_id: string; status: string }>(
        '/api/skills/desktop-recorder/publish',
        {
          method: 'POST',
          body: JSON.stringify({
            session_id: sessionId,
            skill_name: skillName,
            markdown_content: draft.markdown_content,
            description: draft.description,
          }),
        }
      );
      set({ status: 'published', publishedSkillId: response.skill_id });
      return response.skill_id;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to publish skill';
      set({ error: msg });
      return null;
    }
  },

  reset: () => {
    set({
      status: 'idle',
      sessionId: null,
      appScope: 'all',
      steps: [],
      draft: null,
      publishedSkillId: null,
      error: null,
    });
  },
}));

export default useDesktopRecordingStore;
