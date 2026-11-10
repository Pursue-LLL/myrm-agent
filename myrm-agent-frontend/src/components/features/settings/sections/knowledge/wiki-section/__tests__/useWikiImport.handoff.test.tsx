/** @vitest-environment jsdom */
import { act, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ObsidianImportResultResponse } from '@/services/wikiService';
import { deferred } from '@/test-utils/deferred';
import { settle } from '@/test-utils/fakeClock';
import { consumeHandoff, resetKit, service, toast, toastTexts } from './wikiSectionTestKit';
import { obsidianResultOf } from './wikiSectionFixtures';
import { renderImport } from './wikiImportBench';

const ANCHOR = '#wiki-obsidian-import';
const ANCHOR_ID = 'wiki-obsidian-import';
let consoleError: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  resetKit();
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  document.getElementById(ANCHOR_ID)?.remove();
  vi.restoreAllMocks();
});

/** 页面上的 Obsidian 导入卡片，滚动请求记录在返回的 spy 上。 */
function mountImportCard() {
  const card = document.createElement('div');
  card.id = ANCHOR_ID;
  const scrollIntoView = vi.fn();
  Object.defineProperty(card, 'scrollIntoView', { value: scrollIntoView });
  document.body.append(card);
  return scrollIntoView;
}

describe('useWikiImport: migration vault handoff', () => {
  it('stays out of the way unless the URL points at the import card', async () => {
    consumeHandoff.mockReturnValue({ vaultPath: '/vault' });
    renderImport();
    await settle();
    expect(consumeHandoff).not.toHaveBeenCalled();
    expect(service.importObsidianFolder).not.toHaveBeenCalled();
  });

  it.each([[null], [{}], [{ vaultPath: '' }]])('does nothing when the handoff has no vault (%j)', async (handoff) => {
    window.location.hash = ANCHOR;
    consumeHandoff.mockReturnValue(handoff);
    const bench = renderImport();
    await settle();
    expect(consumeHandoff).toHaveBeenCalledOnce();
    expect(toast.message).not.toHaveBeenCalled();
    expect(service.importObsidianFolder).not.toHaveBeenCalled();
    expect(bench.current().isImportingObsidian).toBe(false);
  });

  it.each([
    [null, undefined],
    ['a1', 'a1'],
  ])('asks for the handoff of the current scope (%s)', async (scope, expected) => {
    window.location.hash = ANCHOR;
    renderImport(scope);
    await settle();
    expect(consumeHandoff).toHaveBeenCalledExactlyOnceWith(expected);
  });

  it('imports the handed-over vault, tells the user and scrolls to the card', async () => {
    window.location.hash = ANCHOR;
    consumeHandoff.mockReturnValue({ vaultPath: '/vault' });
    const scrollIntoView = mountImportCard();
    const pending = deferred<ObsidianImportResultResponse>();
    service.importObsidianFolder.mockReturnValue(pending.promise);
    const bench = renderImport('a1');
    await settle();
    expect(scrollIntoView).toHaveBeenCalledExactlyOnceWith({ behavior: 'smooth', block: 'start' });
    expect(toastTexts('message')).toEqual(['import.migrationVaultHandoff|{"path":"/vault"}']);
    expect(service.importObsidianFolder).toHaveBeenCalledExactlyOnceWith('/vault', true, 'a1');
    expect(bench.current().isImportingObsidian).toBe(true);
    expect(bench.current().isImporting).toBe(false);

    pending.resolve(obsidianResultOf());
    await settle();
    expect(bench.current().isImportingObsidian).toBe(false);
    expect(toastTexts('success')).toEqual(['import.obsidianResult|{"processed":5,"tags":2,"images":1,"skipped":1}']);
    expect(toast.message).toHaveBeenNthCalledWith(2, 'obsidianVault.postWorkflowHint', {
      action: { label: 'obsidianVault.postWorkflowAction', onClick: bench.goToKnowledgeGraph },
    });
    expect(toast.message).toHaveBeenNthCalledWith(3, 'import.dedupScanStarted');
    expect(bench.handleWikiTabChange).toHaveBeenCalledExactlyOnceWith('duplicateReview');
    expect(bench.overview.loadStats).toHaveBeenCalledOnce();
  });

  it('imports even when the card is not on the page', async () => {
    window.location.hash = ANCHOR;
    consumeHandoff.mockReturnValue({ vaultPath: '/vault' });
    renderImport();
    await settle();
    expect(service.importObsidianFolder).toHaveBeenCalledExactlyOnceWith('/vault', true, null);
  });

  it('lets the user replace conflicting notes of the handed-over vault', async () => {
    window.location.hash = ANCHOR;
    consumeHandoff.mockReturnValue({ vaultPath: '/vault' });
    service.importObsidianFolder.mockResolvedValueOnce(obsidianResultOf({ conflict_paths: ['a.md'] }));
    const bench = renderImport('a1');
    await settle();
    expect(bench.current().importConflictOpen).toBe(true);
    expect(bench.current().importConflictPaths).toEqual(['a.md']);
    await act(() => bench.current().retryImportWithSupersede('newer notes'));
    expect(service.importObsidianFolder).toHaveBeenLastCalledWith('/vault', true, 'a1', {
      onConflict: 'supersede',
      supersedeReason: 'newer notes',
    });
  });

  it('reports a failed handoff import without logging noise and stops showing it as running', async () => {
    window.location.hash = ANCHOR;
    consumeHandoff.mockReturnValue({ vaultPath: '/vault' });
    service.importObsidianFolder.mockRejectedValue(new Error('network'));
    const bench = renderImport();
    await settle();
    expect(toastTexts('error')).toEqual(['import.migrationVaultHandoffFailed']);
    expect(bench.current().isImportingObsidian).toBe(false);
    expect(consoleError).not.toHaveBeenCalled();
    expect(bench.handleWikiTabChange).not.toHaveBeenCalled();
  });

  it('reports a refusal from the server like a manual import', async () => {
    window.location.hash = ANCHOR;
    consumeHandoff.mockReturnValue({ vaultPath: '/vault' });
    service.importObsidianFolder.mockResolvedValue(obsidianResultOf({ success: false, message: 'Not a vault' }));
    const bench = renderImport();
    await settle();
    expect(toastTexts('error')).toEqual(['errors.importFailed']);
    expect(bench.current().isImportingObsidian).toBe(false);
  });

  it('imports a handoff only once, even after the scope changes', async () => {
    window.location.hash = ANCHOR;
    consumeHandoff.mockReturnValue({ vaultPath: '/vault' });
    const bench = renderImport('a1');
    await settle();
    bench.rerenderWithScope('a2');
    await settle();
    expect(consumeHandoff).toHaveBeenCalledOnce();
    expect(service.importObsidianFolder).toHaveBeenCalledOnce();
  });

  it('keeps looking for a handoff after an empty one, as the scope changes', async () => {
    window.location.hash = ANCHOR;
    const bench = renderImport('a1');
    await settle();
    expect(consumeHandoff).toHaveBeenLastCalledWith('a1');
    consumeHandoff.mockReturnValue({ vaultPath: '/vault' });
    bench.rerenderWithScope('a2');
    await settle();
    expect(consumeHandoff).toHaveBeenCalledTimes(2);
    expect(consumeHandoff).toHaveBeenLastCalledWith('a2');
    expect(service.importObsidianFolder).toHaveBeenCalledExactlyOnceWith('/vault', true, 'a2');
  });
});
