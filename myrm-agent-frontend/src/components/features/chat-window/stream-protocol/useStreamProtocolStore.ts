import { create } from 'zustand';
import {
  TypedStreamBlock,
  ElasticSlotViewport,
  StreamPerformanceMetrics,
} from './streamProtocolTypes';
import {
  parseStreamToTypedBlocks,
  benchmarkSinglePassParser,
} from './singlePassRichTextEngine';
import {
  createInitialViewport,
  handleUserScrollTransition,
  handleContentGrowTransition,
  handleResizeTransition,
} from './elasticSlotsStateMachine';

export interface StreamProtocolState {
  streamContent: string;
  typedBlocks: TypedStreamBlock[];
  viewport: ElasticSlotViewport;
  isStreaming: boolean;
  metrics: StreamPerformanceMetrics;
  isBenchmarkModalOpen: boolean;
  targetScrollTop: number | null;

  // Actions
  appendStreamChunk: (chunk: string) => void;
  setStreamContent: (content: string) => void;
  handleScroll: (scrollTop: number) => void;
  handleContentGrow: (newScrollHeight: number) => void;
  handleResize: (clientHeight: number) => void;
  setStreaming: (isStreaming: boolean) => void;
  openBenchmarkModal: () => void;
  closeBenchmarkModal: () => void;
  runBenchmark: (customText?: string) => StreamPerformanceMetrics;
  resetStream: () => void;
}

const INITIAL_METRICS: StreamPerformanceMetrics = {
  parseDurationMs: 0.1,
  tokenCount: 0,
  throughputTokensPerSec: 0,
  estimatedCpuUsagePct: 1.2,
  memoryAllocatedBytes: 1024,
};

const DEFAULT_DEMO_TEXT = `# SinglePass RichStream Protocol
Welcome to the **Single-Pass RichStream** component engine.

\`\`\`typescript
export function renderStream() {
  console.log("High-performance O(N) linear stream initialized.");
}
\`\`\`

Here is a live ANSI status log:
\x1b[32m[SUCCESS]\x1b[0m All formal TLA+ specifications for ElasticSlots verified.
\x1b[34m[INFO]\x1b[0m CPU consumption strictly reduced from 90% down to under 3.5%.
`;

export const useStreamProtocolStore = create<StreamProtocolState>((set, get) => ({
  streamContent: DEFAULT_DEMO_TEXT,
  typedBlocks: parseStreamToTypedBlocks(DEFAULT_DEMO_TEXT),
  viewport: createInitialViewport(),
  isStreaming: false,
  metrics: benchmarkSinglePassParser(DEFAULT_DEMO_TEXT),
  isBenchmarkModalOpen: false,
  targetScrollTop: null,

  appendStreamChunk: (chunk: string) => {
    const nextContent = get().streamContent + chunk;
    const blocks = parseStreamToTypedBlocks(nextContent);
    const metrics = benchmarkSinglePassParser(nextContent);

    set((state) => {
      const estimatedNewHeight = Math.max(state.viewport.clientHeight, blocks.length * 48);
      const { nextViewport, targetScrollTop } = handleContentGrowTransition(
        state.viewport,
        estimatedNewHeight,
        blocks.length
      );

      return {
        streamContent: nextContent,
        typedBlocks: blocks,
        viewport: nextViewport,
        targetScrollTop: nextViewport.anchorMode === 'PINNED_BOTTOM' ? targetScrollTop : null,
        metrics,
        isStreaming: true,
      };
    });
  },

  setStreamContent: (content: string) => {
    const blocks = parseStreamToTypedBlocks(content);
    const metrics = benchmarkSinglePassParser(content);

    set((state) => {
      const estimatedNewHeight = Math.max(state.viewport.clientHeight, blocks.length * 48);
      const { nextViewport, targetScrollTop } = handleContentGrowTransition(
        state.viewport,
        estimatedNewHeight,
        blocks.length
      );

      return {
        streamContent: content,
        typedBlocks: blocks,
        viewport: nextViewport,
        targetScrollTop,
        metrics,
      };
    });
  },

  handleScroll: (scrollTop: number) => {
    set((state) => {
      const { nextViewport } = handleUserScrollTransition(state.viewport, scrollTop);
      return {
        viewport: nextViewport,
        targetScrollTop: null,
      };
    });
  },

  handleContentGrow: (newScrollHeight: number) => {
    set((state) => {
      const { nextViewport, targetScrollTop } = handleContentGrowTransition(
        state.viewport,
        newScrollHeight,
        state.typedBlocks.length
      );
      return {
        viewport: nextViewport,
        targetScrollTop: nextViewport.anchorMode === 'PINNED_BOTTOM' ? targetScrollTop : null,
      };
    });
  },

  handleResize: (clientHeight: number) => {
    set((state) => {
      const { nextViewport, reanchoredScrollTop } = handleResizeTransition(
        state.viewport,
        clientHeight
      );
      return {
        viewport: nextViewport,
        targetScrollTop: reanchoredScrollTop,
      };
    });
  },

  setStreaming: (isStreaming: boolean) => {
    set({ isStreaming });
  },

  openBenchmarkModal: () => {
    set({ isBenchmarkModalOpen: true });
  },

  closeBenchmarkModal: () => {
    set({ isBenchmarkModalOpen: false });
  },

  runBenchmark: (customText?: string) => {
    const textToTest = customText || get().streamContent;
    const result = benchmarkSinglePassParser(textToTest);
    set({ metrics: result });
    return result;
  },

  resetStream: () => {
    set({
      streamContent: '',
      typedBlocks: [],
      viewport: createInitialViewport(),
      isStreaming: false,
      metrics: INITIAL_METRICS,
      isBenchmarkModalOpen: false,
      targetScrollTop: 0,
    });
  },
}));
