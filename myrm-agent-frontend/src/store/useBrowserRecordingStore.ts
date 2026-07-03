/**
 * [INPUT]
 * @/lib/api::getWsUrl, apiRequest (POS: API base URL and request utilities)
 *
 * [OUTPUT]
 * useBrowserRecordingStore: Zustand store for Browser Recording panel state.
 *
 * [POS]
 * State management for the Browser Skill Recording Wizard. Manages WebSocket
 * connection lifecycle, recorded steps, session state, and skill generation.
 */

import { create } from 'zustand';
import { apiRequest, getWsUrl } from '@/lib/api';

type RecordingStatus = 'idle' | 'recording' | 'paused' | 'stopped' | 'generating';

interface RecordedStep {
  seq: number;
  action: string;
  selector: string;
  value: string;
  url: string;
  title: string;
  timestamp: number;
  elementText: string;
  elementRole: string;
  isPassword: boolean;
  screenshotB64?: string;
}

interface GeneratedSkill {
  skillId: string;
  skillName: string;
  description: string;
  stepCount: number;
  credentialPlaceholders: string[];
}

interface BrowserRecordingState {
  isOpen: boolean;
  status: RecordingStatus;
  sessionId: string | null;
  steps: RecordedStep[];
  generatedSkill: GeneratedSkill | null;
  error: string | null;

  togglePanel: () => void;
  openPanel: () => void;
  closePanel: () => void;
  startRecording: (url?: string) => void;
  stopRecording: () => void;
  pauseRecording: () => void;
  resumeRecording: () => void;
  deleteStep: (seq: number) => void;
  generateSkill: (skillName: string, description?: string) => Promise<void>;
  reset: () => void;
}

let ws: WebSocket | null = null;

const useBrowserRecordingStore = create<BrowserRecordingState>((set, get) => ({
  isOpen: false,
  status: 'idle',
  sessionId: null,
  steps: [],
  generatedSkill: null,
  error: null,

  togglePanel: () => set((s) => ({ isOpen: !s.isOpen })),
  openPanel: () => set({ isOpen: true }),
  closePanel: () => set({ isOpen: false }),

  startRecording: (url?: string) => {
    const wsUrl = getWsUrl('/api/v1/browser/ws/recording');
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      ws?.send(JSON.stringify({ type: 'start', url: url || '' }));
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        switch (msg.type) {
          case 'session_started':
            set({ sessionId: msg.session_id, status: 'recording', steps: [], error: null });
            break;
          case 'step':
            set((s) => ({
              steps: [
                ...s.steps,
                {
                  seq: msg.seq,
                  action: msg.action,
                  selector: msg.selector,
                  value: msg.value ?? '',
                  url: msg.url ?? '',
                  title: msg.title ?? '',
                  timestamp: msg.timestamp ?? 0,
                  elementText: msg.element_text ?? '',
                  elementRole: msg.element_role ?? '',
                  isPassword: msg.is_password ?? false,
                  screenshotB64: msg.screenshot_b64,
                },
              ],
            }));
            break;
          case 'session_stopped':
            set({ status: 'stopped' });
            break;
          case 'paused':
            set({ status: 'paused' });
            break;
          case 'resumed':
            set({ status: 'recording' });
            break;
          case 'step_deleted': {
            const deletedSeq = msg.seq;
            set((s) => ({ steps: s.steps.filter((step) => step.seq !== deletedSeq) }));
            break;
          }
          case 'error':
            set({ error: msg.message });
            break;
        }
      } catch {
        // ignore parse errors
      }
    };

    ws.onclose = () => {
      const { status } = get();
      if (status === 'recording' || status === 'paused') {
        set({ status: 'stopped' });
      }
    };

    ws.onerror = () => {
      set({ error: 'WebSocket connection failed', status: 'idle' });
    };

    set({ status: 'recording', steps: [], error: null, generatedSkill: null });
  },

  stopRecording: () => {
    ws?.send(JSON.stringify({ type: 'stop' }));
  },

  pauseRecording: () => {
    ws?.send(JSON.stringify({ type: 'pause' }));
  },

  resumeRecording: () => {
    ws?.send(JSON.stringify({ type: 'resume' }));
  },

  deleteStep: (seq: number) => {
    ws?.send(JSON.stringify({ type: 'delete_step', seq }));
  },

  generateSkill: async (skillName: string, description?: string) => {
    const { sessionId } = get();
    if (!sessionId) return;

    set({ status: 'generating', error: null });

    try {
      const result = await apiRequest<{
        skill_id: string;
        skill_name: string;
        description: string;
        step_count: number;
        credential_placeholders: string[];
      }>('/api/v1/browser/recording/generate-skill', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          skill_name: skillName,
          description: description || '',
        }),
      });

      set({
        generatedSkill: {
          skillId: result.skill_id,
          skillName: result.skill_name,
          description: result.description,
          stepCount: result.step_count,
          credentialPlaceholders: result.credential_placeholders,
        },
        status: 'stopped',
      });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : 'Skill generation failed', status: 'stopped' });
    }
  },

  reset: () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.close();
    }
    ws = null;
    set({
      status: 'idle',
      sessionId: null,
      steps: [],
      generatedSkill: null,
      error: null,
    });
  },
}));

export default useBrowserRecordingStore;
export type { RecordedStep, GeneratedSkill, RecordingStatus };
