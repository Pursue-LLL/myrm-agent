import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useComposerContextChips } from '../useComposerContextChips';
import useChatStore, { File as FileType } from '@/store/useChatStore';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('useComposerContextChips', () => {
  beforeEach(() => {
    act(() => {
      useChatStore.setState({
        pendingWorkflowTemplateId: null,
        pendingWorkflowTemplateDisplayName: null,
        pendingExplicitSkillActivation: null,
        activeKnowledgeBaseIds: [],
        activeKnowledgeBaseNames: {},
      });
    });
  });

  it('aggregates workflow template and skill chips correctly', () => {
    act(() => {
      useChatStore.setState({
        pendingWorkflowTemplateId: 'wf-audit',
        pendingWorkflowTemplateDisplayName: 'Security Audit Workflow',
        pendingExplicitSkillActivation: {
          skillNames: ['github_pr_analyzer'],
          instruction: 'Check test coverage',
        },
      });
    });

    const { result } = renderHook(() =>
      useComposerContextChips({
        turnCapabilitySelection: null,
        setTurnCapabilitySelection: vi.fn(),
        files: [],
        setFiles: vi.fn(),
        clearCurrentSessionMessageId: vi.fn(),
        mentionReferences: [],
        removeMentionReference: vi.fn(),
      }),
    );

    expect(result.current.chips).toHaveLength(2);
    expect(result.current.chips[0].category).toBe('workflow');
    expect(result.current.chips[0].label).toBe('Security Audit Workflow');
    expect(result.current.chips[1].category).toBe('skill');
    expect(result.current.chips[1].label).toBe('github pr analyzer');
    expect(result.current.summary.totalItems).toBe(2);
  });

  it('handles mention references and removes them with correct key', () => {
    const removeMentionReference = vi.fn();
    const { result } = renderHook(() =>
      useComposerContextChips({
        turnCapabilitySelection: null,
        setTurnCapabilitySelection: vi.fn(),
        files: [],
        setFiles: vi.fn(),
        clearCurrentSessionMessageId: vi.fn(),
        mentionReferences: [
          {
            type: 'file',
            path: 'src/index.ts',
            label: 'index.ts',
            startLine: 1,
            endLine: 20,
          },
        ],
        removeMentionReference,
      }),
    );

    expect(result.current.chips).toHaveLength(1);
    expect(result.current.chips[0].category).toBe('mention');
    expect(result.current.chips[0].label).toBe('index.ts');

    act(() => {
      result.current.chips[0].onRemove?.();
    });

    expect(removeMentionReference).toHaveBeenCalledWith('file:src/index.ts:1:20');
  });

  it('hides individual file chips when hideAttachList is false (AttachList handles preview)', () => {
    const files: FileType[] = [
      {
        id: 'file-1',
        fileName: 'architecture.png',
        fileExtension: 'png',
        fileSize: 1024,
        fileUrl: 'blob://arch',
        status: 'ready',
      },
    ];

    const { result } = renderHook(() =>
      useComposerContextChips({
        turnCapabilitySelection: null,
        setTurnCapabilitySelection: vi.fn(),
        files,
        setFiles: vi.fn(),
        clearCurrentSessionMessageId: vi.fn(),
        mentionReferences: [],
        removeMentionReference: vi.fn(),
        hideAttachList: false,
      }),
    );

    // Files are omitted from chip strip when AttachList is active
    expect(result.current.chips).toHaveLength(0);
    // But still accounted for in summary
    expect(result.current.summary.totalFiles).toBe(1);
  });

  it('renders individual file chips when hideAttachList is true', () => {
    const clearSession = vi.fn();
    const setFiles = vi.fn();
    const files: FileType[] = [
      {
        id: 'file-1',
        fileName: 'architecture.png',
        fileExtension: 'png',
        fileSize: 1024,
        fileUrl: 'blob://arch',
        status: 'ready',
      },
    ];

    const { result } = renderHook(() =>
      useComposerContextChips({
        turnCapabilitySelection: null,
        setTurnCapabilitySelection: vi.fn(),
        files,
        setFiles,
        clearCurrentSessionMessageId: clearSession,
        mentionReferences: [],
        removeMentionReference: vi.fn(),
        hideAttachList: true,
      }),
    );

    expect(result.current.chips).toHaveLength(1);
    expect(result.current.chips[0].category).toBe('attachment');
    expect(result.current.chips[0].label).toBe('architecture.png');

    act(() => {
      result.current.chips[0].onRemove?.();
    });

    expect(setFiles).toHaveBeenCalledWith([]);
    expect(clearSession).toHaveBeenCalledTimes(1);
  });

  it('calculates isOverloaded when tool count exceeds threshold', () => {
    const { result } = renderHook(() =>
      useComposerContextChips({
        turnCapabilitySelection: {
          skillIds: ['skill-1', 'skill-2', 'skill-3'],
          mcpNames: ['mcp-1', 'mcp-2', 'mcp-3'],
        },
        setTurnCapabilitySelection: vi.fn(),
        files: [],
        setFiles: vi.fn(),
        clearCurrentSessionMessageId: vi.fn(),
        mentionReferences: [],
        removeMentionReference: vi.fn(),
      }),
    );

    expect(result.current.summary.totalSkills).toBe(3);
    expect(result.current.summary.totalMcp).toBe(3);
    expect(result.current.summary.isOverloaded).toBe(true);
  });

  it('renders mounted knowledge base chips and handles unmount removal', () => {
    act(() => {
      useChatStore.setState({
        activeKnowledgeBaseIds: ['kb-1', 'kb-2'],
        activeKnowledgeBaseNames: {
          'kb-1': 'Architecture Guide',
          'kb-2': 'API Standards',
        },
      });
    });

    const { result } = renderHook(() =>
      useComposerContextChips({
        turnCapabilitySelection: null,
        setTurnCapabilitySelection: vi.fn(),
        files: [],
        setFiles: vi.fn(),
        clearCurrentSessionMessageId: vi.fn(),
        mentionReferences: [],
        removeMentionReference: vi.fn(),
      }),
    );

    const kbChips = result.current.chips.filter((c) => c.category === 'knowledge');
    expect(kbChips).toHaveLength(2);
    expect(kbChips[0].label).toBe('Architecture Guide');
    expect(kbChips[0].iconType).toBe('knowledge');
    expect(kbChips[1].label).toBe('API Standards');

    act(() => {
      kbChips[0].onRemove?.();
    });

    expect(useChatStore.getState().activeKnowledgeBaseIds).toEqual(['kb-2']);
  });
});
