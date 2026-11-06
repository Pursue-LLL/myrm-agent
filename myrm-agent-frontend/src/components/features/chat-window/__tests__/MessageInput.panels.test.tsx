/**
 * [INPUT]
 * - ./messageInputHarness (POS: 输入区集成测试的共享替身)
 * - ../MessageInput (POS: 聊天输入区视图层)
 *
 * [OUTPUT]
 * Vitest: 输入区的面板开合（手机操作表、选项区、能力编辑）、拖拽、对话框与提示条、工作区选择器接线。
 *
 * [POS]
 * 守住输入区拆分前后的行为：每个用例只经由 DOM 与替身记录的属性来断言。
 */
import { act, fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  callStubProp,
  fileDrag,
  h,
  hookOf,
  makeFileDrag,
  makeSessionDrag,
  renderComposer,
  renderInput,
  sessionDrag,
  setHook,
  stubProps,
  installMessageInputHarness,
} from './messageInputHarness';
import type { ChatItem } from '@/services/chat';
import type { Project } from '@/services/projects';
import type { File as ChatFile, Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import { useProjectStore } from '@/store/useProjectStore';

installMessageInputHarness();

const ACCEPTED_DROP_TYPES = [
  'image/*',
  'video/*',
  'audio/*',
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'application/vnd.ms-powerpoint',
  'text/csv',
  'text/plain',
  'text/markdown',
  'application/json',
];

describe('MessageInput panels', () => {
  it('opens the action sheet from the phone "+" button and closes it again', () => {
    renderInput();
    expect(stubProps('MobileActionSheet').open).toBe(false);

    fireEvent.click(screen.getByTestId('sendbox-mobile-plus-btn'));
    expect(stubProps('MobileActionSheet').open).toBe(true);

    callStubProp('MobileActionSheet', 'onClose');
    expect(stubProps('MobileActionSheet').open).toBe(false);
  });

  it('closes the sheet from its entries and hands the capability toggle the selection', () => {
    const selection = { skillIds: ['s'] } as unknown as ReturnType<typeof hookOf>['turnCapabilitySelection'];
    setHook({ turnCapabilitySelection: selection });
    renderInput({ loading: true });
    fireEvent.click(screen.getByTestId('sendbox-mobile-plus-btn'));
    expect(stubProps('MobileActionSheet').open).toBe(true);

    const entriesOptions = h.useMobileSheetEntries.mock.calls.at(-1)?.[0] as { onClose: () => void };
    act(() => entriesOptions.onClose());

    expect(stubProps('MobileActionSheet').open).toBe(false);
    expect(stubProps('TurnCapabilityToggle')).toMatchObject({
      selection,
      onSelectionChange: hookOf().setTurnCapabilitySelection,
      disabled: true,
    });
  });

  it('edits capabilities in the options region on desktop', () => {
    renderInput();

    callStubProp('ComposerContextChipStrip', 'onOpenCapabilityEditor');

    expect(stubProps('ComposerOptionsRegion')).toMatchObject({ turnCapabilityOpen: true, expanded: true });
    expect(stubProps('MobileActionSheet').open).toBe(false);
  });

  it('edits capabilities in the action sheet on the phone', () => {
    h.desktop.current = false;
    renderInput();

    callStubProp('SkillRequiredConnectorsPreflightBanner', 'onOpenCapabilityEditor');

    expect(stubProps('MobileActionSheet').open).toBe(true);
    expect(stubProps('ComposerOptionsRegion').turnCapabilityOpen).toBe(false);
    expect(stubProps('useComposerContextChips').onOpenCapabilityEditor).toBe(
      stubProps('SkillRequiredConnectorsPreflightBanner').onOpenCapabilityEditor,
    );
  });

  it('toggles the options region and keeps it open while the capability popover is open', () => {
    renderInput();
    expect(stubProps('ComposerOptionsRegion').expanded).toBe(false);

    callStubProp('ComposerPrimaryControls', 'onToggleOptions');
    expect(stubProps('ComposerOptionsRegion').expanded).toBe(true);
    expect(stubProps('ComposerPrimaryControls').optionsExpanded).toBe(true);

    callStubProp('ComposerPrimaryControls', 'onToggleOptions');
    expect(stubProps('ComposerOptionsRegion').expanded).toBe(false);

    callStubProp('ComposerOptionsRegion', 'onTurnCapabilityOpenChange', true);
    expect(stubProps('ComposerOptionsRegion').expanded).toBe(true);
    callStubProp('ComposerPrimaryControls', 'onToggleOptions');
    expect(stubProps('ComposerOptionsRegion')).toMatchObject({ expanded: false, turnCapabilityOpen: false });
    expect(stubProps('ComposerPrimaryControls').optionsRegionId).toBe(stubProps('ComposerOptionsRegion').id);
  });
});

describe('MessageInput drag and drop', () => {
  it('shows the drop overlay for file, session and desktop folder drags', () => {
    h.fileDrag.current = makeFileDrag(true);
    const { rerender } = renderInput();
    expect(screen.getByText('dragDrop.title')).toBeInTheDocument();
    expect(screen.getByText('dragDrop.description')).toBeInTheDocument();

    h.fileDrag.current = makeFileDrag(false);
    h.sessionDrag.current = makeSessionDrag(true);
    rerender();
    expect(screen.getByText('dragDrop.sessionTitle')).toBeInTheDocument();
    expect(screen.getByText('dragDrop.sessionDescription')).toBeInTheDocument();

    h.sessionDrag.current = makeSessionDrag(false);
    h.folderDrag.current = true;
    rerender();
    expect(screen.getByText('dragDrop.title')).toBeInTheDocument();

    h.folderDrag.current = false;
    rerender();
    expect(screen.queryByText('dragDrop.title')).toBeNull();
  });

  it('feeds every drag event to both the file and the session drop handlers', () => {
    const { textarea } = renderInput();

    fireEvent.dragEnter(textarea);
    fireEvent.dragOver(textarea);
    fireEvent.dragLeave(textarea);
    fireEvent.drop(textarea);

    for (const { dragHandlers } of [fileDrag(), sessionDrag()]) {
      expect(dragHandlers.onDragEnter).toHaveBeenCalledTimes(1);
      expect(dragHandlers.onDragOver).toHaveBeenCalledTimes(1);
      expect(dragHandlers.onDragLeave).toHaveBeenCalledTimes(1);
      expect(dragHandlers.onDrop).toHaveBeenCalledTimes(1);
    }
  });

  it('accepts the supported file types, caps the batch and routes picks to the upload handler', () => {
    renderInput();

    const options = h.useDragDrop.mock.calls.at(-1)?.[0] as {
      accept: string[];
      maxFiles: number;
      disabled: boolean;
      onFilesSelected: (files: File[]) => void;
    };
    expect(options.accept).toEqual(ACCEPTED_DROP_TYPES);
    expect(options.maxFiles).toBe(20);
    expect(options.disabled).toBe(false);

    const dropped = [new File(['x'], 'x.txt', { type: 'text/plain' })];
    options.onFilesSelected(dropped);
    expect(hookOf().handleDroppedFiles).toHaveBeenCalledWith(dropped);
  });

  it('turns every drop target off while the agent runs or in fast mode', () => {
    const { rerender } = renderInput({ loading: true });
    expect(h.useDragDrop.mock.calls.at(-1)?.[0]).toMatchObject({ disabled: true });
    expect(h.usePriorChatComposerDrop.mock.calls.at(-1)?.[0]).toEqual({ disabled: true });
    expect(h.useDesktopFolderDrop.mock.calls.at(-1)?.[0]).toEqual({ disabled: true });

    setHook({ actionMode: 'fast' });
    rerender();
    expect(h.useDragDrop.mock.calls.at(-1)?.[0]).toMatchObject({ disabled: true });

    setHook();
    rerender();
    expect(h.usePriorChatComposerDrop.mock.calls.at(-1)?.[0]).toEqual({ disabled: false });
    expect(h.useDesktopFolderDrop.mock.calls.at(-1)?.[0]).toEqual({ disabled: false });
  });
});

describe('MessageInput dialogs and strips', () => {
  it('confirms a compaction with the remember choice', () => {
    setHook({ showCompactConfirm: true });
    renderInput();

    expect(screen.getByText('compact.confirmTitle')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('compact.dontRemindAgain'));
    expect(hookOf().setDontRemindCompact).toHaveBeenCalledWith(true);

    fireEvent.click(screen.getByRole('button', { name: 'compact.confirmButton' }));
    expect(hookOf().confirmCompact).toHaveBeenCalledTimes(1);
  });

  it('dismisses the compaction dialog through its open state', () => {
    setHook({ showCompactConfirm: true });
    renderInput();

    fireEvent.click(screen.getByRole('button', { name: 'cancel' }));

    expect(hookOf().setShowCompactConfirm).toHaveBeenCalledWith(false);
  });

  it('wires the link detection dialog to its state and handlers', () => {
    setHook({ showLinkDialog: true, dontRemindAgain: true });
    renderInput();

    expect(stubProps('LinkDetectionDialog')).toMatchObject({
      open: true,
      onOpenChange: hookOf().setShowLinkDialog,
      dontRemindAgain: true,
      setDontRemindAgain: hookOf().setDontRemindAgain,
      onAddAtSymbol: hookOf().handleAddAtSymbol,
      onSkip: hookOf().handleSkipAtSymbol,
    });
  });

  it('wires the queue list to the queue state', () => {
    setHook({ queuePausedReason: 'stuck', queueEditingId: 'q1' });
    renderInput();

    expect(stubProps('QueuedMessagesList')).toMatchObject({
      pausedReason: 'stuck',
      editingId: 'q1',
      setEditingId: hookOf().setQueueEditingId,
      editMessage: hookOf().editMessage,
      removeMessage: hookOf().removeMessage,
      reorder: hookOf().reorder,
      resume: hookOf().resumeQueue,
    });
  });

  it('lists attachments only when there are some and the list is not hidden', () => {
    const file = { id: 'f' } as ChatFile;
    const { rerender } = renderInput();
    expect(h.propsByStub.has('AttachList')).toBe(false);

    setHook({ files: [file], hideAttachList: true });
    rerender();
    expect(h.propsByStub.has('AttachList')).toBe(false);

    setHook({ files: [file] });
    rerender();
    expect(stubProps('AttachList')).toMatchObject({
      files: [file],
      setFiles: hookOf().setFiles,
      clearCurrentSessionMessageId: hookOf().clearCurrentSessionMessageId,
      setHideAttachList: hookOf().setHideAttachList,
    });
  });

  it('warns that /btw and /bg are ambiguous only while a turn runs', () => {
    setHook({ inputMessage: '/btw look at this' });
    const { rerender } = renderInput();
    expect(screen.queryByText('builtin.btwDisambiguation')).toBeNull();

    rerender({ loading: true });
    expect(screen.getByText('builtin.btwDisambiguation')).toBeInTheDocument();

    setHook({ inputMessage: 'btw look at this' });
    rerender({ loading: true });
    expect(screen.queryByText('builtin.btwDisambiguation')).toBeNull();
  });

  it('replaces the input with the clarification form while a clarification waits for an answer', () => {
    const clarification = { answered: false, options: ['a'], allowMultiple: false, title: 'Pick one' };
    useChatStore.setState({
      messages: [{ messageId: 'm1', chatId: 'c', role: 'assistant', content: '', clarification } as unknown as Message],
    });

    const { container } = renderComposer();

    expect(stubProps('ClarificationInput')).toMatchObject({ messageId: 'm1', variant: 'composer', title: 'Pick one' });
    expect(container.querySelector('textarea')).toBeNull();
  });
});

describe('MessageInput workspace picker', () => {
  const chatItem = (projectId: string | null): ChatItem => ({ id: 'chat-1', projectId }) as ChatItem;
  const project = (workspacePath: string): Project => ({ id: 'p1', workspacePath }) as unknown as Project;

  it('shows the picker for a chat outside any project', () => {
    useChatStore.setState({ chatId: 'chat-1', chatHistoryItems: [chatItem(null)] });
    renderInput();

    expect(h.propsByStub.has('WorkspaceDirPicker')).toBe(true);
  });

  it('hides it when the chat belongs to a project that owns a workspace', () => {
    useChatStore.setState({ chatId: 'chat-1', chatHistoryItems: [chatItem('p1')] });
    useProjectStore.setState({ projects: [project('/work/space')] });
    renderInput();

    expect(h.propsByStub.has('WorkspaceDirPicker')).toBe(false);
  });

  it('keeps it for a project without a usable workspace path', () => {
    useChatStore.setState({ chatId: 'chat-1', chatHistoryItems: [chatItem('p1')] });
    useProjectStore.setState({ projects: [project('   ')] });
    renderInput();

    expect(h.propsByStub.has('WorkspaceDirPicker')).toBe(true);
  });

  it('loads the project list once when it is not loaded yet', () => {
    const fetchProjects = vi.fn();
    useProjectStore.setState({ loaded: false, fetchProjects });
    renderInput();

    expect(fetchProjects).toHaveBeenCalledTimes(1);
  });
});
