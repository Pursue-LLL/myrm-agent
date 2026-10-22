import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserAnnotationPinMarker } from '../BrowserAnnotationPinMarker';
import type { BrowserAnnotationPin } from '../browserAnnotationTypes';

describe('BrowserAnnotationPinMarker', () => {
  const mockPin: BrowserAnnotationPin = {
    id: 'pin-101',
    index: 1,
    box: {
      x: 50,
      y: 60,
      width: 120,
      height: 40,
      viewportWidth: 1000,
      viewportHeight: 800,
    },
    comment: 'Fix button text color',
    createdAt: 1700000000000,
    domMetadata: {
      cssSelector: '#app > button.btn-cta',
      tagName: 'button',
      classList: ['btn-cta'],
      sanitizedOuterHtml: '<button class="btn-cta">Click</button>',
      innerText: 'Click',
      computedStyles: { color: 'rgb(0,0,0)' },
      subtreeBranch: '#app',
    },
  };

  it('renders pin number and bounding box correctly', () => {
    const onSelectPin = vi.fn();
    const onUpdateComment = vi.fn();
    const onDeletePin = vi.fn();

    render(
      <BrowserAnnotationPinMarker
        pin={mockPin}
        scaleX={1}
        scaleY={1}
        isActive={false}
        onSelectPin={onSelectPin}
        onUpdateComment={onUpdateComment}
        onDeletePin={onDeletePin}
      />,
    );

    expect(screen.getByTestId('annotation-box-pin-101')).toBeInTheDocument();
    const pinBtn = screen.getByTestId('annotation-pin-pin-101');
    expect(pinBtn).toHaveTextContent('1');
  });

  it('opens popover and triggers onSelectPin when pin is clicked', () => {
    const onSelectPin = vi.fn();
    const onUpdateComment = vi.fn();
    const onDeletePin = vi.fn();

    render(
      <BrowserAnnotationPinMarker
        pin={mockPin}
        scaleX={1}
        scaleY={1}
        isActive={false}
        onSelectPin={onSelectPin}
        onUpdateComment={onUpdateComment}
        onDeletePin={onDeletePin}
      />,
    );

    const pinBtn = screen.getByTestId('annotation-pin-pin-101');
    fireEvent.click(pinBtn);

    expect(onSelectPin).toHaveBeenCalledWith('pin-101');
    expect(screen.getByTestId('annotation-popover-pin-101')).toBeInTheDocument();
    expect(screen.getByText('#app > button.btn-cta')).toBeInTheDocument();
  });

  it('allows editing comment and calls onUpdateComment on save', () => {
    const onSelectPin = vi.fn();
    const onUpdateComment = vi.fn();
    const onDeletePin = vi.fn();

    render(
      <BrowserAnnotationPinMarker
        pin={mockPin}
        scaleX={1}
        scaleY={1}
        isActive={true}
        onSelectPin={onSelectPin}
        onUpdateComment={onUpdateComment}
        onDeletePin={onDeletePin}
      />,
    );

    // Click comment to open textarea
    const commentEl = screen.getByText('Fix button text color');
    fireEvent.click(commentEl);

    const textarea = screen.getByTestId('annotation-textarea-pin-101');
    fireEvent.change(textarea, { target: { value: 'Make text bold and blue' } });

    const saveBtn = screen.getByTestId('save-comment-pin-101');
    fireEvent.click(saveBtn);

    expect(onUpdateComment).toHaveBeenCalledWith('pin-101', 'Make text bold and blue');
  });

  it('calls onDeletePin when delete button is clicked', () => {
    const onSelectPin = vi.fn();
    const onUpdateComment = vi.fn();
    const onDeletePin = vi.fn();

    render(
      <BrowserAnnotationPinMarker
        pin={mockPin}
        scaleX={1}
        scaleY={1}
        isActive={true}
        onSelectPin={onSelectPin}
        onUpdateComment={onUpdateComment}
        onDeletePin={onDeletePin}
      />,
    );

    const deleteBtn = screen.getByTestId('delete-pin-pin-101');
    fireEvent.click(deleteBtn);

    expect(onDeletePin).toHaveBeenCalledWith('pin-101');
  });
});
