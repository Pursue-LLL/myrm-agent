import { beforeEach, describe, expect, it } from 'vitest';

import {
  canDeepLinkMigrationSource,
  getMigrationSourceDisplayName,
  registerMigrationSourceManifest,
  resolveMigrationImportSource,
  type MigrationSourceManifestItem,
} from '@/services/migrationDiscovery';

const MANIFEST: MigrationSourceManifestItem[] = [
  {
    id: 'hermes',
    display_name: 'Hermes',
    import_source: 'hermes',
    discover_modes: ['local_scan'],
    deep_link_enabled: true,
  },
  {
    id: 'gbrain',
    display_name: 'GBrain',
    import_source: 'gbrain',
    discover_modes: [],
    deep_link_enabled: false,
  },
];

describe('migrationDiscovery source manifest helpers', () => {
  beforeEach(() => {
    registerMigrationSourceManifest(MANIFEST);
  });

  it('returns manifest display names when present', () => {
    expect(getMigrationSourceDisplayName('hermes')).toBe('Hermes');
    expect(getMigrationSourceDisplayName('gbrain')).toBe('GBrain');
  });

  it('resolves import source from manifest', () => {
    expect(resolveMigrationImportSource('hermes')).toBe('hermes');
    expect(resolveMigrationImportSource('gbrain')).toBe('gbrain');
  });

  it('falls back safely for unknown source ids', () => {
    expect(resolveMigrationImportSource('unknown_vendor')).toBe('auto');
    expect(getMigrationSourceDisplayName('unknown_vendor')).toBe('unknown_vendor');
    expect(canDeepLinkMigrationSource('unknown_vendor')).toBe(false);
  });

  it('honors manifest deep-link capability flags', () => {
    expect(canDeepLinkMigrationSource('hermes')).toBe(true);
    expect(canDeepLinkMigrationSource('gbrain')).toBe(false);
  });

  it('keeps default source coverage when payload is partial', () => {
    registerMigrationSourceManifest([
      {
        id: 'gbrain',
        display_name: 'GBrain',
        import_source: 'gbrain',
        discover_modes: [],
        deep_link_enabled: false,
      },
    ]);
    expect(resolveMigrationImportSource('chatgpt')).toBe('chatgpt');
    expect(canDeepLinkMigrationSource('chatgpt')).toBe(true);
  });

  it('replaces defaults when server marks payload authoritative', () => {
    registerMigrationSourceManifest(
      [
        {
          id: 'gbrain',
          display_name: 'GBrain',
          import_source: 'gbrain',
          discover_modes: [],
          deep_link_enabled: false,
        },
      ],
      { authoritative: true },
    );
    expect(resolveMigrationImportSource('chatgpt')).toBe('auto');
    expect(canDeepLinkMigrationSource('chatgpt')).toBe(false);
    expect(resolveMigrationImportSource('gbrain')).toBe('gbrain');
  });

  it('ignores empty authoritative payloads to avoid accidental wipe', () => {
    registerMigrationSourceManifest([], { authoritative: true });
    expect(resolveMigrationImportSource('chatgpt')).toBe('chatgpt');
    expect(resolveMigrationImportSource('gbrain')).toBe('gbrain');
  });
});
