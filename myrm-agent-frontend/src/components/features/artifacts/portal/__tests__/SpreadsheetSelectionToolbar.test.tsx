import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';

const mockSendMessage = vi.fn();
const mockSetTarget = vi.fn();
const mockAddMentionReference = vi.fn();
const mockWriteToClipboard = vi.fn();

vi.mock('@/store/useChatStore', () => {
  const getState = () => ({
    chatId: 'test-chat-1',
    loading: false,
    sendMessage: mockSendMessage,
    addMentionReference: mockAddMentionReference,
  });
  return {
    default: Object.assign((selector: (s: Record<string, unknown>) => unknown) => selector(getState()), {
      getState,
    }),
  };
});

vi.mock('@/store/useScopedArtifactStore', () => ({
  useScopedArtifactStore: {
    getState: () => ({
      setTarget: mockSetTarget,
    }),
  },
  default: {
    getState: () => ({
      setTarget: mockSetTarget,
    }),
  },
}));

vi.mock('@/store/useArtifactPortalStore', () => {
  const getState = () => ({
    getActiveTab: () => ({ title: '销售明细.xlsx', artifactId: 'art-sheet-1' }),
    getDirtyArtifacts: () => ({}),
    clearDirtyState: vi.fn(),
  });
  return {
    default: {
      getState,
    },
  };
});

vi.mock('@/hooks/message-input/useMessageQueue', () => ({
  useMessageQueue: () => ({
    enqueue: vi.fn(),
    queue: [],
    hasQueuedMessages: false,
  }),
}));

vi.mock('@/lib/utils/clipboardUtils', () => ({
  writeToClipboard: (...args: unknown[]) => mockWriteToClipboard(...args),
}));

vi.mock('hugeicons-react', () => ({
  Edit04Icon: (props: Record<string, unknown>) => <span data-testid="edit-icon" {...props} />,
  InformationCircleIcon: (props: Record<string, unknown>) => <span data-testid="info-icon" {...props} />,
  Copy01Icon: (props: Record<string, unknown>) => <span data-testid="copy-icon" {...props} />,
  ArrowRight01Icon: (props: Record<string, unknown>) => <span data-testid="arrow-icon" {...props} />,
  MessageAdd01Icon: (props: Record<string, unknown>) => <span data-testid="quote-icon" {...props} />,
}));

import { SpreadsheetSelectionToolbar } from '../SpreadsheetSelectionToolbar';

describe('SpreadsheetSelectionToolbar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders range label and action buttons when visible', () => {
    const handleClose = vi.fn();
    render(
      <SpreadsheetSelectionToolbar
        visible={true}
        filename="销售明细.xlsx"
        sheetName="Q3汇总"
        selectedRangeLabel="B2:D10"
        selectedSnippet="产品A\t100\t2000"
        onClose={handleClose}
      />,
    );

    expect(screen.getByText('Q3汇总!B2:D10')).toBeDefined();
    expect(screen.getByText('引用到输入框')).toBeDefined();
    expect(screen.getByText('copy')).toBeDefined();
    expect(screen.getByText('explain')).toBeDefined();
  });

  it('quotes range to scoped artifact store and chat store on click', () => {
    const handleClose = vi.fn();
    const sampleSnippet = '产品A\t100\t2000';
    render(
      <SpreadsheetSelectionToolbar
        visible={true}
        artifactId="art-sheet-1"
        filename="销售明细.xlsx"
        sheetName="Q3汇总"
        selectedRangeLabel="B2:D10"
        selectedSnippet={sampleSnippet}
        onClose={handleClose}
      />,
    );

    const quoteBtn = screen.getByText('引用到输入框');
    fireEvent.click(quoteBtn.closest('button')!);

    expect(mockSetTarget).toHaveBeenCalledWith({
      artifactId: 'art-sheet-1',
      artifactName: '销售明细.xlsx',
      kind: 'spreadsheet',
      scopeLabel: 'Q3汇总!B2:D10',
      selectedSnippet: sampleSnippet,
    });

    expect(mockAddMentionReference).toHaveBeenCalledWith({
      type: 'artifact_range',
      label: '销售明细.xlsx',
      artifactId: 'art-sheet-1',
      sheetName: 'Q3汇总',
      range: 'Q3汇总!B2:D10',
      source: 'generated',
      size: sampleSnippet.length,
    });

    expect(handleClose).toHaveBeenCalled();
  });
});
