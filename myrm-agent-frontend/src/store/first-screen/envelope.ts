/**
 * [INPUT]
 * - window.localStorage (POS: per-origin storage of the desktop WebView; the shell serves the UI from a fixed port)
 * - @/lib/utils/typeUtils::isRecord (POS: guard for parsed JSON)
 * - process.env.NEXT_PUBLIC_APP_BUILD (POS: release tag the bundle was built for; `dev` outside release builds)
 *
 * [OUTPUT]
 * - SnapshotSectionName: the whitelist of first-screen data that may be stored.
 * - readSnapshotSection / writeSnapshotSection / flushSnapshot: versioned, expiring read and windowed write of one section.
 * - SNAPSHOT_MAX_AGE_MS: how long a section stays usable.
 * - resetSnapshotForTests
 *
 * [POS]
 * Storage layer of the first-screen snapshot. One envelope under one key holds the sections; an envelope written by another
 * schema or another build is ignored whole, and a section older than SNAPSHOT_MAX_AGE_MS is not returned. A flush re-reads the
 * stored envelope and replaces only the sections this window wrote, so two windows never overwrite each other's sections.
 */
import { isRecord } from '@/lib/utils/typeUtils';

/** The only first-screen data that is stored; a section is added here together with its codec. */
export type SnapshotSectionName = 'chatHistory' | 'projects';

const SECTION_NAMES: readonly SnapshotSectionName[] = ['chatHistory', 'projects'];
const STORAGE_KEY = 'myrm-first-screen-snapshot';
/** Bumped when the stored shape of any section changes. */
const SCHEMA_VERSION = 1;
const APP_BUILD = process.env.NEXT_PUBLIC_APP_BUILD ?? 'dev';
/** Past this age a section no longer says anything about what the user has now. */
export const SNAPSHOT_MAX_AGE_MS = 14 * 24 * 60 * 60 * 1000;
const PERSIST_WINDOW_MS = 1_000;

interface StoredSection {
  savedAt: number;
  data: unknown;
}

interface Envelope {
  schema: number;
  build: string;
  sections: Partial<Record<SnapshotSectionName, StoredSection>>;
}

const pending = new Map<SnapshotSectionName, StoredSection>();
let persistTimer: ReturnType<typeof setTimeout> | null = null;

function emptyEnvelope(): Envelope {
  return { schema: SCHEMA_VERSION, build: APP_BUILD, sections: {} };
}

/** The stored envelope, or null when there is none, it is unreadable, or another schema or build wrote it. */
function readEnvelope(): Envelope | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed: unknown = JSON.parse(raw);
    if (
      !isRecord(parsed) ||
      parsed.schema !== SCHEMA_VERSION ||
      parsed.build !== APP_BUILD ||
      !isRecord(parsed.sections)
    ) {
      return null;
    }
    const envelope = emptyEnvelope();
    for (const name of SECTION_NAMES) {
      const section = parsed.sections[name];
      if (isRecord(section) && typeof section.savedAt === 'number' && Number.isFinite(section.savedAt)) {
        envelope.sections[name] = { savedAt: section.savedAt, data: section.data };
      }
    }
    return envelope;
  } catch {
    return null;
  }
}

/** The stored data of one section, or null when it is missing, expired or dated in the future. */
export function readSnapshotSection(name: SnapshotSectionName, now: number = Date.now()): unknown {
  const section = readEnvelope()?.sections[name];
  if (!section) {
    return null;
  }
  const age = now - section.savedAt;
  return age >= 0 && age <= SNAPSHOT_MAX_AGE_MS ? section.data : null;
}

/** Writes the section within PERSIST_WINDOW_MS of its first change; later calls inside the window replace the data and share that one write. */
export function writeSnapshotSection(name: SnapshotSectionName, data: unknown, now: number = Date.now()): void {
  pending.set(name, { savedAt: now, data });
  if (persistTimer === null) {
    persistTimer = setTimeout(flushSnapshot, PERSIST_WINDOW_MS);
  }
}

/** Writes what is pending right away (the window is going away). */
export function flushSnapshot(): void {
  if (persistTimer !== null) {
    clearTimeout(persistTimer);
    persistTimer = null;
  }
  if (pending.size === 0) {
    return;
  }
  const envelope = readEnvelope() ?? emptyEnvelope();
  for (const [name, section] of pending) {
    envelope.sections[name] = section;
  }
  pending.clear();
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(envelope));
  } catch {
    // Storage is full or denied: the snapshot only speeds the start up, so losing a write costs nothing else.
  }
}

/** @internal test helper */
export function resetSnapshotForTests(): void {
  if (persistTimer !== null) {
    clearTimeout(persistTimer);
    persistTimer = null;
  }
  pending.clear();
}
