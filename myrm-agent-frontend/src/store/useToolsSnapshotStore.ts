import { create } from 'zustand';
import type { ToolSnapshotItem } from '@/store/chat/types';

interface ToolsSnapshotState {
  tools: ToolSnapshotItem[];
  setTools: (tools: ToolSnapshotItem[]) => void;
  clear: () => void;
}

const useToolsSnapshotStore = create<ToolsSnapshotState>((set) => ({
  tools: [],
  setTools: (tools) => set({ tools }),
  clear: () => set({ tools: [] }),
}));

export default useToolsSnapshotStore;
