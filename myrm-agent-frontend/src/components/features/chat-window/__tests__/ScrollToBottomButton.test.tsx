'use client';

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next-intl', () => ({
  useTranslations: (ns: string) => (key: string) => `${ns}.${key}`,
}));

import ScrollToBottomButton from '../ScrollToBottomButton';

describe('ScrollToBottomButton', () => {
  const defaultProps = {
    visible: true,
    hasNewMessage: false,
    onClick: vi.fn(),
  };

  it('renders nothing when visible=false', () => {
    const { container } = render(
      <ScrollToBottomButton {...defaultProps} visible={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders a button when visible=true', () => {
    render(<ScrollToBottomButton {...defaultProps} />);
    const btn = screen.getByRole('button');
    expect(btn).toBeInTheDocument();
  });

  it('calls onClick when clicked', () => {
    const onClick = vi.fn();
    render(<ScrollToBottomButton {...defaultProps} onClick={onClick} />);
    fireEvent.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('shows "scrollToBottom" aria-label by default', () => {
    render(<ScrollToBottomButton {...defaultProps} />);
    expect(screen.getByLabelText('chat.scrollCue.scrollToBottom')).toBeInTheDocument();
  });

  it('shows "newMessage" aria-label and text when hasNewMessage=true', () => {
    render(<ScrollToBottomButton {...defaultProps} hasNewMessage={true} />);
    expect(screen.getByLabelText('chat.scrollCue.newMessage')).toBeInTheDocument();
    expect(screen.getByText('chat.scrollCue.newMessage')).toBeInTheDocument();
  });

  it('does not show message text when hasNewMessage=false', () => {
    render(<ScrollToBottomButton {...defaultProps} />);
    expect(screen.queryByText('chat.scrollCue.newMessage')).not.toBeInTheDocument();
  });

  it('applies primary styling when hasNewMessage=true', () => {
    render(<ScrollToBottomButton {...defaultProps} hasNewMessage={true} />);
    const btn = screen.getByRole('button');
    expect(btn.className).toContain('bg-primary');
  });

  it('applies background styling when hasNewMessage=false', () => {
    render(<ScrollToBottomButton {...defaultProps} />);
    const btn = screen.getByRole('button');
    expect(btn.className).toContain('bg-background/90');
  });

  it('renders ArrowDown icon', () => {
    const { container } = render(<ScrollToBottomButton {...defaultProps} />);
    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();
  });
});
