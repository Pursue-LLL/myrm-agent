/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { click, resetKit } from './wikiSectionTestKit';
import { WikiPurposeCard } from '../WikiPurposeCard';
import type { WikiPurposeController } from '../useWikiPurpose';

function renderCard(over: Partial<WikiPurposeController> = {}) {
  const controller = {
    purpose: 'saved',
    purposeDraft: 'saved',
    setPurposeDraft: vi.fn(),
    isLoadingPurpose: false,
    isSavingPurpose: false,
    handleSavePurpose: vi.fn(),
    ...over,
  } satisfies WikiPurposeController;
  render(<WikiPurposeCard {...controller} />);
  return controller;
}

const saveButton = () => screen.getByRole('button', { name: 'purpose.save' });

beforeEach(resetKit);
afterEach(cleanup);

describe('WikiPurposeCard', () => {
  it('names the card and explains it', () => {
    renderCard();
    expect(screen.getByText('purpose.title')).toBeTruthy();
    expect(screen.getByText('purpose.description')).toBeTruthy();
  });

  it('shows a placeholder instead of the editor while the purpose loads', () => {
    renderCard({ isLoadingPurpose: true });
    expect(screen.getByText('loading')).toBeTruthy();
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('edits the draft', () => {
    const controller = renderCard({ purposeDraft: 'saved draft' });
    const editor = screen.getByPlaceholderText<HTMLTextAreaElement>('purpose.placeholder');
    expect(editor.value).toBe('saved draft');
    fireEvent.change(editor, { target: { value: 'new direction' } });
    expect(controller.setPurposeDraft).toHaveBeenCalledExactlyOnceWith('new direction');
  });

  it('offers neither save nor reset while the draft equals the saved purpose', () => {
    renderCard();
    expect((saveButton() as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole('button', { name: 'purpose.reset' })).toBeNull();
  });

  it('saves a changed draft and lets the user go back to the saved purpose', async () => {
    const controller = renderCard({ purposeDraft: 'edited' });
    expect((saveButton() as HTMLButtonElement).disabled).toBe(false);
    await click(saveButton());
    expect(controller.handleSavePurpose).toHaveBeenCalledOnce();
    await click(screen.getByRole('button', { name: 'purpose.reset' }));
    expect(controller.setPurposeDraft).toHaveBeenCalledExactlyOnceWith('saved');
  });

  it('locks saving while a save is running and says so', () => {
    renderCard({ purposeDraft: 'edited', isSavingPurpose: true });
    const saving = screen.getByRole('button', { name: 'purpose.saving' }) as HTMLButtonElement;
    expect(saving.disabled).toBe(true);
    expect(screen.queryByRole('button', { name: 'purpose.save' })).toBeNull();
  });
});
