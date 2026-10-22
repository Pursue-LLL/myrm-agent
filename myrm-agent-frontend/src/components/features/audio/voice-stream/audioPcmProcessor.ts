/**
 * Audio PCM Sampling & VAD (Voice Activity Detection) Engine
 * 16kHz PCM 单声道重采样转换、RMS 能量计算与轻量级前端 VAD 状态机
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 所有 if 显式包裹大括号；
 * 3. 行数严格受控在 400 行以内。
 */

import { AudioSampleConfig, PcmAudioFrame, VadState } from './voiceStreamTypes';

export const DEFAULT_AUDIO_CONFIG: AudioSampleConfig = {
  sampleRate: 16000,
  channelCount: 1,
  bufferSize: 2048,
  vadThreshold: 0.015,
};

export function convertFloat32ToInt16Pcm(input: Float32Array): Int16Array {
  const output = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    output[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return output;
}

export function calculateRmsEnergy(input: Float32Array): number {
  if (input.length === 0) {
    return 0;
  }
  let sumSquares = 0;
  for (let i = 0; i < input.length; i++) {
    sumSquares += input[i] * input[i];
  }
  return Math.sqrt(sumSquares / input.length);
}

export function convertRmsToDecibel(rms: number): number {
  if (rms <= 0.00001) {
    return -100;
  }
  return Math.max(-100, Math.min(0, 20 * Math.log10(rms)));
}

export class FrontendVadStateMachine {
  private threshold: number;
  private consecutiveSpeechFrames: number = 0;
  private consecutiveSilenceFrames: number = 0;
  private currentState: VadState = 'silence';

  constructor(threshold: number = DEFAULT_AUDIO_CONFIG.vadThreshold) {
    this.threshold = threshold;
  }

  public setThreshold(threshold: number): void {
    this.threshold = threshold;
  }

  public processRms(rms: number): VadState {
    const isAboveThreshold = rms >= this.threshold;

    if (isAboveThreshold) {
      this.consecutiveSpeechFrames += 1;
      this.consecutiveSilenceFrames = 0;
      if (this.consecutiveSpeechFrames >= 2) {
        this.currentState = 'speech';
      }
    } else {
      this.consecutiveSilenceFrames += 1;
      this.consecutiveSpeechFrames = 0;
      if (this.consecutiveSilenceFrames >= 5) {
        this.currentState = 'silence';
      }
    }

    return this.currentState;
  }

  public getCurrentState(): VadState {
    return this.currentState;
  }

  public reset(): void {
    this.consecutiveSpeechFrames = 0;
    this.consecutiveSilenceFrames = 0;
    this.currentState = 'silence';
  }
}

export function processAudioInputChunk(
  float32Chunk: Float32Array,
  vadMachine: FrontendVadStateMachine,
  sampleRate: number = DEFAULT_AUDIO_CONFIG.sampleRate
): PcmAudioFrame {
  const pcmData = convertFloat32ToInt16Pcm(float32Chunk);
  const rmsEnergy = calculateRmsEnergy(float32Chunk);
  const decibel = convertRmsToDecibel(rmsEnergy);
  const vadState = vadMachine.processRms(rmsEnergy);

  return {
    timestamp: Date.now(),
    sampleRate,
    pcmData,
    rmsEnergy,
    decibel,
    isSpeech: vadState === 'speech',
  };
}
