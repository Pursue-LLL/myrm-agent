/**
 * Audio PCM Processor & VAD Machine Unit Tests
 */

import { describe, expect, it } from 'vitest';
import {
  calculateRmsEnergy,
  convertFloat32ToInt16Pcm,
  convertRmsToDecibel,
  FrontendVadStateMachine,
  processAudioInputChunk,
} from '../audioPcmProcessor';

describe('audioPcmProcessor', () => {
  it('should convert Float32 [-1, 1] to Int16 PCM correctly', () => {
    const floatArray = new Float32Array([0, 1.0, -1.0, 0.5, -0.5]);
    const pcm = convertFloat32ToInt16Pcm(floatArray);

    expect(pcm[0]).toBe(0);
    expect(pcm[1]).toBe(32767);
    expect(pcm[2]).toBe(-32768);
    expect(pcm[3]).toBe(16383);
    expect(pcm[4]).toBe(-16384);
  });

  it('should calculate RMS energy and decibel accurately', () => {
    const silence = new Float32Array(100).fill(0);
    expect(calculateRmsEnergy(silence)).toBe(0);
    expect(convertRmsToDecibel(0)).toBe(-100);

    const fullScale = new Float32Array(100).fill(1.0);
    const rms = calculateRmsEnergy(fullScale);
    expect(rms).toBeCloseTo(1.0);
    expect(convertRmsToDecibel(rms)).toBeCloseTo(0);
  });

  it('should track speech and silence transitions via FrontendVadStateMachine', () => {
    const vad = new FrontendVadStateMachine(0.02);

    // Initial state is silence
    expect(vad.getCurrentState()).toBe('silence');

    // Single frame above threshold does not trigger speech immediately (requires 2 consecutive frames)
    expect(vad.processRms(0.05)).toBe('silence');
    // Second frame triggers speech
    expect(vad.processRms(0.06)).toBe('speech');
    expect(vad.getCurrentState()).toBe('speech');

    // Silence for 4 frames should still hold speech state
    for (let i = 0; i < 4; i++) {
      expect(vad.processRms(0.005)).toBe('speech');
    }
    // 5th consecutive silence frame transitions back to silence
    expect(vad.processRms(0.005)).toBe('silence');
  });

  it('should process audio chunk and return standard PcmAudioFrame', () => {
    const vad = new FrontendVadStateMachine(0.01);
    const sampleChunk = new Float32Array([0.1, 0.2, 0.15, 0.3]);

    const frame = processAudioInputChunk(sampleChunk, vad, 16000);
    expect(frame.sampleRate).toBe(16000);
    expect(frame.pcmData.length).toBe(4);
    expect(frame.rmsEnergy).toBeGreaterThan(0);
    expect(frame.decibel).toBeGreaterThan(-100);
    expect(typeof frame.isSpeech).toBe('boolean');
  });
});
