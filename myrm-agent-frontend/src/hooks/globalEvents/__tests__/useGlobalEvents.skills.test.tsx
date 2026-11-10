import { describe, expect, it, vi } from 'vitest';
import {
  emit,
  installGlobalEventsLifecycle,
  mocks,
  mountGlobalEvents,
  recordWindowEvents,
  toastMessage,
  toastOptions,
} from './globalEventsTestKit';

describe('useGlobalEvents: skill and system notices', () => {
  installGlobalEventsLifecycle();

  describe('skills', () => {
    it('new_skill_draft offers the draft review and announces the draft', () => {
      mountGlobalEvents();
      const events = recordWindowEvents();

      emit('new_skill_draft', { name: 'Docx', draft_id: 'd1', draft_type: 'skill' });

      expect(toastMessage(mocks.toast.info)).toBe('newSkillDraft');
      expect(toastOptions(mocks.toast.info)).toMatchObject({ duration: 8_000, dismissible: true });
      toastOptions(mocks.toast.info).action?.onClick();
      expect(mocks.router.push).toHaveBeenCalledWith('/settings/evolutionPending');
      expect(events()).toEqual([
        { type: 'skill-draft-created', detail: { draftId: 'd1', name: 'Docx', draftType: 'skill' } },
      ]);
    });

    it.each([
      ['FAILED_SCAN', 'error', 'skillGrowthFailedScan'],
      ['BLOCKED_LOCKED', 'warning', 'skillGrowthBlockedLocked'],
    ] as const)('skill_growth_updated %s raises a %s toast and relays the update', (status, level, message) => {
      mountGlobalEvents();
      const events = recordWindowEvents();

      emit('skill_growth_updated', { name: 'Docx', status, case_id: 'c1', draft_type: 'skill' });

      expect(toastMessage(mocks.toast[level])).toBe(message);
      expect(toastOptions(mocks.toast[level])).toMatchObject({ duration: 10_000, dismissible: true });
      toastOptions(mocks.toast[level]).action?.onClick();
      expect(mocks.router.push).toHaveBeenCalledWith('/settings/evolutionPending');
      expect(events()).toEqual([
        { type: 'skill-growth-updated', detail: { caseId: 'c1', status, draftType: 'skill', name: 'Docx' } },
      ]);
    });

    it('skill_growth_updated AUTO_APPLIED delegates to the learned toast, other statuses stay silent', () => {
      mountGlobalEvents();

      emit('skill_growth_updated', { name: 'Docx', status: 'AUTO_APPLIED' });
      emit('skill_growth_updated', { name: 'Docx', status: 'PENDING' });

      expect(mocks.showSkillLearnedToast).toHaveBeenCalledTimes(1);
      expect(mocks.showSkillLearnedToast).toHaveBeenCalledWith('Docx', {
        t: expect.any(Function),
        pushToast: expect.any(Object),
        openSkillGrowth: expect.any(Function),
      });
      expect(mocks.toast.error).not.toHaveBeenCalled();
      expect(mocks.toast.warning).not.toHaveBeenCalled();
    });

    it('skill_evolved delegates to the evolved toast and relays the evolution type', () => {
      mountGlobalEvents();
      const events = recordWindowEvents();

      emit('skill_evolved', { skill_name: 'Docx', evolution_type: 'merge' });
      emit('skill_evolved', { skill_name: 'Pdf' });

      expect(mocks.showSkillEvolvedToast).toHaveBeenCalledWith(
        { skill_name: 'Docx', evolution_type: 'merge' },
        { t: expect.any(Function), pushToast: expect.any(Object), openSkillGrowth: expect.any(Function) },
      );
      expect(events()).toEqual([
        { type: 'skill-evolved', detail: { skill_name: 'Docx', evolution_type: 'merge' } },
        { type: 'skill-evolved', detail: { skill_name: 'Pdf', evolution_type: 'new' } },
      ]);
    });
  });

  describe('skill_pool_updated', () => {
    it('relays every update and reloads the skill lists once after the burst settles', async () => {
      mountGlobalEvents();
      const events = recordWindowEvents();

      emit('skill_pool_updated', { action: 'install', skill_id: 'local::a' });
      await vi.advanceTimersByTimeAsync(200);
      emit('skill_pool_updated', { action: 'uninstall', skill_id: 'local::a' });
      await vi.advanceTimersByTimeAsync(299);
      await vi.dynamicImportSettled();
      expect(mocks.fetchLocalSkills).not.toHaveBeenCalled();

      await vi.advanceTimersByTimeAsync(1);
      await vi.dynamicImportSettled();

      expect(mocks.fetchLocalSkills).toHaveBeenCalledTimes(1);
      expect(mocks.fetchUserSkillConfig).toHaveBeenCalledTimes(1);
      expect(mocks.fetchUserSkillConfig).toHaveBeenCalledWith(true);
      expect(events()).toEqual([
        { type: 'skill_pool_updated', detail: { action: 'install', skill_id: 'local::a' } },
        { type: 'skill_pool_updated', detail: { action: 'uninstall', skill_id: 'local::a' } },
      ]);
    });

    it('drops a pending reload when the hook unmounts', async () => {
      const { unmount } = mountGlobalEvents();

      emit('skill_pool_updated', { action: 'install' });
      unmount();
      await vi.advanceTimersByTimeAsync(1_000);
      await vi.dynamicImportSettled();

      expect(mocks.fetchLocalSkills).not.toHaveBeenCalled();
      expect(mocks.fetchUserSkillConfig).not.toHaveBeenCalled();
    });
  });

  describe('system_notification', () => {
    it('shows the notice as a toast and relays the whole payload', () => {
      mountGlobalEvents();
      const events = recordWindowEvents();

      emit('system_notification', { title: 'Backup done', message: '3 files' });

      expect(toastMessage(mocks.toast.success)).toBe('Backup done');
      expect(toastOptions(mocks.toast.success)).toEqual({
        description: '3 files',
        duration: 10_000,
        dismissible: true,
      });
      expect(events()).toEqual([
        {
          type: 'system-notification',
          detail: {
            type: 'system_notification',
            data: { title: 'Backup done', message: '3 files' },
            timestamp: expect.any(String),
          },
        },
      ]);
    });

    it.each(['info', 'warning', 'error'] as const)('shows a notice that declares the %s level as that toast', (level) => {
      mountGlobalEvents();

      emit('system_notification', { title: 'Task paused', message: 'Reached its end time.', meta_data: { level } });

      expect(toastMessage(mocks.toast[level])).toBe('Task paused');
      expect(toastOptions(mocks.toast[level])).toEqual({
        description: 'Reached its end time.',
        duration: 10_000,
        dismissible: true,
      });
      expect(mocks.toast.success).not.toHaveBeenCalled();
    });

    it('falls back to a default title and stays silent for snapshot_created notices', () => {
      mountGlobalEvents();

      emit('system_notification', { message: 'x' });
      emit('system_notification', { title: 'Snapshot', message: 'y', meta_data: { type: 'snapshot_created' } });

      expect(mocks.toast.success).toHaveBeenCalledTimes(1);
      expect(toastMessage(mocks.toast.success)).toBe('systemNotificationTitle');
    });

    it('refreshes the goal and the background task list when a background job finishes', async () => {
      mountGlobalEvents();
      const meta = { kind: 'background_job_finish', chat_id: 'c1' };

      emit('system_notification', { title: 't', message: 'm', meta_data: meta });
      emit('system_notification', {
        title: 't',
        message: 'm',
        meta_data: { kind: 'background_job_finish', chat_id: ' ' },
      });
      await vi.dynamicImportSettled();

      expect(mocks.refreshActiveGoal).toHaveBeenCalledTimes(1);
      expect(mocks.refreshActiveGoal).toHaveBeenCalledWith('c1');
      expect(mocks.shellJobFinish).toHaveBeenCalledTimes(1);
      expect(mocks.shellJobFinish).toHaveBeenCalledWith(meta);
    });

    it('announces a finished voice task only for a chat that owns it', () => {
      mountGlobalEvents();
      const events = recordWindowEvents();
      const meta = { kind: 'voice_background_task_done', chat_id: 'c9' };

      emit('system_notification', { title: 'Voice', message: 'done', meta_data: meta });
      emit('system_notification', {
        title: 'Voice',
        message: 'done',
        meta_data: { kind: 'voice_background_task_done' },
      });

      expect(mocks.voiceJobFinish).toHaveBeenCalledTimes(2);
      expect(mocks.voiceJobFinish).toHaveBeenCalledWith(meta);
      expect(events().filter((event) => event.type === 'voice-bg-done')).toEqual([
        { type: 'voice-bg-done', detail: { title: 'Voice', message: 'done', chat_id: 'c9' } },
      ]);
    });
  });
});
