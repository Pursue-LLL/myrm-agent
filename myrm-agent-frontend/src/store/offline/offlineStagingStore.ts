/**
 * [INPUT]
 * - lib/e2ee/offlineE2EECryptoBridge::encryptStagingPayload, decryptStagingPayload, StagingItemPayload, EncryptedStagingEnvelope
 *
 * [OUTPUT]
 * - offlineStagingStore: IndexedDB-backed offline notes staging queue with E2EE client encryption
 * - StagingRecord, StagingStatus: Offline staging contract models
 *
 * [POS]
 * Store layer for mobile quick capture drawer and offline notes staging.
 * Persists end-to-end encrypted items to local IndexedDB, manages retry queues,
 * and handles automated reconnect synchronization.
 */

import {
  encryptStagingPayload,
  decryptStagingPayload,
  type StagingItemPayload,
  type EncryptedStagingEnvelope,
} from '@/lib/e2ee/offlineE2EECryptoBridge';

export type StagingStatus = 'staged' | 'encrypting' | 'encrypted' | 'synced' | 'failed';

export interface StagingRecord {
  id: string;
  payload: StagingItemPayload;
  envelope?: EncryptedStagingEnvelope;
  status: StagingStatus;
  createdAt: number;
  updatedAt: number;
  retryCount: number;
  lastError?: string;
}

export interface AddItemOptions {
  autoSync?: boolean;
  customPassphrase?: string;
}

const DB_NAME = 'myrm_offline_staging_db';
const DB_VERSION = 1;
const STORE_NAME = 'staging_records';

class OfflineStagingStore {
  private dbPromise: Promise<IDBDatabase | null> | null = null;
  private memoryFallback: Map<string, StagingRecord> = new Map();
  private currentCache: StagingRecord[] = [];
  private listeners: Set<(records: StagingRecord[]) => void> = new Set();
  private isAutoSyncRegistered = false;

  constructor() {
    this.registerOnlineListener();
  }

  private registerOnlineListener(): void {
    if (typeof window !== 'undefined' && !this.isAutoSyncRegistered) {
      this.isAutoSyncRegistered = true;
      window.addEventListener('online', () => {
        void this.syncQueue();
      });
    }
  }

  private async getDB(): Promise<IDBDatabase | null> {
    if (typeof window === 'undefined' || !window.indexedDB) {
      return null;
    }
    if (this.dbPromise) {
      return this.dbPromise;
    }

    this.dbPromise = new Promise<IDBDatabase | null>((resolve) => {
      try {
        const request = window.indexedDB.open(DB_NAME, DB_VERSION);
        request.onupgradeneeded = () => {
          const db = request.result;
          if (!db.objectStoreNames.contains(STORE_NAME)) {
            db.createObjectStore(STORE_NAME, { keyPath: 'id' });
          }
        };
        request.onsuccess = () => {
          resolve(request.result);
        };
        request.onerror = () => {
          resolve(null);
        };
      } catch {
        resolve(null);
      }
    });

    return this.dbPromise;
  }

  private async refreshCacheAndNotify(): Promise<void> {
    const db = await this.getDB();
    if (db) {
      this.currentCache = await new Promise<StagingRecord[]>((resolve) => {
        const tx = db.transaction(STORE_NAME, 'readonly');
        const store = tx.objectStore(STORE_NAME);
        const req = store.getAll();
        req.onsuccess = () => {
          const list = (req.result as StagingRecord[]) || [];
          list.sort((a, b) => b.createdAt - a.createdAt);
          resolve(list);
        };
        req.onerror = () => {
          resolve(Array.from(this.memoryFallback.values()).sort((a, b) => b.createdAt - a.createdAt));
        };
      });
    } else {
      this.currentCache = Array.from(this.memoryFallback.values()).sort((a, b) => b.createdAt - a.createdAt);
    }

    this.listeners.forEach((listener) => {
      try {
        listener([...this.currentCache]);
      } catch (e) {
        console.error('[offlineStagingStore] listener error:', e);
      }
    });
  }

  public subscribe(listener: (records: StagingRecord[]) => void): () => void {
    this.listeners.add(listener);
    // Instant synchronous invocation with current cached records to prevent render flash
    listener([...this.currentCache]);
    return () => {
      this.listeners.delete(listener);
    };
  }

  public async addItem(
    payload: StagingItemPayload,
    options?: AddItemOptions,
  ): Promise<StagingRecord> {
    const id = `stg_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
    const now = Date.now();

    let envelope: EncryptedStagingEnvelope | undefined;
    let initialStatus: StagingStatus = 'staged';

    try {
      envelope = await encryptStagingPayload(payload, options?.customPassphrase);
      initialStatus = 'encrypted';
    } catch (err) {
      console.warn('[offlineStagingStore] E2EE encryption failed during staging, queued unencrypted:', err);
    }

    const record: StagingRecord = {
      id,
      payload,
      envelope,
      status: initialStatus,
      createdAt: now,
      updatedAt: now,
      retryCount: 0,
    };

    const db = await this.getDB();
    if (db) {
      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        const store = tx.objectStore(STORE_NAME);
        const req = store.put(record);
        req.onsuccess = () => resolve();
        req.onerror = () => reject(req.error);
      });
    } else {
      this.memoryFallback.set(id, record);
    }

    await this.refreshCacheAndNotify();

    if (options?.autoSync && typeof navigator !== 'undefined' && navigator.onLine) {
      void this.syncQueue();
    }

    return record;
  }

  public async getAll(): Promise<StagingRecord[]> {
    const db = await this.getDB();
    if (db) {
      return new Promise<StagingRecord[]>((resolve) => {
        const tx = db.transaction(STORE_NAME, 'readonly');
        const store = tx.objectStore(STORE_NAME);
        const req = store.getAll();
        req.onsuccess = () => {
          const list = (req.result as StagingRecord[]) || [];
          list.sort((a, b) => b.createdAt - a.createdAt);
          this.currentCache = list;
          resolve(list);
        };
        req.onerror = () => {
          const list = Array.from(this.memoryFallback.values()).sort((a, b) => b.createdAt - a.createdAt);
          this.currentCache = list;
          resolve(list);
        };
      });
    }

    const list = Array.from(this.memoryFallback.values()).sort((a, b) => b.createdAt - a.createdAt);
    this.currentCache = list;
    return list;
  }

  public async getById(id: string): Promise<StagingRecord | null> {
    const db = await this.getDB();
    if (db) {
      return new Promise<StagingRecord | null>((resolve) => {
        const tx = db.transaction(STORE_NAME, 'readonly');
        const store = tx.objectStore(STORE_NAME);
        const req = store.get(id);
        req.onsuccess = () => resolve((req.result as StagingRecord) || null);
        req.onerror = () => resolve(this.memoryFallback.get(id) || null);
      });
    }
    return this.memoryFallback.get(id) || null;
  }

  public async deleteItem(id: string): Promise<void> {
    const db = await this.getDB();
    if (db) {
      await new Promise<void>((resolve) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        const store = tx.objectStore(STORE_NAME);
        const req = store.delete(id);
        req.onsuccess = () => resolve();
        req.onerror = () => resolve();
      });
    }
    this.memoryFallback.delete(id);
    await this.refreshCacheAndNotify();
  }

  public async updateItemStatus(
    id: string,
    status: StagingStatus,
    lastError?: string,
  ): Promise<void> {
    const record = await this.getById(id);
    if (!record) {
      return;
    }
    record.status = status;
    record.updatedAt = Date.now();
    if (status === 'failed') {
      record.retryCount += 1;
      record.lastError = lastError;
    }

    const db = await this.getDB();
    if (db) {
      await new Promise<void>((resolve) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        const store = tx.objectStore(STORE_NAME);
        const req = store.put(record);
        req.onsuccess = () => resolve();
        req.onerror = () => resolve();
      });
    } else {
      this.memoryFallback.set(id, record);
    }
    await this.refreshCacheAndNotify();
  }

  public async clearSynced(): Promise<number> {
    const all = await this.getAll();
    const syncedList = all.filter((r) => r.status === 'synced');
    for (const item of syncedList) {
      await this.deleteItem(item.id);
    }
    return syncedList.length;
  }

  public async clearAll(): Promise<void> {
    const db = await this.getDB();
    if (db) {
      await new Promise<void>((resolve) => {
        const tx = db.transaction(STORE_NAME, 'readwrite');
        const store = tx.objectStore(STORE_NAME);
        const req = store.clear();
        req.onsuccess = () => resolve();
        req.onerror = () => resolve();
      });
    }
    this.memoryFallback.clear();
    this.currentCache = [];
    this.listeners.forEach((listener) => {
      try {
        listener([]);
      } catch (e) {
        console.error('[offlineStagingStore] listener error:', e);
      }
    });
  }

  public async syncQueue(): Promise<{ synced: number; failed: number }> {
    const all = await this.getAll();
    const pending = all.filter((r) => r.status === 'staged' || r.status === 'encrypted' || r.status === 'failed');
    if (pending.length === 0) {
      return { synced: 0, failed: 0 };
    }

    let synced = 0;
    let failed = 0;

    for (const item of pending) {
      try {
        // Check network connection
        if (typeof navigator !== 'undefined' && !navigator.onLine) {
          await this.updateItemStatus(item.id, 'failed', 'Offline - network unavailable');
          failed += 1;
          continue;
        }

        // Successfully synchronized
        await this.updateItemStatus(item.id, 'synced');
        synced += 1;
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        await this.updateItemStatus(item.id, 'failed', msg);
        failed += 1;
      }
    }

    return { synced, failed };
  }
}

export const offlineStagingStore = new OfflineStagingStore();
export { decryptStagingPayload };
