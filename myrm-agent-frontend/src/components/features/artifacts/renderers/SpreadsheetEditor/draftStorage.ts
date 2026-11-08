/**
 * [INPUT]
 * IndexedDB 浏览器存储 API
 * [OUTPUT]
 * `getDraftKey`, `saveDraft`, `loadDraft`, `deleteDraft`
 * [POS]
 * 表格编辑器离线草稿本地存储与容灾恢复机制
 */

const DRAFT_DB_NAME = 'myrm-spreadsheet-drafts';
const DRAFT_STORE = 'drafts';

export function getDraftKey(previewUrl: string): string {
  return `draft:${previewUrl}`;
}

async function openDraftDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DRAFT_DB_NAME, 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(DRAFT_STORE);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function saveDraft(key: string, snapshot: unknown): Promise<void> {
  try {
    const db = await openDraftDB();
    const tx = db.transaction(DRAFT_STORE, 'readwrite');
    tx.objectStore(DRAFT_STORE).put(snapshot, key);
    await new Promise<void>((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch {
    /* best-effort; don't crash editor on quota/permission errors */
  }
}

export async function loadDraft(key: string): Promise<unknown | null> {
  try {
    const db = await openDraftDB();
    const tx = db.transaction(DRAFT_STORE, 'readonly');
    const req = tx.objectStore(DRAFT_STORE).get(key);
    const result = await new Promise<unknown | null>((resolve, reject) => {
      req.onsuccess = () => resolve(req.result ?? null);
      req.onerror = () => reject(req.error);
    });
    db.close();
    return result;
  } catch {
    return null;
  }
}

export async function deleteDraft(key: string): Promise<void> {
  try {
    const db = await openDraftDB();
    const tx = db.transaction(DRAFT_STORE, 'readwrite');
    tx.objectStore(DRAFT_STORE).delete(key);
    await new Promise<void>((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch {
    /* best-effort */
  }
}
