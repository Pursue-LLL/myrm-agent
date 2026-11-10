import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import useChatStore from '@/store/useChatStore';
import ContentSidebar from '../ContentSidebar';
import { kit, resetSidebarKit } from './sidebarKit';

vi.mock('next/navigation', async () => (await import('./sidebarKit')).navigationMock());
vi.mock('../ChatSidebarContent', async () => (await import('./sidebarKit')).chatSidebarMock());

const handlers = {
  onToggleCollapse: vi.fn<() => void>(),
  onResizeStart: vi.fn<(event: React.MouseEvent) => void>(),
  onResizeDoubleClick: vi.fn<() => void>(),
  initializeChat: vi.fn<(id?: string) => void>(),
};

type SidebarProps = React.ComponentProps<typeof ContentSidebar>;

function renderSidebar(props: Partial<SidebarProps> = {}) {
  return render(
    <ContentSidebar isCollapsed={false} onToggleCollapse={handlers.onToggleCollapse} navbarWidth={64} {...props} />,
  );
}

const sidebar = (container: HTMLElement) => container.querySelector<HTMLElement>('[data-theme-shell="sidebar"]');
const resizeHandle = (container: HTMLElement) => container.querySelector<HTMLElement>('.cursor-col-resize');

beforeEach(() => {
  resetSidebarKit();
  useChatStore.setState({ initializeChat: handlers.initializeChat });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ContentSidebar when collapsed', () => {
  it('shows only a button that brings the sidebar back, next to the navigation rail', () => {
    const { container } = renderSidebar({ isCollapsed: true, navbarWidth: 72 });

    const button = screen.getByRole('button', { name: 'showSidebar' });
    expect(button).toHaveStyle({ left: '80px' });
    expect(sidebar(container)).toBeNull();
    expect(screen.queryByTestId('chat-sidebar')).toBeNull();

    fireEvent.click(button);
    expect(handlers.onToggleCollapse).toHaveBeenCalledTimes(1);
  });
});

describe('ContentSidebar on a desktop', () => {
  it('sits beside the navigation rail at its default width', () => {
    const { container } = renderSidebar({ navbarWidth: 72 });

    expect(sidebar(container)).toHaveStyle({ left: '72px', width: '280px' });
    expect(screen.getByTestId('chat-sidebar')).toHaveAttribute('data-mobile', 'false');
  });

  it('takes the width it is given', () => {
    const { container } = renderSidebar({ width: 336 });

    expect(sidebar(container)).toHaveStyle({ width: '336px' });
  });

  it('collapses from the sidebar body', () => {
    renderSidebar();

    fireEvent.click(screen.getByRole('button', { name: 'sidebar-collapse' }));

    expect(handlers.onToggleCollapse).toHaveBeenCalledTimes(1);
  });

  it('does not collapse when a chat is chosen', () => {
    renderSidebar();

    expect(kit.chatSidebar.latest?.onMobileItemClick).toBeUndefined();
  });

  it('can be dragged wider by its edge, and reset by a double click', () => {
    const { container } = renderSidebar({
      onResizeStart: handlers.onResizeStart,
      onResizeDoubleClick: handlers.onResizeDoubleClick,
    });
    const handle = resizeHandle(container);
    expect(handle).not.toBeNull();

    fireEvent.mouseDown(handle as HTMLElement);
    fireEvent.doubleClick(handle as HTMLElement);

    expect(handlers.onResizeStart).toHaveBeenCalledTimes(1);
    expect(handlers.onResizeDoubleClick).toHaveBeenCalledTimes(1);
  });

  it('has no edge to drag when nobody listens for it', () => {
    const { container } = renderSidebar();

    expect(resizeHandle(container)).toBeNull();
  });

  it('follows the pointer without animating, and without selecting text, while it is dragged', () => {
    const { container } = renderSidebar({ isDragging: true, onResizeStart: handlers.onResizeStart });

    expect(sidebar(container)).toHaveClass('select-none');
    expect(sidebar(container)).toHaveStyle({ transition: 'none' });
    expect(resizeHandle(container)).toHaveClass('bg-primary/30');
  });

  it('animates its width when it is not being dragged', () => {
    const { container } = renderSidebar({ onResizeStart: handlers.onResizeStart });

    expect(sidebar(container)).not.toHaveClass('select-none');
    expect(sidebar(container)?.style.transition).toBe('');
  });
});

describe('ContentSidebar on a phone', () => {
  it('fills the drawer instead of sitting beside the rail', () => {
    const { container } = renderSidebar({ isMobile: true, width: 336, onResizeStart: handlers.onResizeStart });

    expect(sidebar(container)).toHaveClass('flex-1', 'h-full');
    expect(sidebar(container)?.style.left).toBe('');
    expect(sidebar(container)?.style.width).toBe('');
    expect(screen.getByTestId('chat-sidebar')).toHaveAttribute('data-mobile', 'true');
  });

  it('has no edge to drag', () => {
    const { container } = renderSidebar({ isMobile: true, onResizeStart: handlers.onResizeStart });

    expect(resizeHandle(container)).toBeNull();
  });

  it('closes the drawer when a chat is chosen', () => {
    renderSidebar({ isMobile: true });

    fireEvent.click(screen.getByRole('button', { name: 'sidebar-item' }));

    expect(handlers.onToggleCollapse).toHaveBeenCalledTimes(1);
  });
});

describe('ContentSidebar new chat', () => {
  it('opens the start page and a fresh chat when it is chosen from another page', () => {
    kit.pathname.current = '/c-12';
    renderSidebar();

    fireEvent.click(screen.getByRole('button', { name: 'sidebar-new-chat' }));

    expect(kit.push).toHaveBeenCalledExactlyOnceWith('/');
    expect(handlers.initializeChat).toHaveBeenCalledExactlyOnceWith(undefined);
  });

  it('only resets the chat when it is already on the start page', () => {
    kit.pathname.current = '/';
    renderSidebar();

    fireEvent.click(screen.getByRole('button', { name: 'sidebar-new-chat' }));

    expect(kit.push).not.toHaveBeenCalled();
    expect(handlers.initializeChat).toHaveBeenCalledExactlyOnceWith(undefined);
  });

  it('does not close the drawer by itself, the sidebar body decides when the visit is over', () => {
    renderSidebar({ isMobile: true });

    fireEvent.click(screen.getByRole('button', { name: 'sidebar-new-chat' }));

    expect(handlers.onToggleCollapse).not.toHaveBeenCalled();
  });

  it('keeps the same handler across renders, so the memoized sidebar body is not redrawn for nothing', () => {
    const { rerender } = renderSidebar();
    const first = kit.chatSidebar.latest?.onNewChat;

    act(() => {
      rerender(
        <ContentSidebar
          isCollapsed={false}
          onToggleCollapse={handlers.onToggleCollapse}
          navbarWidth={64}
          width={300}
        />,
      );
    });

    expect(kit.chatSidebar.latest?.onNewChat).toBe(first);
  });
});
