/**
 * Voice Stream Store Unit Tests
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { useVoiceStreamStore } from '../useVoiceStreamStore';

describe('useVoiceStreamStore', () => {
  beforeEach(() => {
    useVoiceStreamStore.getState().resetToDefault();
  });

  it('should initialize with idle status and default metrics', () => {
    const state = useVoiceStreamStore.getState();
    expect(state.status).toBe('idle');
    expect(state.isDuplexEnabled).toBe(false);
    expect(state.metrics.framesSent).toBe(0);
    expect(state.vadState).toBe('silence');
  });

  it('should unlock Autoplay policy via resumeContext', () => {
    const store = useVoiceStreamStore.getState();
    store.refreshEnvironmentReport({
      audioContextState: 'suspended',
    });
    expect(useVoiceStreamStore.getState().environmentReport.isAutoplaySuspended).toBe(true);

    store.resumeContext();
    const updated = useVoiceStreamStore.getState();
    expect(updated.isAutoplayDismissed).toBe(true);
    expect(updated.environmentReport.isAutoplaySuspended).toBe(false);
    expect(updated.environmentReport.requiresUserGesture).toBe(false);
  });

  it('should fail starting stream if context is insecure', async () => {
    const store = useVoiceStreamStore.getState();
    store.refreshEnvironmentReport({
      isSecureContext: false,
      protocol: 'http:',
      host: '192.168.1.100:3000',
      hasMediaDevices: false,
    });

    const success = await store.startDuplexStream();
    expect(success).toBe(false);
    expect(useVoiceStreamStore.getState().status).toBe('error');
    expect(useVoiceStreamStore.getState().errorMessage).toContain('非安全上下文');
  });

  it('should start and stop duplex stream properly under secure environment', async () => {
    const store = useVoiceStreamStore.getState();
    store.refreshEnvironmentReport({
      isSecureContext: true,
      protocol: 'https:',
      host: 'myrm.example.com',
      hasMediaDevices: true,
    });

    const success = await store.startDuplexStream();
    expect(success).toBe(true);
    expect(useVoiceStreamStore.getState().status).toBe('duplex_active');
    expect(useVoiceStreamStore.getState().isDuplexEnabled).toBe(true);

    // Process chunk during stream
    const chunk = new Float32Array([0.2, 0.4, 0.3, 0.5]);
    const frame = store.processAudioChunk(chunk);
    expect(frame.rmsEnergy).toBeGreaterThan(0);
    expect(useVoiceStreamStore.getState().metrics.framesSent).toBe(1);

    // Stop stream
    store.stopStream();
    expect(useVoiceStreamStore.getState().status).toBe('idle');
    expect(useVoiceStreamStore.getState().isDuplexEnabled).toBe(false);
  });

  it('should simulate agent speech playback lifecycle', () => {
    const store = useVoiceStreamStore.getState();
    store.setIsDuplexEnabled(true);

    store.simulateAgentSpeech(true);
    expect(useVoiceStreamStore.getState().status).toBe('speaking');
    expect(useVoiceStreamStore.getState().metrics.framesReceived).toBe(1);

    store.simulateAgentSpeech(false);
    expect(useVoiceStreamStore.getState().status).toBe('duplex_active');
  });
});
