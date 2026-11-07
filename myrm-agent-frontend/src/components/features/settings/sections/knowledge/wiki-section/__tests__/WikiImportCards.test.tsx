/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { createRef } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { click, resetKit } from './wikiSectionTestKit';
import { stubProps } from './wikiSectionStubs';
import { WikiBatchImportCard } from '../WikiBatchImportCard';
import { WikiImportDialogs } from '../WikiImportDialogs';
import { WikiObsidianImportCard } from '../WikiObsidianImportCard';

type BatchProps = Parameters<typeof WikiBatchImportCard>[0];
type ObsidianProps = Parameters<typeof WikiObsidianImportCard>[0];
type DialogImports = Parameters<typeof WikiImportDialogs>[0]['imports'];

function renderBatch(over: Partial<BatchProps> = {}) {
  const props: BatchProps = {
    isTauriEnv: false,
    isImporting: false,
    zipInputRef: createRef<HTMLInputElement>(),
    webFolderInputRef: createRef<HTMLInputElement>(),
    handleImportFolder: vi.fn(),
    handleImportZip: vi.fn(),
    handleWebFolderSelect: vi.fn(),
    setUrlImportDialogOpen: vi.fn(),
    setVideoImportDialogOpen: vi.fn(),
    ...over,
  };
  const { container } = render(<WikiBatchImportCard {...props} />);
  return { props, container };
}

function renderObsidian(over: Partial<ObsidianProps> = {}) {
  const props: ObsidianProps = {
    isTauriEnv: false,
    isImportingObsidian: false,
    obsidianZipRef: createRef<HTMLInputElement>(),
    handleImportObsidianFolder: vi.fn(),
    handleImportObsidianZip: vi.fn(),
    ...over,
  };
  const { container } = render(<WikiObsidianImportCard {...props} />);
  return { props, container };
}

const fileInputs = (container: HTMLElement) => [...container.querySelectorAll<HTMLInputElement>('input[type="file"]')];
const button = (name: string) => screen.getByRole<HTMLButtonElement>('button', { name });

beforeEach(resetKit);
afterEach(cleanup);

describe('WikiBatchImportCard', () => {
  it('names the card and offers the four ways to import', () => {
    renderBatch();
    expect(screen.getByText('import.title')).toBeTruthy();
    expect(screen.getByText('import.description')).toBeTruthy();
    expect(screen.getAllByRole('button').map((node) => node.textContent)).toEqual([
      'import.folder',
      'import.zip',
      'import.urls',
      'import.video',
    ]);
  });

  it('imports a folder, opens the link dialog and opens the video dialog', async () => {
    const { props } = renderBatch();
    await click(button('import.folder'));
    expect(props.handleImportFolder).toHaveBeenCalledOnce();
    await click(button('import.urls'));
    expect(props.setUrlImportDialogOpen).toHaveBeenCalledExactlyOnceWith(true);
    await click(button('import.video'));
    expect(props.setVideoImportDialogOpen).toHaveBeenCalledExactlyOnceWith(true);
    expect(props.setUrlImportDialogOpen).toHaveBeenCalledOnce();
  });

  it('opens the hidden archive picker from the ZIP button', async () => {
    const { props, container } = renderBatch();
    const archivePicker = props.zipInputRef.current;
    expect(archivePicker).toBe(fileInputs(container)[0]);
    const pick = vi.spyOn(archivePicker as HTMLInputElement, 'click');
    await click(button('import.zip'));
    expect(pick).toHaveBeenCalledOnce();
  });

  it('keeps an archive picker that takes ZIP files and reports what is chosen', () => {
    const { props, container } = renderBatch();
    const [archivePicker] = fileInputs(container);
    expect(archivePicker.accept).toBe('.zip');
    expect(archivePicker.className).toContain('hidden');
    fireEvent.change(archivePicker, { target: { files: [] } });
    expect(props.handleImportZip).toHaveBeenCalledOnce();
  });

  it('adds a folder picker in the browser that reports what is chosen', () => {
    const { props, container } = renderBatch();
    const pickers = fileInputs(container);
    expect(pickers).toHaveLength(2);
    expect(props.webFolderInputRef.current).toBe(pickers[1]);
    expect(pickers[1].hasAttribute('webkitdirectory')).toBe(true);
    expect(pickers[1].className).toContain('hidden');
    fireEvent.change(pickers[1], { target: { files: [] } });
    expect(props.handleWebFolderSelect).toHaveBeenCalledOnce();
  });

  it('has no folder picker in the desktop app, which uses its own dialog', () => {
    const { props, container } = renderBatch({ isTauriEnv: true });
    expect(fileInputs(container)).toHaveLength(1);
    expect(props.webFolderInputRef.current).toBeNull();
  });

  it('locks every entry while an import runs, and says so on the two that do the import', () => {
    renderBatch({ isImporting: true });
    expect(screen.getAllByText('import.importing')).toHaveLength(2);
    expect(screen.getAllByRole<HTMLButtonElement>('button').map((node) => node.disabled)).toEqual([
      true,
      true,
      true,
      true,
    ]);
    expect(button('import.urls')).toBeTruthy();
    expect(button('import.video')).toBeTruthy();
  });

  it('leaves every entry usable when idle', () => {
    renderBatch();
    expect(screen.getAllByRole<HTMLButtonElement>('button').map((node) => node.disabled)).toEqual([
      false,
      false,
      false,
      false,
    ]);
  });
});

describe('WikiObsidianImportCard', () => {
  it('is the anchor the migration handoff scrolls to, with its title and description', () => {
    const { container } = renderObsidian();
    expect(container.firstElementChild?.id).toBe('wiki-obsidian-import');
    expect(screen.getByText('import.obsidianTitle')).toBeTruthy();
    expect(screen.getByText('import.obsidianDescription')).toBeTruthy();
  });

  it('offers only the archive import in the browser', () => {
    renderObsidian();
    expect(screen.getAllByRole('button').map((node) => node.textContent)).toEqual(['import.obsidianZip']);
  });

  it('adds the vault folder import in the desktop app and starts it', async () => {
    const { props } = renderObsidian({ isTauriEnv: true });
    expect(screen.getAllByRole('button').map((node) => node.textContent)).toEqual([
      'import.obsidianFolder',
      'import.obsidianZip',
    ]);
    await click(button('import.obsidianFolder'));
    expect(props.handleImportObsidianFolder).toHaveBeenCalledOnce();
  });

  it('opens the hidden archive picker from the ZIP button and reports what is chosen', async () => {
    const { props, container } = renderObsidian();
    const [archivePicker] = fileInputs(container);
    expect(props.obsidianZipRef.current).toBe(archivePicker);
    expect(archivePicker.accept).toBe('.zip');
    expect(archivePicker.className).toContain('hidden');
    const pick = vi.spyOn(archivePicker, 'click');
    await click(button('import.obsidianZip'));
    expect(pick).toHaveBeenCalledOnce();
    fireEvent.change(archivePicker, { target: { files: [] } });
    expect(props.handleImportObsidianZip).toHaveBeenCalledOnce();
  });

  it('locks every entry while the import runs, and says so', () => {
    renderObsidian({ isTauriEnv: true, isImportingObsidian: true });
    const buttons = screen.getAllByRole<HTMLButtonElement>('button');
    expect(buttons.map((node) => node.textContent)).toEqual(['import.importing', 'import.importing']);
    expect(buttons.map((node) => node.disabled)).toEqual([true, true]);
  });

  it('leaves every entry usable when idle', () => {
    renderObsidian({ isTauriEnv: true });
    expect(screen.getAllByRole<HTMLButtonElement>('button').map((node) => node.disabled)).toEqual([false, false]);
  });
});

describe('WikiImportDialogs', () => {
  const imports = (): DialogImports => ({
    importConflictOpen: true,
    importConflictPaths: ['a.md'],
    dismissImportConflict: vi.fn(),
    keepSkippedImports: vi.fn(),
    retryImportWithSupersede: vi.fn(),
    importSecurityOpen: false,
    importSecurityBlockedPaths: ['secret.md'],
    importSecurityRedactedPaths: ['token.md'],
    dismissImportSecurity: vi.fn(),
    urlImportDialogOpen: true,
    setUrlImportDialogOpen: vi.fn(),
    handleUrlImportFinished: vi.fn(),
    videoImportDialogOpen: false,
    setVideoImportDialogOpen: vi.fn(),
    handleVideoImportFinished: vi.fn(),
  });

  it('wires the conflict dialog to its paths and the three ways to answer it', () => {
    const wiring = imports();
    render(<WikiImportDialogs agentScopeId="a1" imports={wiring} />);
    expect(stubProps('WikiImportConflictDialog')).toMatchObject({
      open: true,
      conflictPaths: ['a.md'],
      onClose: wiring.dismissImportConflict,
      onKeepSkipped: wiring.keepSkippedImports,
      onSupersede: wiring.retryImportWithSupersede,
    });
  });

  it('wires the security dialog to what was blocked and redacted', () => {
    const wiring = imports();
    render(<WikiImportDialogs agentScopeId="a1" imports={wiring} />);
    expect(stubProps('WikiImportSecurityDialog')).toMatchObject({
      open: false,
      blockedPaths: ['secret.md'],
      redactedPaths: ['token.md'],
      onClose: wiring.dismissImportSecurity,
    });
  });

  it('wires the link and video dialogs to their switches, the scope and their finish handlers', () => {
    const wiring = imports();
    render(<WikiImportDialogs agentScopeId="a1" imports={wiring} />);
    expect(stubProps('WikiUrlImportDialog')).toMatchObject({
      open: true,
      onOpenChange: wiring.setUrlImportDialogOpen,
      agentScopeId: 'a1',
      onImportFinished: wiring.handleUrlImportFinished,
    });
    expect(stubProps('WikiVideoImportDialog')).toMatchObject({
      open: false,
      onOpenChange: wiring.setVideoImportDialogOpen,
      agentScopeId: 'a1',
      onImportFinished: wiring.handleVideoImportFinished,
    });
  });

  it('opens each dialog from its own switch', () => {
    const wiring: DialogImports = {
      ...imports(),
      importConflictOpen: false,
      importSecurityOpen: true,
      urlImportDialogOpen: false,
      videoImportDialogOpen: true,
    };
    render(<WikiImportDialogs agentScopeId="a1" imports={wiring} />);
    expect(
      ['WikiImportConflictDialog', 'WikiImportSecurityDialog', 'WikiUrlImportDialog', 'WikiVideoImportDialog'].map(
        (name) => stubProps(name).open,
      ),
    ).toEqual([false, true, false, true]);
  });

  it('passes the default scope on as null', () => {
    render(<WikiImportDialogs agentScopeId={null} imports={imports()} />);
    expect(stubProps('WikiUrlImportDialog').agentScopeId).toBeNull();
    expect(stubProps('WikiVideoImportDialog').agentScopeId).toBeNull();
  });
});
