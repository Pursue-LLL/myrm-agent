/**
 * [INPUT]
 * - ../MessageInput (POS: 聊天输入区视图层)
 * - @/hooks/message-input/useMessageInput (POS: 输入状态与提交编排，这里以可控替身接入)
 *
 * [OUTPUT]
 * - h: 钩子与子组件替身的可变状态；stubProps / callStubProp: 读取与触发子组件替身收到的属性
 * - installMessageInputHarness: 每个用例前复位替身与 store
 * - renderInput: 渲染输入区并取回文本框
 *
 * [POS]
 * MessageInput 集成测试的共享替身：子组件与重钩子换成记录属性的替身，只验证输入区自己的接线与分流。
 * 测试文件必须先导入本模块再导入被测组件，这样 vi.mock 先于被测组件的依赖解析生效。
 */
import * as React from 'react';
import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, vi, type Mock } from 'vitest';
import type { useMessageInput } from '@/hooks/message-input/useMessageInput';
import type { ContextChipItem } from '@/hooks/message-input/useComposerContextChips';
import type { DragHandlers } from '@/hooks/ui/useDragDrop';
import useChatStore from '@/store/useChatStore';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import { useProjectStore } from '@/store/useProjectStore';

export type MessageInputHook = ReturnType<typeof useMessageInput>;

export interface SlashState {
  showCommandPalette: boolean;
  filteredItems: never[];
  selectedIndex: number;
  executeCommand: Mock;
  handleKeyDown: Mock;
}

export interface MentionState {
  isOpen: boolean;
  results: never[];
  selectedIndex: number;
  query: string;
  selectReference: Mock;
  handleKeyDown: Mock;
}

export interface HistoryState {
  popup: { open: boolean; entries: never[]; activeIndex: number };
  ghostText: string | undefined;
  handleKeyDown: Mock;
  close: Mock;
  confirm: Mock;
  setActiveIndex: Mock;
}

export interface PrewarmState {
  triggerPrewarm: Mock;
  cancelPrewarm: Mock;
  shouldPrewarm: boolean;
}

export interface FileDragState {
  isDragging: boolean;
  dragHandlers: DragHandlers;
}

export interface SessionDragState {
  isSessionDragging: boolean;
  dragHandlers: DragHandlers;
}

const state = vi.hoisted(() => {
  const propsByStub = new Map<string, Record<string, unknown>>();
  return {
    propsByStub,
    stub: (name: string) => (props: Record<string, unknown>) => {
      propsByStub.set(name, props);
      return null;
    },
    hook: { current: undefined as unknown },
    slash: { current: undefined as unknown },
    mention: { current: undefined as unknown },
    history: { current: undefined as unknown },
    chips: { current: [] as unknown[] },
    fileDrag: { current: undefined as unknown },
    sessionDrag: { current: undefined as unknown },
    folderDrag: { current: false },
    prewarm: { current: undefined as unknown },
    turnStoppable: { current: true },
    desktop: { current: true },
    useSlashCommand: vi.fn(),
    useReferenceMention: vi.fn(),
    useDragDrop: vi.fn(),
    usePriorChatComposerDrop: vi.fn(),
    useDesktopFolderDrop: vi.fn(),
    useMobileSheetEntries: vi.fn(),
    reportUserActivity: vi.fn(),
  };
});

export const h = state;

vi.mock('../../message-input-actions/AttachList', () => ({ default: state.stub('AttachList') }));
vi.mock('../../message-input-actions/AttachButton', () => ({ default: state.stub('AttachButton') }));
vi.mock('../../message-input-actions/SearchModeSelector', () => ({ default: state.stub('SearchModeSelector') }));
vi.mock('../../message-input-actions/DeepSearchToggle', () => ({ default: state.stub('DeepSearchToggle') }));
vi.mock('../../message-input-actions/WorkflowModeToggle', () => ({ default: state.stub('WorkflowModeToggle') }));
vi.mock('../../message-box/ContextUsageIndicator', () => ({ default: state.stub('ContextUsageIndicator') }));
vi.mock('../LivenessIndicator', () => ({ default: state.stub('LivenessIndicator') }));
vi.mock('../../message-input-actions/ReadinessBadge', () => ({ default: state.stub('ReadinessBadge') }));
vi.mock('../BudgetBadge', () => ({ default: state.stub('BudgetBadge') }));
vi.mock('@/components/billing/WorkUnitBalanceBar', () => ({ default: state.stub('WorkUnitBalanceBar') }));
vi.mock('@/components/billing/SessionSpendSurface', () => ({ default: state.stub('SessionSpendSurface') }));
vi.mock('../../message-input-actions/EnvironmentShield', () => ({ default: state.stub('EnvironmentShield') }));
vi.mock('../../message-input-actions/AgentIndicator', () => ({ default: state.stub('AgentIndicator') }));
vi.mock('../../message-input-actions/KnowledgePickerPopover', () => ({
  default: state.stub('KnowledgePickerPopover'),
}));
vi.mock('../../message-input-actions/TurnCapabilityToggle', () => ({ default: state.stub('TurnCapabilityToggle') }));
vi.mock('../WorkspaceDirPicker', () => ({ default: state.stub('WorkspaceDirPicker') }));
vi.mock('../../message-input-actions/SpeechInputButton', () => ({ default: state.stub('SpeechInputButton') }));
vi.mock('../../message-input-actions/VoiceSessionButton', () => ({ default: state.stub('VoiceSessionButton') }));
vi.mock('../../message-input-actions/IncognitoModeToggle', () => ({ default: state.stub('IncognitoModeToggle') }));
vi.mock('../../message-input-actions/SecurityPresetSelector', () => ({
  default: state.stub('SecurityPresetSelector'),
}));
vi.mock('../../message-input-actions/ProviderLowBalanceWarningHUD', () => ({
  default: state.stub('ProviderLowBalanceWarningHUD'),
}));
vi.mock('../../message-input-actions/ActiveFilesPanel', () => ({ default: state.stub('ActiveFilesPanel') }));
vi.mock('../../message-box/ClarificationInput', () => ({ default: state.stub('ClarificationInput') }));
vi.mock('../SessionAccessRootsBar', () => ({ default: state.stub('SessionAccessRootsBar') }));
vi.mock('../ProjectBoundaryBadge', () => ({ default: state.stub('ProjectBoundaryBadge') }));
vi.mock('../InputHistoryPopup', () => ({ default: state.stub('InputHistoryPopup') }));
vi.mock('../RealTimeCostAndCacheHud', () => ({ RealTimeCostAndCacheHud: state.stub('RealTimeCostAndCacheHud') }));
vi.mock('../composer-options/ComposerOptionsRegion', () => ({
  ComposerOptionsRegion: state.stub('ComposerOptionsRegion'),
}));
vi.mock('../composer-options/ComposerPrimaryControls', () => ({
  ComposerPrimaryControls: state.stub('ComposerPrimaryControls'),
}));
vi.mock('../QueuedMessagesList', () => ({ QueuedMessagesList: state.stub('QueuedMessagesList') }));
vi.mock('../LinkDetectionDialog', () => ({ LinkDetectionDialog: state.stub('LinkDetectionDialog') }));
vi.mock('@/components/features/app-shell/command-palette', () => ({ CommandPalette: state.stub('CommandPalette') }));
vi.mock('../ReferenceMentionPopover', () => ({ ReferenceMentionPopover: state.stub('ReferenceMentionPopover') }));
vi.mock('../QuoteCard', () => ({ QuoteCard: state.stub('QuoteCard') }));
vi.mock('../agent-config-panel/FeaturedExpertChips', () => ({
  FeaturedExpertChips: state.stub('FeaturedExpertChips'),
}));
vi.mock('../context-strip/ComposerContextChipStrip', () => ({
  ComposerContextChipStrip: state.stub('ComposerContextChipStrip'),
}));
vi.mock('../context-strip/SkillRequiredConnectorsPreflightBanner', () => ({
  SkillRequiredConnectorsPreflightBanner: state.stub('SkillRequiredConnectorsPreflightBanner'),
}));
vi.mock('../ScopedArtifactChip', () => ({ ScopedArtifactChip: state.stub('ScopedArtifactChip') }));
vi.mock('../WechatArticleComposerHint', () => ({ WechatArticleComposerHint: state.stub('WechatArticleComposerHint') }));
vi.mock('../../message-box/ContextSpilloverBadge', () => ({
  ContextSpilloverBadge: state.stub('ContextSpilloverBadge'),
}));
vi.mock('../subagent/ChatInlineTeamRunVisibilityStrip', () => ({
  ChatInlineTeamRunVisibilityStrip: state.stub('ChatInlineTeamRunVisibilityStrip'),
}));
vi.mock('../mobile/MobileActionSheet', () => ({
  MobileActionSheet: (props: Record<string, unknown> & { footer?: React.ReactNode }) => {
    state.propsByStub.set('MobileActionSheet', props);
    return <div data-testid="mobile-sheet">{props.footer}</div>;
  },
}));
vi.mock('../mobile/useMobileSheetEntries', () => ({ useMobileSheetEntries: state.useMobileSheetEntries }));
vi.mock('@/hooks/message-input/useMessageInput', () => ({ useMessageInput: () => state.hook.current }));
vi.mock('@/hooks/message-input/useSlashCommand', () => ({ useSlashCommand: state.useSlashCommand }));
vi.mock('@/hooks/message-input/useReferenceMention', () => ({ useReferenceMention: state.useReferenceMention }));
vi.mock('@/hooks/message-input/useInputHistory', () => ({ useInputHistory: () => state.history.current }));
vi.mock('@/hooks/message-input/useComposerContextChips', () => ({
  useComposerContextChips: (params: Record<string, unknown>) => {
    state.propsByStub.set('useComposerContextChips', params);
    return {
      chips: state.chips.current,
      summary: { totalItems: 0, totalSkills: 0, totalMcp: 0, totalFiles: 0, isOverloaded: false },
    };
  },
}));
vi.mock('@/hooks/ui/useDragDrop', () => ({ useDragDrop: state.useDragDrop }));
vi.mock('@/hooks/chat/usePriorChatComposerDrop', () => ({
  usePriorChatComposerDrop: state.usePriorChatComposerDrop,
}));
vi.mock('@/hooks/message-input/useDesktopFolderDrop', () => ({ useDesktopFolderDrop: state.useDesktopFolderDrop }));
vi.mock('@/hooks/chat/useTurnStoppable', () => ({ useTurnStoppable: () => state.turnStoppable.current }));
vi.mock('@/hooks/chat/useChatTurnPrewarm', () => ({ useChatTurnPrewarm: () => state.prewarm.current }));
vi.mock('@/services/memory', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/memory')>()),
  reportUserActivity: state.reportUserActivity,
}));

import MessageInput from '../MessageInput';

const initialChatState = useChatStore.getState();
const initialProjectState = useProjectStore.getState();
const initialFeatureState = useFeatureGateStore.getState();

export function makeHook(overrides: Partial<MessageInputHook> = {}): MessageInputHook {
  return {
    showLinkDialog: false,
    setShowLinkDialog: vi.fn(),
    detectedLink: null,
    dontRemindAgain: false,
    setDontRemindAgain: vi.fn(),
    isUploadingPaste: false,
    showCompactConfirm: false,
    setShowCompactConfirm: vi.fn(),
    dontRemindCompact: false,
    setDontRemindCompact: vi.fn(),
    turnCapabilitySelection: null,
    setTurnCapabilitySelection: vi.fn(),
    inputRef: React.createRef<HTMLTextAreaElement>(),
    actionMode: 'agent',
    setActionMode: vi.fn(),
    files: [],
    setFiles: vi.fn(),
    hideAttachList: false,
    setHideAttachList: vi.fn(),
    stopMessage: vi.fn(),
    clearCurrentSessionMessageId: vi.fn(),
    inputMessage: '',
    setInputMessage: vi.fn(),
    loading: false,
    queue: [],
    queuePausedReason: null,
    queueEditingId: null,
    editMessage: vi.fn(),
    removeMessage: vi.fn(),
    clearQueue: vi.fn(),
    reorder: vi.fn(),
    setQueueEditingId: vi.fn(),
    resumeQueue: vi.fn(),
    handlePaste: vi.fn(),
    handleDroppedFiles: vi.fn(),
    handleSubmit: vi.fn(),
    handleSteerSubmit: vi.fn(),
    handleRedirectSubmit: vi.fn(),
    handleQueueSubmit: vi.fn(),
    handleInputChange: vi.fn(),
    handleAddAtSymbol: vi.fn(),
    handleSkipAtSymbol: vi.fn(),
    executeCompact: vi.fn(),
    confirmCompact: vi.fn(),
    ...overrides,
  };
}

function makeDragHandlers(): DragHandlers {
  return { onDragEnter: vi.fn(), onDragOver: vi.fn(), onDragLeave: vi.fn(), onDrop: vi.fn() };
}

export function makeFileDrag(isDragging: boolean): FileDragState {
  return { isDragging, dragHandlers: makeDragHandlers() };
}

export function makeSessionDrag(isSessionDragging: boolean): SessionDragState {
  return { isSessionDragging, dragHandlers: makeDragHandlers() };
}

export function chip(id: string, isRemovable: boolean, onRemove?: () => void): ContextChipItem {
  return { id, category: 'mention', label: id, iconType: 'mention', isRemovable, onRemove };
}

/** Replaces what `useMessageInput` returns; call before rendering or before a rerender. */
export function setHook(overrides: Partial<MessageInputHook> = {}): MessageInputHook {
  const hook = makeHook(overrides);
  state.hook.current = hook;
  return hook;
}

export const hookOf = (): MessageInputHook => state.hook.current as MessageInputHook;
export const slash = (): SlashState => state.slash.current as SlashState;
export const mention = (): MentionState => state.mention.current as MentionState;
export const history = (): HistoryState => state.history.current as HistoryState;
export const prewarm = (): PrewarmState => state.prewarm.current as PrewarmState;
export const fileDrag = (): FileDragState => state.fileDrag.current as FileDragState;
export const sessionDrag = (): SessionDragState => state.sessionDrag.current as SessionDragState;

export function stubProps(name: string): Record<string, unknown> {
  const props = state.propsByStub.get(name);
  if (!props) {
    throw new Error(`${name} did not render`);
  }
  return props;
}

export function callStubProp(name: string, prop: string, ...args: unknown[]): void {
  const fn = stubProps(name)[prop];
  if (typeof fn !== 'function') {
    throw new Error(`${name}.${prop} is not a function`);
  }
  act(() => {
    (fn as (...callArgs: unknown[]) => void)(...args);
  });
}

export function expandEditor(): void {
  callStubProp('ComposerPrimaryControls', 'onToggleEditor');
}

interface InputProps {
  loading?: boolean;
}

const inputElement = ({ loading = false }: InputProps) => <MessageInput loading={loading} />;

/** Renders the composer; `rerender` swaps its props and picks up whatever the replaced hook state returns. */
export function renderComposer(props: InputProps = {}) {
  const view = render(inputElement(props));
  return { container: view.container, rerender: (next: InputProps = {}) => view.rerender(inputElement(next)) };
}

/** Like `renderComposer`, plus the textarea (absent while a clarification replaces the input). */
export function renderInput(props: InputProps = {}) {
  const view = renderComposer(props);
  const textarea = view.container.querySelector('textarea');
  if (!textarea) {
    throw new Error('the composer textarea did not render');
  }
  return { ...view, textarea };
}

function resetHarness(): void {
  state.propsByStub.clear();
  localStorage.clear();
  useChatStore.setState(initialChatState, true);
  useProjectStore.setState({ ...initialProjectState, loaded: true, projects: [], fetchProjects: vi.fn() }, true);
  useFeatureGateStore.setState(initialFeatureState, true);
  setHook();
  state.slash.current = {
    showCommandPalette: false,
    filteredItems: [],
    selectedIndex: 0,
    executeCommand: vi.fn(),
    handleKeyDown: vi.fn(),
  } satisfies SlashState;
  state.mention.current = {
    isOpen: false,
    results: [],
    selectedIndex: 0,
    query: '',
    selectReference: vi.fn(),
    handleKeyDown: vi.fn(() => false),
  } satisfies MentionState;
  state.history.current = {
    popup: { open: false, entries: [], activeIndex: 0 },
    ghostText: undefined,
    handleKeyDown: vi.fn(() => false),
    close: vi.fn(),
    confirm: vi.fn(),
    setActiveIndex: vi.fn(),
  } satisfies HistoryState;
  state.chips.current = [];
  state.fileDrag.current = makeFileDrag(false);
  state.sessionDrag.current = makeSessionDrag(false);
  state.folderDrag.current = false;
  state.prewarm.current = {
    triggerPrewarm: vi.fn(),
    cancelPrewarm: vi.fn(),
    shouldPrewarm: true,
  } satisfies PrewarmState;
  state.turnStoppable.current = true;
  state.desktop.current = true;
  state.useSlashCommand.mockReset().mockImplementation(() => state.slash.current);
  state.useReferenceMention.mockReset().mockImplementation(() => state.mention.current);
  state.useDragDrop.mockReset().mockImplementation(() => state.fileDrag.current);
  state.usePriorChatComposerDrop.mockReset().mockImplementation(() => state.sessionDrag.current);
  state.useDesktopFolderDrop.mockReset().mockImplementation(() => ({ isDraggingOver: state.folderDrag.current }));
  state.useMobileSheetEntries.mockReset().mockReturnValue([]);
  state.reportUserActivity.mockReset().mockResolvedValue(undefined);
  window.matchMedia = vi.fn((query: string) => ({
    matches: state.desktop.current,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

/** Registers the per-case reset for the calling test file; call it once at the top level. */
export function installMessageInputHarness(): void {
  beforeEach(resetHarness);
  afterEach(() => {
    vi.useRealTimers();
  });
}
