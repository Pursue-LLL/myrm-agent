/**
 * [INPUT]
 * lib/vision/frameSelector::selectFrames (POS: Intelligent frame selector)
 * lib/vision/speechVisualSession::SpeechVisualSession (POS: Speech-visual time synchronizer)
 *
 * [OUTPUT]
 * useCameraInput: Hook managing camera lifecycle, frame buffer, snapshot capture, and facing mode toggle
 *
 * [POS]
 * Camera input manager. Provides real-time video capture with configurable frame buffering for multimodal interactions.
 */

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { VisualFrame } from '@/lib/vision/frameSelector';
import { selectFrames, type FrameSelectionOptions } from '@/lib/vision/frameSelector';
import { SpeechVisualSession } from '@/lib/vision/speechVisualSession';

export type CameraState = 'off' | 'starting' | 'active' | 'error';
export type FacingMode = 'user' | 'environment';

interface UseCameraInputOptions {
  captureIntervalMs?: number;
  maxBufferMs?: number;
  maxBufferFrames?: number;
  captureWidth?: number;
  captureHeight?: number;
  jpegQuality?: number;
  onError?: (error: string) => void;
}

interface UseCameraInputReturn {
  cameraState: CameraState;
  facingMode: FacingMode;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  startCamera: () => Promise<void>;
  stopCamera: () => void;
  toggleFacing: () => void;
  captureSnapshot: () => VisualFrame | null;
  getFramesForSpeech: (opts?: Partial<FrameSelectionOptions>) => VisualFrame[];
  beginSpeechCapture: () => void;
  endSpeechCapture: () => void;
  bufferSize: number;
}

const DEFAULT_CAPTURE_INTERVAL_MS = 500;
const DEFAULT_MAX_BUFFER_MS = 4000;
const DEFAULT_MAX_BUFFER_FRAMES = 48;
const DEFAULT_CAPTURE_WIDTH = 640;
const DEFAULT_CAPTURE_HEIGHT = 480;
const DEFAULT_JPEG_QUALITY = 0.6;

let frameCounter = 0;
function nextFrameId(): string {
  return `vf-${Date.now()}-${++frameCounter}`;
}

export function useCameraInput(options: UseCameraInputOptions = {}): UseCameraInputReturn {
  const {
    captureIntervalMs = DEFAULT_CAPTURE_INTERVAL_MS,
    maxBufferMs = DEFAULT_MAX_BUFFER_MS,
    maxBufferFrames = DEFAULT_MAX_BUFFER_FRAMES,
    captureWidth = DEFAULT_CAPTURE_WIDTH,
    captureHeight = DEFAULT_CAPTURE_HEIGHT,
    jpegQuality = DEFAULT_JPEG_QUALITY,
    onError,
  } = options;

  const [cameraState, setCameraState] = useState<CameraState>('off');
  const [facingMode, setFacingMode] = useState<FacingMode>('user');
  const [bufferSize, setBufferSize] = useState(0);
  const facingModeRef = useRef<FacingMode>('user');

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const framesRef = useRef<VisualFrame[]>([]);
  const sessionRef = useRef(new SpeechVisualSession());

  const pruneBuffer = useCallback(
    (now: number = Date.now()) => {
      const minTs = now - maxBufferMs;
      let frames = framesRef.current.filter((f) => f.timestamp >= minTs);
      if (frames.length > maxBufferFrames) {
        frames = frames.slice(-maxBufferFrames);
      }
      framesRef.current = frames;
      setBufferSize(frames.length);
    },
    [maxBufferMs, maxBufferFrames],
  );

  const captureFrame = useCallback((): VisualFrame | null => {
    const video = videoRef.current;
    if (!video || video.readyState < 2) return null;

    if (!canvasRef.current) {
      canvasRef.current = document.createElement('canvas');
    }
    const canvas = canvasRef.current;
    canvas.width = captureWidth;
    canvas.height = captureHeight;

    const ctx = canvas.getContext('2d');
    if (!ctx) return null;

    ctx.drawImage(video, 0, 0, captureWidth, captureHeight);
    const base64 = canvas.toDataURL('image/jpeg', jpegQuality);

    const frame: VisualFrame = {
      id: nextFrameId(),
      base64,
      width: captureWidth,
      height: captureHeight,
      timestamp: Date.now(),
    };

    framesRef.current.push(frame);
    pruneBuffer(frame.timestamp);

    return frame;
  }, [captureWidth, captureHeight, jpegQuality, pruneBuffer]);

  const stopCamera = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    framesRef.current = [];
    setBufferSize(0);
    sessionRef.current.reset();
    canvasRef.current = null;
    setCameraState('off');
  }, []);

  const startCamera = useCallback(async () => {
    if (cameraState === 'active' || cameraState === 'starting') return;

    setCameraState('starting');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: facingModeRef.current,
          width: { ideal: captureWidth },
          height: { ideal: captureHeight },
        },
      });

      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }

      intervalRef.current = setInterval(() => {
        captureFrame();
      }, captureIntervalMs);

      setCameraState('active');
    } catch {
      setCameraState('error');
      onError?.('Camera access denied or unavailable');
    }
  }, [cameraState, captureWidth, captureHeight, captureIntervalMs, captureFrame, onError]);

  const toggleFacing = useCallback(() => {
    const newMode: FacingMode = facingModeRef.current === 'user' ? 'environment' : 'user';
    facingModeRef.current = newMode;
    setFacingMode(newMode);

    if (cameraState === 'active') {
      stopCamera();
      setTimeout(() => {
        void startCamera();
      }, 100);
    }
  }, [cameraState, stopCamera, startCamera]);

  const captureSnapshot = useCallback((): VisualFrame | null => {
    return captureFrame();
  }, [captureFrame]);

  const beginSpeechCapture = useCallback(() => {
    sessionRef.current.beginSpeech();
  }, []);

  const endSpeechCapture = useCallback(() => {
    sessionRef.current.endSpeech();
  }, []);

  const getFramesForSpeech = useCallback((opts?: Partial<FrameSelectionOptions>): VisualFrame[] => {
    const window = sessionRef.current.endSpeech();
    sessionRef.current.reset();

    if (!window) {
      const latest = framesRef.current.at(-1);
      return latest ? [latest] : [];
    }

    const candidates = framesRef.current.filter(
      (f) => f.timestamp >= window.frameWindowStartAt && f.timestamp <= window.frameWindowEndAt,
    );

    if (candidates.length === 0) {
      const latest = framesRef.current.at(-1);
      return latest ? [latest] : [];
    }

    return selectFrames(candidates, opts).frames;
  }, []);

  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, [stopCamera]);

  return {
    cameraState,
    facingMode,
    videoRef,
    startCamera,
    stopCamera,
    toggleFacing,
    captureSnapshot,
    getFramesForSpeech,
    beginSpeechCapture,
    endSpeechCapture,
    bufferSize,
  };
}
