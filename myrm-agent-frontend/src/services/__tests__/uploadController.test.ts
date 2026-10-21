import { describe, expect, it, beforeEach } from 'vitest';
import { getUploadSignal, abortCurrentUpload, resetUploadController } from '../uploadController';

describe('uploadController', () => {
  beforeEach(() => {
    abortCurrentUpload();
  });

  it('getUploadSignal returns an AbortSignal', () => {
    const signal = getUploadSignal();
    expect(signal).toBeInstanceOf(AbortSignal);
    expect(signal.aborted).toBe(false);
  });

  it('getUploadSignal returns the same signal on consecutive calls', () => {
    const s1 = getUploadSignal();
    const s2 = getUploadSignal();
    expect(s1).toBe(s2);
  });

  it('abortCurrentUpload aborts the current signal', () => {
    const signal = getUploadSignal();
    abortCurrentUpload();
    expect(signal.aborted).toBe(true);
  });

  it('abortCurrentUpload is safe to call when no controller exists', () => {
    expect(() => abortCurrentUpload()).not.toThrow();
    expect(() => abortCurrentUpload()).not.toThrow();
  });

  it('resetUploadController creates a fresh non-aborted signal', () => {
    const oldSignal = getUploadSignal();
    abortCurrentUpload();
    expect(oldSignal.aborted).toBe(true);

    resetUploadController();
    const newSignal = getUploadSignal();
    expect(newSignal.aborted).toBe(false);
    expect(newSignal).not.toBe(oldSignal);
  });

  it('abort after reset does not affect old signal holders', () => {
    const s1 = getUploadSignal();
    resetUploadController();
    const s2 = getUploadSignal();
    abortCurrentUpload();
    expect(s1.aborted).toBe(false);
    expect(s2.aborted).toBe(true);
  });

  it('rapid consecutive aborts do not throw (simulates fast session switching)', () => {
    resetUploadController();
    expect(() => {
      abortCurrentUpload();
      abortCurrentUpload();
      abortCurrentUpload();
    }).not.toThrow();
  });

  it('reset-abort-reset cycle produces valid fresh signals each time', () => {
    resetUploadController();
    const s1 = getUploadSignal();
    abortCurrentUpload();
    expect(s1.aborted).toBe(true);

    resetUploadController();
    const s2 = getUploadSignal();
    expect(s2.aborted).toBe(false);
    abortCurrentUpload();
    expect(s2.aborted).toBe(true);

    resetUploadController();
    const s3 = getUploadSignal();
    expect(s3.aborted).toBe(false);
    expect(s3).not.toBe(s1);
    expect(s3).not.toBe(s2);
  });

  it('getUploadSignal after abort without reset returns a new non-aborted signal', () => {
    resetUploadController();
    const s1 = getUploadSignal();
    abortCurrentUpload();
    expect(s1.aborted).toBe(true);

    const s2 = getUploadSignal();
    expect(s2.aborted).toBe(false);
    expect(s2).not.toBe(s1);
  });

  it('abort event listener fires on signal', () => {
    resetUploadController();
    const signal = getUploadSignal();
    let abortFired = false;
    signal.addEventListener('abort', () => {
      abortFired = true;
    });
    abortCurrentUpload();
    expect(abortFired).toBe(true);
  });
});
