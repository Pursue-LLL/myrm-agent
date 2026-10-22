import { describe, it, expect, beforeEach } from 'vitest';
import { useMigrationWizardStore } from '../useMigrationWizardStore';

describe('useMigrationWizardStore', () => {
  beforeEach(() => {
    useMigrationWizardStore.getState().resetState();
  });

  it('initializes with detected ecosystem assets and visible banner', () => {
    const store = useMigrationWizardStore.getState();
    expect(store.isBannerVisible).toBe(true);
    expect(store.isDrawerOpen).toBe(false);
    expect(store.radarReport.hasDetectedAssets).toBe(true);
    expect(store.radarReport.agents).toHaveLength(3);
    expect(store.radarReport.skills).toHaveLength(3);
    expect(store.radarReport.mcpServers).toHaveLength(2);
    expect(store.progress.status).toBe('idle');
  });

  it('toggles selection of individual assets', () => {
    const store = useMigrationWizardStore.getState();
    const targetAgentId = 'agent-oc-01';

    // 默认是选中的
    expect(store.radarReport.agents.find((a) => a.id === targetAgentId)?.selected).toBe(true);

    store.toggleAssetSelection('agents', targetAgentId);
    expect(
      useMigrationWizardStore
        .getState()
        .radarReport.agents.find((a) => a.id === targetAgentId)?.selected
    ).toBe(false);

    store.toggleAssetSelection('agents', targetAgentId);
    expect(
      useMigrationWizardStore
        .getState()
        .radarReport.agents.find((a) => a.id === targetAgentId)?.selected
    ).toBe(true);
  });

  it('supports selectAll and deselectAll across all asset categories', () => {
    const store = useMigrationWizardStore.getState();

    store.selectAll(false);
    const report1 = useMigrationWizardStore.getState().radarReport;
    expect(report1.agents.every((a) => !a.selected)).toBe(true);
    expect(report1.skills.every((s) => !s.selected)).toBe(true);
    expect(report1.mcpServers.every((m) => !m.selected)).toBe(true);

    store.selectAll(true);
    const report2 = useMigrationWizardStore.getState().radarReport;
    expect(report2.agents.every((a) => a.selected)).toBe(true);
    expect(report2.skills.every((s) => s.selected)).toBe(true);
    expect(report2.mcpServers.every((m) => m.selected)).toBe(true);
  });

  it('executes zero-loss migration pipeline and marks completion', async () => {
    const store = useMigrationWizardStore.getState();
    const totalAssets = store.radarReport.totalAssetsCount;

    await store.startMigration();

    const updated = useMigrationWizardStore.getState();
    expect(updated.progress.status).toBe('completed');
    expect(updated.progress.progressPercentage).toBe(100);
    expect(updated.progress.migratedCount).toBe(totalAssets);
    expect(updated.isBannerVisible).toBe(false);
  });

  it('manages drawer and banner visibility', () => {
    const store = useMigrationWizardStore.getState();
    expect(store.isDrawerOpen).toBe(false);

    store.openDrawer();
    expect(useMigrationWizardStore.getState().isDrawerOpen).toBe(true);

    store.closeDrawer();
    expect(useMigrationWizardStore.getState().isDrawerOpen).toBe(false);

    store.dismissBanner();
    expect(useMigrationWizardStore.getState().isBannerVisible).toBe(false);
  });
});
