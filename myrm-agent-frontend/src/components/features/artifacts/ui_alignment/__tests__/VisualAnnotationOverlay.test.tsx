import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { VisualAnnotationItem } from '../uiAlignmentTypes';
import { useUiAlignmentStore } from '../useUiAlignmentStore';
import { VisualAnnotationOverlay } from '../VisualAnnotationOverlay';

const { stableT } = vi.hoisted(() => ({ stableT: (key: string) => key }));

vi.mock('next-intl', () => ({ useTranslations: () => stableT }));

const saved: VisualAnnotationItem = {
  annotation_id: 'anno_1',
  variant_id: 'var_01',
  x: 10,
  y: 10,
  width: 15,
  height: 10,
  comment: 'Tighten the heading',
  label: 'visual_feedback',
  created_at_ms: 1000,
};

/** Draws a box on the capture surface and types a comment, leaving the dialog ready to save. */
function openDialogWith(comment: string): HTMLTextAreaElement {
  render(<VisualAnnotationOverlay chatId="chat_test" variantId="var_01" annotations={[]} isAnnotating />);
  const surface = screen.getByLabelText('drawingSurfaceLabel');
  fireEvent.mouseDown(surface, { clientX: 10, clientY: 10 });
  fireEvent.mouseUp(surface);
  const box = screen.getByPlaceholderText('commentPlaceholder') as HTMLTextAreaElement;
  fireEvent.change(box, { target: { value: comment } });
  return box;
}

describe('saving a canvas annotation', () => {
  beforeEach(() => {
    useUiAlignmentStore.getState().reset();
  });

  it('keeps a refused comment in the box so it can be edited and saved again', async () => {
    const addAnnotation = vi.fn(async () => null);
    useUiAlignmentStore.setState({ addAnnotation });
    openDialogWith('use key sk-AAAAAABBBBBBCCCCCCDDDD-0');

    fireEvent.click(screen.getByText('submitAnnotation'));

    await waitFor(() => expect(addAnnotation).toHaveBeenCalledTimes(1));
    expect((screen.getByPlaceholderText('commentPlaceholder') as HTMLTextAreaElement).value).toBe(
      'use key sk-AAAAAABBBBBBCCCCCCDDDD-0',
    );
  });

  it('closes the box once the annotation is saved', async () => {
    const addAnnotation = vi.fn(async () => saved);
    useUiAlignmentStore.setState({ addAnnotation });
    openDialogWith('Tighten the heading');

    fireEvent.click(screen.getByText('submitAnnotation'));

    await waitFor(() => expect(screen.queryByPlaceholderText('commentPlaceholder')).toBeNull());
    expect(addAnnotation).toHaveBeenCalledTimes(1);
  });
});
