import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import useChatStore from '@/store/useChatStore';
import IncognitoModeToggle from '../IncognitoModeToggle';

const mockPush = vi.hoisted(() => vi.fn());
const mockPathname = vi.hoisted(() => ({ value: '/' }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => mockPathname.value,
}));

vi.mock('@/components/primitives/tooltip', () => ({
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const initial = useChatStore.getState();

describe('IncognitoModeToggle', () => {
  beforeEach(() => {
    mockPush.mockClear();
    mockPathname.value = '/';
    useChatStore.setState({
      incognitoMode: initial.incognitoMode,
      chatId: initial.chatId,
      messages: initial.messages,
    });
  });

  afterEach(() => {
    useChatStore.setState({
      incognitoMode: initial.incognitoMode,
      chatId: initial.chatId,
      messages: initial.messages,
    });
  });

  const click = () => fireEvent.click(screen.getByRole('button', { name: 'incognitoMode' }));

  it('starts a fresh chat even when the current one already has a row but no messages', () => {
    // A chat row outlives its messages (/focus soft-deletes them), so an id can point at a row the server will
    // never treat as incognito. Switching must not leave that id in place, or its uploads would be exported.
    useChatStore.setState({ incognitoMode: false, chatId: 'c-old', messages: [] });

    render(<IncognitoModeToggle />);
    click();

    const state = useChatStore.getState();
    expect(state.incognitoMode).toBe(true);
    expect(state.chatId).not.toBe('c-old');
    expect(state.chatId).toMatch(/^c-/);
  });

  it('starts a fresh chat when incognito is switched off again', () => {
    useChatStore.setState({ incognitoMode: true, chatId: 'c-incognito', messages: [] });

    render(<IncognitoModeToggle />);
    click();

    const state = useChatStore.getState();
    expect(state.incognitoMode).toBe(false);
    expect(state.chatId).not.toBe('c-incognito');
  });

  it('leaves a non-home route for the home route so the id and the URL never disagree', () => {
    mockPathname.value = '/chat/c-old';
    useChatStore.setState({ incognitoMode: false, chatId: 'c-old', messages: [] });

    render(<IncognitoModeToggle />);
    click();

    expect(mockPush).toHaveBeenCalledWith('/');
  });

  it('reports the current state through aria-pressed', () => {
    useChatStore.setState({ incognitoMode: true, chatId: 'c-incognito', messages: [] });

    render(<IncognitoModeToggle />);

    expect(screen.getByRole('button', { name: 'incognitoMode' }).getAttribute('aria-pressed')).toBe('true');
  });
});
