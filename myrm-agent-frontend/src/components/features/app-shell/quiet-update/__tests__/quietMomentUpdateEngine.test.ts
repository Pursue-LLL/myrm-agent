import { describe, it, expect } from 'vitest';
import {
  evaluateAppQuietness,
  isSnapshotFresh,
  isVersionDismissed,
  evaluateUpdateOfferEligibility,
  validateActionContext,
  formatDownloadSize,
} from '../quietMomentUpdateEngine';
import type {
  QuietMomentContext,
  UpdateAvailabilitySnapshot,
  DismissedVersionRecord,
} from '../quietMomentUpdateTypes';

describe('quietMomentUpdateEngine', () => {
  const baseContext: QuietMomentContext = {
    isWindowFocused: true,
    isDocumentVisible: true,
    lastTypedAt: 1000,
    typingGraceMs: 5000,
    hasActiveStreamingOrTask: false,
    hasBlockingSurface: false,
    connectionMode: 'local',
    isInstallingBusy: false,
    now: 10_000,
  };

  describe('evaluateAppQuietness', () => {
    it('should return quiet when all conditions are satisfied', () => {
      const result = evaluateAppQuietness(baseContext);
      expect(result.isQuiet).toBe(true);
      expect(result.reason).toBeUndefined();
    });

    it('should block when window is not focused or not visible', () => {
      const blurred = evaluateAppQuietness({ ...baseContext, isWindowFocused: false });
      expect(blurred.isQuiet).toBe(false);
      expect(blurred.reason).toBe('window_not_visible_or_blurred');

      const hidden = evaluateAppQuietness({ ...baseContext, isDocumentVisible: false });
      expect(hidden.isQuiet).toBe(false);
      expect(hidden.reason).toBe('window_not_visible_or_blurred');
    });

    it('should block when user typed recently within grace period', () => {
      const result = evaluateAppQuietness({
        ...baseContext,
        lastTypedAt: 8_000,
        now: 10_000, // 2000ms < 5000ms grace
      });
      expect(result.isQuiet).toBe(false);
      expect(result.reason).toBe('user_actively_typing');
    });

    it('should block when there is an active streaming or running task', () => {
      const result = evaluateAppQuietness({
        ...baseContext,
        hasActiveStreamingOrTask: true,
      });
      expect(result.isQuiet).toBe(false);
      expect(result.reason).toBe('active_task_or_streaming');
    });

    it('should block when blocking modal/popover surface is open', () => {
      const result = evaluateAppQuietness({
        ...baseContext,
        hasBlockingSurface: true,
      });
      expect(result.isQuiet).toBe(false);
      expect(result.reason).toBe('blocking_surface_open');
    });

    it('should block when background installer is busy', () => {
      const result = evaluateAppQuietness({
        ...baseContext,
        isInstallingBusy: true,
      });
      expect(result.isQuiet).toBe(false);
      expect(result.reason).toBe('install_busy');
    });
  });

  describe('isSnapshotFresh', () => {
    it('should return false for null snapshot', () => {
      expect(isSnapshotFresh(null, 10_000)).toBe(false);
    });

    it('should return true when snapshot is within fresh ttl', () => {
      const snapshot: UpdateAvailabilitySnapshot = {
        version: '1.2.0',
        readAt: 10_000,
      };
      expect(isSnapshotFresh(snapshot, 20_000, 60_000)).toBe(true);
      expect(isSnapshotFresh(snapshot, 75_000, 60_000)).toBe(false);
    });

    it('should respect empty snapshot short ttl', () => {
      const emptySnapshot: UpdateAvailabilitySnapshot = {
        version: '',
        readAt: 10_000,
      };
      expect(isSnapshotFresh(emptySnapshot, 14_000, 60_000, 5_000)).toBe(true);
      expect(isSnapshotFresh(emptySnapshot, 16_000, 60_000, 5_000)).toBe(false);
    });
  });

  describe('isVersionDismissed', () => {
    it('should return false when version is empty or not in dismissed records', () => {
      expect(isVersionDismissed('', [], 10_000)).toBe(false);
      expect(isVersionDismissed('1.0.0', [{ version: '1.0.1', dismissedAt: 5_000 }], 10_000)).toBe(false);
    });

    it('should return true when version is dismissed permanently', () => {
      const records: DismissedVersionRecord[] = [
        { version: '1.2.0', dismissedAt: 5_000 },
      ];
      expect(isVersionDismissed('1.2.0', records, 10_000)).toBe(true);
    });

    it('should respect remindAfter timestamp for snoozed versions', () => {
      const records: DismissedVersionRecord[] = [
        { version: '1.2.0', dismissedAt: 5_000, remindAfter: 20_000 },
      ];
      expect(isVersionDismissed('1.2.0', records, 15_000)).toBe(true);
      expect(isVersionDismissed('1.2.0', records, 25_000)).toBe(false);
    });
  });

  describe('evaluateUpdateOfferEligibility', () => {
    const validSnapshot: UpdateAvailabilitySnapshot = {
      version: '2.0.0',
      readAt: 10_000,
    };

    it('should approve offer when context is quiet and update is ready', () => {
      const result = evaluateUpdateOfferEligibility({
        ctx: baseContext,
        snapshot: validSnapshot,
        dismissedRecords: [],
      });
      expect(result.canOffer).toBe(true);
      expect(result.tipId).toBe('update-offer:2.0.0');
    });

    it('should reject when connection mode is not local/hybrid', () => {
      const result = evaluateUpdateOfferEligibility({
        ctx: { ...baseContext, connectionMode: 'cloud' },
        snapshot: validSnapshot,
        dismissedRecords: [],
      });
      expect(result.canOffer).toBe(false);
      expect(result.blockReason).toBe('connection_mode_ineligible');
    });

    it('should reject when offer is in cooldown', () => {
      const result = evaluateUpdateOfferEligibility({
        ctx: baseContext,
        snapshot: validSnapshot,
        dismissedRecords: [],
        lastOfferedAt: 9_000,
        cooldownMs: 5_000,
      });
      expect(result.canOffer).toBe(false);
      expect(result.blockReason).toBe('cooling_down');
    });
  });

  describe('validateActionContext & formatDownloadSize', () => {
    it('should validate action context generations and task states', () => {
      expect(validateActionContext(1, 1, baseContext)).toBe(true);
      expect(validateActionContext(1, 2, baseContext)).toBe(false);
      expect(validateActionContext(1, 1, { ...baseContext, isInstallingBusy: true })).toBe(false);
      expect(validateActionContext(1, 1, { ...baseContext, hasActiveStreamingOrTask: true })).toBe(false);
    });

    it('should format file download sizes properly', () => {
      expect(formatDownloadSize()).toBe('');
      expect(formatDownloadSize(0)).toBe('');
      expect(formatDownloadSize(45.5)).toBe('45.5 MB');
      expect(formatDownloadSize(1536)).toBe('1.5 GB');
    });
  });
});
