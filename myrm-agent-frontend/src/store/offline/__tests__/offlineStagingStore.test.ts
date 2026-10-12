import { describe, it, expect, beforeEach, vi } from 'vitest';
import { offlineStagingStore, type StagingRecord } from '../offlineStagingStore';
import type { StagingItemPayload } from '@/lib/e2ee/offlineE2EECryptoBridge';

describe('offlineStagingStore', () => {
  const samplePayload: StagingItemPayload = {
    title: 'Mobile Brain Dump',
    content: 'Need to remember adding E2EE support for mobile capture drawer.',
    voiceTranscript: 'Audio transcribed note: check web crypto compatibility.',
    tags: ['mobile', 'ideas'],
  };

  beforeEach(async () => {
    vi.clearAllMocks();
    await offlineStagingStore.clearAll();
  });

  it('adds an item to staging queue and automatically encrypts it', async () => {
    const record = await offlineStagingStore.addItem(samplePayload);

    expect(record.id).toMatch(/^stg_\d+_/);
    expect(record.payload.content).toBe(samplePayload.content);
    expect(record.status).toBe('encrypted');
    expect(record.envelope).toBeDefined();
    expect(record.envelope?.algorithm).toBe('AES-GCM-256');

    const all = await offlineStagingStore.getAll();
    expect(all.length).toBe(1);
    expect(all[0].id).toBe(record.id);
  });

  it('retrieves staged items by id and deletes them', async () => {
    const record = await offlineStagingStore.addItem(samplePayload);
    const retrieved = await offlineStagingStore.getById(record.id);
    expect(retrieved?.id).toBe(record.id);

    await offlineStagingStore.deleteItem(record.id);
    const afterDelete = await offlineStagingStore.getById(record.id);
    expect(afterDelete).toBeNull();
  });

  it('notifies subscribers upon adding and deleting items', async () => {
    const subscriberMock = vi.fn();
    const unsubscribe = offlineStagingStore.subscribe(subscriberMock);

    // Initial subscriber call
    expect(subscriberMock).toHaveBeenCalledWith([]);

    await offlineStagingStore.addItem(samplePayload);
    expect(subscriberMock).toHaveBeenCalledTimes(2);
    expect(subscriberMock.mock.calls[1][0].length).toBe(1);

    unsubscribe();
    await offlineStagingStore.clearAll();
    // After unsubscribe, count should remain 2
    expect(subscriberMock).toHaveBeenCalledTimes(2);
  });

  it('updates item status and tracks error retry count', async () => {
    const record = await offlineStagingStore.addItem(samplePayload);
    expect(record.retryCount).toBe(0);

    await offlineStagingStore.updateItemStatus(record.id, 'failed', 'Network timeout');
    const updated = await offlineStagingStore.getById(record.id);
    expect(updated?.status).toBe('failed');
    expect(updated?.retryCount).toBe(1);
    expect(updated?.lastError).toBe('Network timeout');
  });

  it('syncs queue and clears synced records', async () => {
    // Add two items
    const record1 = await offlineStagingStore.addItem({ content: 'Item 1' });
    const record2 = await offlineStagingStore.addItem({ content: 'Item 2' });

    // Mock navigator.onLine as true
    vi.stubGlobal('navigator', { onLine: true });

    const result = await offlineStagingStore.syncQueue();
    expect(result.synced).toBe(2);
    expect(result.failed).toBe(0);

    const allAfterSync = await offlineStagingStore.getAll();
    expect(allAfterSync.every((r: StagingRecord) => r.status === 'synced')).toBe(true);

    const clearedCount = await offlineStagingStore.clearSynced();
    expect(clearedCount).toBe(2);

    const allAfterClear = await offlineStagingStore.getAll();
    expect(allAfterClear.length).toBe(0);

    vi.unstubAllGlobals();
  });

  it('marks items as failed during sync when offline', async () => {
    await offlineStagingStore.addItem({ content: 'Offline Item' });

    // Mock navigator.onLine as false
    vi.stubGlobal('navigator', { onLine: false });

    const result = await offlineStagingStore.syncQueue();
    expect(result.synced).toBe(0);
    expect(result.failed).toBe(1);

    const all = await offlineStagingStore.getAll();
    expect(all[0].status).toBe('failed');
    expect(all[0].lastError).toContain('Offline');

    vi.unstubAllGlobals();
  });
});
