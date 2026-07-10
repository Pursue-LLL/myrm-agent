'use client';

import { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import useWorkspaceStore from '@/store/useWorkspaceStore';
import { cn } from '@/lib/utils/classnameUtils';
import { X, Plus, LayoutDashboard } from 'lucide-react';

export default function TabBar() {
  const router = useRouter();
  const pathname = usePathname();
  const { panes, activePaneId, addPane, removePane, setActivePaneId } = useWorkspaceStore();

  // Sync URL with active pane
  useEffect(() => {
    if (pathname === '/work') return; // Dashboard view
    
    const chatId = pathname === '/' ? null : pathname.replace('/', '');
    let pane = panes.find(p => p.chatId === chatId);
    
    if (!pane) {
      // If we navigated to a URL not in our panes, add it
      const newPaneId = addPane(chatId || undefined, chatId ? `Chat ${chatId.substring(0, 4)}` : 'New Chat');
      setActivePaneId(newPaneId);
    } else if (pane.id !== activePaneId) {
      setActivePaneId(pane.id);
    }
  }, [pathname]);

  const handleTabClick = (paneId: string, chatId: string | null) => {
    setActivePaneId(paneId);
    if (chatId) {
      router.push(`/${chatId}`);
    } else {
      router.push('/');
    }
  };

  const handleCloseTab = (e: React.MouseEvent, paneId: string) => {
    e.stopPropagation();
    removePane(paneId);
    // The store automatically selects the first available pane
    // We need to sync the URL
    const nextPane = useWorkspaceStore.getState().panes.find(p => p.id === useWorkspaceStore.getState().activePaneId);
    if (nextPane) {
      router.push(nextPane.chatId ? `/${nextPane.chatId}` : '/');
    } else {
      router.push('/');
    }
  };

  const handleAddTab = () => {
    router.push('/');
  };

  return (
    <div className="flex items-center h-10 bg-muted/30 border-b border-border px-2 overflow-x-auto no-scrollbar">
      <button
        onClick={() => router.push('/work')}
        className={cn(
          "flex items-center justify-center w-10 h-8 rounded-md mr-2 flex-shrink-0 transition-colors",
          pathname === '/work' ? "bg-background shadow-sm text-primary" : "text-muted-foreground hover:bg-muted/50"
        )}
        title="Dashboard"
      >
        <LayoutDashboard size={16} />
      </button>

      {panes.map(pane => (
        <div
          key={pane.id}
          onClick={() => handleTabClick(pane.id, pane.chatId)}
          className={cn(
            "group flex items-center h-8 px-3 mx-1 rounded-md min-w-[120px] max-w-[200px] cursor-pointer select-none transition-all flex-shrink-0",
            activePaneId === pane.id 
              ? "bg-background shadow-sm text-foreground border border-border/50" 
              : "text-muted-foreground hover:bg-muted/50 border border-transparent"
          )}
        >
          <div className="flex-1 truncate text-sm font-medium">
            {pane.title}
          </div>
          <button
            onClick={(e) => handleCloseTab(e, pane.id)}
            className="ml-2 p-0.5 rounded-sm opacity-0 group-hover:opacity-100 hover:bg-muted-foreground/20 transition-opacity"
          >
            <X size={14} />
          </button>
        </div>
      ))}

      <button
        onClick={handleAddTab}
        className="flex items-center justify-center w-8 h-8 rounded-md ml-1 flex-shrink-0 text-muted-foreground hover:bg-muted/50 transition-colors"
      >
        <Plus size={16} />
      </button>
    </div>
  );
}
