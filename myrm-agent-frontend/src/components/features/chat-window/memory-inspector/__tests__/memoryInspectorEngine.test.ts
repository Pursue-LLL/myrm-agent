/**
 * [INPUT]
 * - @/components/features/chat-window/memory-inspector/memoryInspectorEngine
 *
 * [OUTPUT]
 * - Unit test suite for pure computational functions in memoryInspectorEngine.
 */

import { describe, it, expect, vi } from 'vitest';
import {
  evaluateLatencyRating,
  calculateReindexTokenEstimate,
  calculateProgressPercent,
  formatVectorStoreLabel,
  computeSimulatedDiagnostic,
  dispatchMemoryHealthEvent,
} from '../memoryInspectorEngine';
import type { VectorStoreType } from '../memoryInspectorTypes';

describe('memoryInspectorEngine', () => {
  describe('evaluateLatencyRating', () => {
    it('should classify latency under 100ms as optimal', () => {
      expect(evaluateLatencyRating(50)).toBe('optimal');
      expect(evaluateLatencyRating(99)).toBe('optimal');
    });

    it('should classify latency between 100ms and 300ms as acceptable', () => {
      expect(evaluateLatencyRating(100)).toBe('acceptable');
      expect(evaluateLatencyRating(250)).toBe('acceptable');
      expect(evaluateLatencyRating(300)).toBe('acceptable');
    });

    it('should classify latency over 300ms as degraded', () => {
      expect(evaluateLatencyRating(301)).toBe('degraded');
      expect(evaluateLatencyRating(1200)).toBe('degraded');
    });
  });

  describe('calculateReindexTokenEstimate', () => {
    it('should estimate token usage with default and custom chunk averages', () => {
      expect(calculateReindexTokenEstimate(4000)).toBe(1000000);
      expect(calculateReindexTokenEstimate(1000, 300)).toBe(300000);
    });

    it('should return 0 for zero or negative chunk counts', () => {
      expect(calculateReindexTokenEstimate(0)).toBe(0);
      expect(calculateReindexTokenEstimate(-10)).toBe(0);
    });
  });

  describe('calculateProgressPercent', () => {
    it('should calculate clamped percentage between 0 and 100', () => {
      expect(calculateProgressPercent(50, 200)).toBe(25);
      expect(calculateProgressPercent(200, 200)).toBe(100);
      expect(calculateProgressPercent(250, 200)).toBe(100);
      expect(calculateProgressPercent(-10, 200)).toBe(0);
    });

    it('should return 0 when total is 0 or negative', () => {
      expect(calculateProgressPercent(10, 0)).toBe(0);
      expect(calculateProgressPercent(10, -5)).toBe(0);
    });
  });

  describe('formatVectorStoreLabel', () => {
    it('should return human-readable labels for known vector stores', () => {
      expect(formatVectorStoreLabel('sqlite_vec')).toContain('SQLite-vec');
      expect(formatVectorStoreLabel('qdrant')).toContain('Qdrant');
      expect(formatVectorStoreLabel('pgvector')).toContain('PGVector');
      expect(formatVectorStoreLabel('memory_ephemeral')).toContain('Memory Ephemeral');
    });

    it('should fallback for unknown vector store types', () => {
      expect(formatVectorStoreLabel('unknown_custom' as VectorStoreType)).toBe('未知向量引擎');
    });
  });

  describe('computeSimulatedDiagnostic', () => {
    it('should compute breakdown with default delays', () => {
      const diag = computeSimulatedDiagnostic({ probedAt: 1000 });
      expect(diag.embeddingMs).toBe(42);
      expect(diag.storageWriteMs).toBe(12);
      expect(diag.cosineSearchMs).toBe(16);
      expect(diag.totalMs).toBe(70);
      expect(diag.overallRating).toBe('optimal');
      expect(diag.probedAt).toBe(1000);
    });

    it('should compute breakdown with custom delays', () => {
      const diag = computeSimulatedDiagnostic({
        embeddingDelay: 200,
        storageWriteDelay: 80,
        cosineSearchDelay: 50,
      });
      expect(diag.totalMs).toBe(330);
      expect(diag.overallRating).toBe('degraded');
    });
  });

  describe('dispatchMemoryHealthEvent', () => {
    it('should dispatch custom browser event with event detail', () => {
      const spy = vi.spyOn(window, 'dispatchEvent');

      const dispatched = dispatchMemoryHealthEvent({
        action: 'deep_diagnostic',
        timestamp: 123456,
      });

      expect(dispatched).toBe(true);
      expect(spy).toHaveBeenCalled();
      spy.mockRestore();
    });
  });
});
