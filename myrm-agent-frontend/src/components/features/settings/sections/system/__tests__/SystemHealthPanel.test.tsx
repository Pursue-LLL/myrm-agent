/** @vitest-environment jsdom */
/**
 * [INPUT]
 * ../SystemHealthPanel::SystemHealthPanel (POS: Developer settings bundle health diagnostics panel)
 * @/services/contextBundle::getContextBundleHealth (POS: Context bundle health API client)
 *
 * [OUTPUT]
 * SystemHealthPanel tests: scene card labels, offload scene path, unknown-scene fallback, meta line contents.
 *
 * [POS]
 * Developer System Health panel regression tests. Pin the scene set the panel labels (memory/workspace/offload)
 * and the raw-name fallback for any scene the labels do not cover.
 */
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getContextBundleHealth, type ContextBundleHealth } from '@/services/contextBundle';
import SystemHealthPanel from '../SystemHealthPanel';

const translations: Record<string, string> = {
  title: 'System health',
  description: 'Context bundle health',
  refresh: 'Refresh',
  loading: 'Loading',
  writable: 'Writable',
  notWritable: 'Not writable',
  manifestOk: 'Manifest present',
  manifestMissing: 'Manifest missing',
  meta: 'Deploy: {deploy} · Bundle: {bundle}',
  memoryPath: 'Memory root',
  harnessPath: 'Harness root',
  'status.ready': 'Healthy',
  'status.degraded': 'Degraded',
  'status.missing': 'Critical',
  'sceneStatus.ready': 'Ready',
  'sceneStatus.degraded': 'Limited',
  'sceneStatus.missing': 'Missing',
  'scenes.memory': 'Memory',
  'scenes.workspace': 'Workspace',
  'scenes.offload': 'Context offload',
};

const stableT = (key: string, values?: Record<string, string>) =>
  Object.entries(values ?? {}).reduce(
    (text, [name, value]) => text.replace(`{${name}}`, value),
    translations[key] ?? key,
  );

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/contextBundle', () => ({
  getContextBundleHealth: vi.fn(),
  applyContextBundleMigration: vi.fn(),
}));

const makeHealth = (scenes: ContextBundleHealth['scenes']): ContextBundleHealth => ({
  bundle_id: 'bundle-1',
  schema_version: 1,
  volume_layout_version: 1,
  state_dir: '/data/state',
  memory_base_path: '/data/state/memory',
  harness_dir: '/data/state/harness',
  writable: true,
  manifest_exists: true,
  deploy_mode: 'local',
  scenes,
  migration_actions_pending: 0,
  warnings: [],
});

describe('SystemHealthPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('labels the memory, workspace and offload scenes and shows where offloads are written', async () => {
    vi.mocked(getContextBundleHealth).mockResolvedValue(
      makeHealth([
        { scene: 'memory', path: '/data/state/memory', index_status: 'ready' },
        { scene: 'workspace', path: '/data/state/harness', index_status: 'ready' },
        { scene: 'offload', path: '/data/.context', index_status: 'ready' },
      ]),
    );

    render(<SystemHealthPanel />);

    await waitFor(() => {
      expect(screen.getByText('Context offload')).toBeInTheDocument();
    });
    expect(screen.getByText('Memory')).toBeInTheDocument();
    expect(screen.getByText('Workspace')).toBeInTheDocument();
    expect(screen.getByText('/data/.context')).toBeInTheDocument();
    expect(screen.getByText('Deploy: local · Bundle: bundle-1')).toBeInTheDocument();
  });

  it('falls back to the raw scene name for a scene without a label', async () => {
    vi.mocked(getContextBundleHealth).mockResolvedValue(
      makeHealth([{ scene: 'archive', path: '/data/archive', index_status: 'degraded' }]),
    );

    render(<SystemHealthPanel />);

    await waitFor(() => {
      expect(screen.getByText('archive')).toBeInTheDocument();
    });
    expect(screen.getByText('Limited')).toBeInTheDocument();
  });
});
