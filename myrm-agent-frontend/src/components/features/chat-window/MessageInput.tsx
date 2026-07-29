/**
 * [INPUT]
 * - @/hooks/message-input/useMessageInput::useMessageInput (POS: 聊天输入状态与提交编排)
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线)
 * - ./LivenessIndicator::LivenessIndicator (POS: 聊天输入区 Agent 状态指示灯)
 *
 * [OUTPUT]
 * - MessageInput: 渲染聊天输入区、工具栏、快捷操作、Agent 状态灯和发送入口。
 *
 * [POS]
 * 聊天输入区视图层。承载消息输入、模式切换、附件、快捷操作与发送控制。
 */
import * as React from 'react';
import {
  ArrowRight,
  Square,
  Plus,
  X,
  Navigation,
  ListPlus,
  Maximize2,
  Minimize2,
  CornerDownLeft,
} from 'lucide-react';
import TextareaAutosize from 'react-textarea-autosize';
import AttachList from '../message-input-actions/AttachList';
import AttachButton from '../message-input-actions/AttachButton';
import SearchModeSelector from '../message-input-actions/SearchModeSelector';
import DeepSearchToggle from '../message-input-actions/DeepSearchToggle';
import WorkflowModeToggle from '../message-input-actions/WorkflowModeToggle';
import BaseModelSelector from '../message-input-actions/BaseModelSelector';
import ContextUsageIndicator from '../message-box/ContextUsageIndicator';
import LivenessIndicator from './LivenessIndicator';
import ReadinessBadge from '../message-input-actions/ReadinessBadge';
import BudgetBadge from './BudgetBadge';
import WorkUnitBalanceBar from '@/components/billing/WorkUnitBalanceBar';
import SessionSpendSurface from '@/components/billing/SessionSpendSurface';
import EnvironmentShield from '../message-input-actions/EnvironmentShield';
import AgentIndicator from '../message-input-actions/AgentIndicator';
import ToolsPanel from '../message-input-actions/ToolsPanel';
import SessionSkillsToggle from '../message-input-actions/SessionSkillsToggle';
import TurnCapabilityToggle from '../message-input-actions/TurnCapabilityToggle';
import WorkspaceDirPicker from './WorkspaceDirPicker';
import SpeechInputButton from '../message-input-actions/SpeechInputButton';
import VoiceSessionButton from '../message-input-actions/VoiceSessionButton';
import ThinkingIntensityButton from '../message-input-actions/ThinkingIntensityButton';
import GoalModeToggle from '../message-input-actions/GoalModeToggle';
import IncognitoModeToggle from '../message-input-actions/IncognitoModeToggle';
import SandboxModeToggle from '../message-input-actions/SandboxModeToggle';
import SecurityPresetSelector from '../message-input-actions/SecurityPresetSelector';
import FocusFlushButton from '../message-input-actions/FocusFlushButton';
import { ForkButton } from './ForkButton';
import { QueuedMessagesList } from './QueuedMessagesList';
import ActiveWorkingMemoryPanel from '../message-input-actions/ActiveWorkingMemoryPanel';
import { useTranslations } from 'next-intl';
import { useMessageInput } from '@/hooks/message-input/useMessageInput';
import { useDragDrop } from '@/hooks/ui/useDragDrop';
import { LinkDetectionDialog } from './LinkDetectionDialog';
import { MobileActionSheet } from './MobileActionSheet';
import { useMobileSheetEntries } from './useMobileSheetEntries';
import { CommandPalette } from '@/components/features/app-shell/command-palette';
import { useSlashCommand } from '@/hooks/message-input/useSlashCommand';
import { useReferenceMention } from '@/hooks/message-input/useReferenceMention';
import { ReferenceMentionPopover } from './ReferenceMentionPopover';
import ClarificationInput from '../message-box/ClarificationInput';
import { findActivePendingClarification } from '@/store/chat/clarificationState';
import useChatStore from '@/store/useChatStore';
import { useShallow } from 'zustand/react/shallow';
import { useProjectStore } from '@/store/useProjectStore';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';
import { QuoteCard } from './QuoteCard';
import { useInputHistory } from '@/hooks/message-input/useInputHistory';
import InputHistoryPopup from './InputHistoryPopup';
import { SkillActivationChips } from '../message-box/SkillActivationChips';

const KEYTERM_PATTERN =
  /(?:[A-Z][a-z]+(?:[A-Z][a-z]+)+|[A-Z]{2,}[a-z]*|[a-zA-Z][\w.-]{2,}(?:\.[\w]+)+|[\u4e00-\u9fff]{2,4}(?:[\u4e00-\u9fff]+)?)/g;
const MAX_KEYTERMS = 15;

function extractKeyterms(messages: { content: string; role: string }[]): string[] {
  const recent = messages.slice(-6);
  const text = recent.map((m) => m.content).join(' ');
  const matches = text.match(KEYTERM_PATTERN);
  if (!matches) return [];

  const counts = new Map<string, number>();
  for (const m of matches) {
    const lower = m.toLowerCase();
    counts.set(lower, (counts.get(lower) || 0) + 1);
  }

  return [...counts.entries()]
    .filter(([, c]) => c >= 1)
    .sort((a, b) => b[1] - a[1])
    .slice(0, MAX_KEYTERMS)
    .map(([term]) => term);
}
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { AlertTriangle } from 'lucide-react';

const mentionReferenceKey = (reference: {
  type: string;
  path?: string;
  fileId?: string;
  url?: string;
  label: string;
  startLine?: number;
  endLine?: number;
}) =>
  `${reference.type}:${reference.path ?? reference.fileId ?? reference.url ?? reference.label}:${reference.startLine ?? ''}:${reference.endLine ?? ''}`;

const MessageInput = ({ loading }: { loading: boolean }) => {
  const commonT = useTranslations('common');
  const chatT = useTranslations('chat');
  const messages = useChatStore((s) => s.messages);
  const chatId = useChatStore((s) => s.chatId);
  const chatHistoryItems = useChatStore((s) => s.chatHistoryItems);
  const projects = useProjectStore((s) => s.projects);
  const projectsLoaded = useProjectStore((s) => s.loaded);
  const fetchProjects = useProjectStore((s) => s.fetchProjects);
  const agentConfig = useChatStore((s) => s.agentConfig);
  const mentionReferences = useChatStore((s) => s.mentionReferences);
  const removeMentionReference = useChatStore((s) => s.removeMentionReference);
  const keyterms = React.useMemo(() => extractKeyterms(messages), [messages]);
  const pendingClarification = React.useMemo(
    () => findActivePendingClarification(messages),
    [messages],
  );
  const isComposerClarifyMode = pendingClarification !== null;
  const isVoiceEnabled = useFeatureGateStore((s) => s.isEnabled('voice_interaction'));

  React.useEffect(() => {
    if (!projectsLoaded) {
      void fetchProjects();
    }
  }, [fetchProjects, projectsLoaded]);

  const hideChatWorkspacePicker = React.useMemo(() => {
    if (!chatId) return false;
    const chatItem = chatHistoryItems.find((item) => item.id === chatId);
    const projectId = chatItem?.projectId;
    if (!projectId) return false;
    const project = projects.find((item) => item.id === projectId);
    return Boolean(project?.workspacePath?.trim());
  }, [chatHistoryItems, chatId, projects]);

  const [isMobileSheetOpen, setIsMobileSheetOpen] = React.useState(false);
  const [isExpanded, setIsExpanded] = React.useState(false);

  const {
    showLinkDialog,
    setShowLinkDialog,
    dontRemindAgain,
    setDontRemindAgain,
    isUploadingPaste,
    showCompactConfirm,
    setShowCompactConfirm,
    dontRemindCompact,
    setDontRemindCompact,
    turnCapabilitySelection,
    setTurnCapabilitySelection,
    inputRef,
    actionMode,
    setActionMode,
    files,
    setFiles,
    hideAttachList,
    setHideAttachList,
    stopMessage,
    clearCurrentSessionMessageId,
    inputMessage,
    setInputMessage,
    handlePaste,
    handleSubmit,
    handleSteerSubmit,
    handleRedirectSubmit,
    handleQueueSubmit,
    handleInputChange,
    handleDroppedFiles,
    handleAddAtSymbol,
    handleSkipAtSymbol,
    confirmCompact,
    queue,
    editMessage,
    removeMessage,
    reorder,
  } = useMessageInput();

  const { pendingExplicitSkillActivation, setPendingExplicitSkillActivation } = useChatStore(
    useShallow((state) => ({
      pendingExplicitSkillActivation: state.pendingExplicitSkillActivation,
      setPendingExplicitSkillActivation: state.setPendingExplicitSkillActivation,
    })),
  );

  const inputHistory = useInputHistory({
    agentId: agentConfig?.id,
    getInputValue: () => inputMessage,
  });


  const mobileSheetEntries = useMobileSheetEntries({
    onClose: () => setIsMobileSheetOpen(false),
  });

  const handleTranscript = React.useCallback(
    (text: string) => {
      const currentMessage = inputRef.current?.value || '';
      setInputMessage(currentMessage ? `${currentMessage} ${text}` : text);
      inputRef.current?.focus();
    },
    [setInputMessage, inputRef],
  );

  // 追踪光标位置（用于快捷指令检测）
  const [cursorPosition, setCursorPosition] = React.useState(0);

  // 更新光标位置的统一方法
  const updateCursorPosition = React.useCallback(() => {
    const pos = inputRef.current?.selectionStart || 0;
    setCursorPosition(pos);
  }, []);

  // 监听输入变化，更新光标位置
  React.useEffect(() => {
    updateCursorPosition();
  }, [inputMessage, updateCursorPosition]);

  // 快捷指令
  const {
    showCommandPalette,
    filteredItems: commandItems,
    selectedIndex: commandSelectedIndex,
    executeCommand,
    handleKeyDown: handleCommandKeyDown,
  } = useSlashCommand(inputMessage, cursorPosition);

  // @ 结构化引用
  const {
    isOpen: showReferenceMention,
    results: referenceMentionResults,
    selectedIndex: referenceMentionSelectedIndex,
    query: referenceMentionQuery,
    selectReference,
    handleKeyDown: handleReferenceMentionKeyDown,
  } = useReferenceMention(inputMessage, cursorPosition);

  // 拖拽上传
  const { isDragging, dragHandlers } = useDragDrop({
    onFilesSelected: (selectedFiles) => {
      void handleDroppedFiles(selectedFiles);
    },
    accept: [
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
    ],
    maxFiles: 20,
    disabled: loading || actionMode === 'fast',
  });

  return (
    <>
      <div
        className={
          isExpanded
            ? 'fixed inset-0 z-50 flex flex-col justify-end bg-background/95 backdrop-blur-sm p-4 sm:p-6'
            : 'relative w-full'
        }
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSubmit();
          }}
          onKeyDown={(e) => {
            // IME 组合输入阶段不拦截按键，避免回车键误发送或触发快捷指令。
            if (e.nativeEvent.isComposing) {
              return;
            }

            if (isExpanded && e.key === 'Escape') {
              e.preventDefault();
              setIsExpanded(false);
              return;
            }

            if (e.key === 'Enter' && e.ctrlKey && e.shiftKey) {
              e.preventDefault();
              setIsExpanded((prev) => !prev);
              return;
            }

            if (showCommandPalette) {
              handleCommandKeyDown(e);
              return;
            }
            if (showReferenceMention && handleReferenceMentionKeyDown(e)) {
              return;
            }

            // 输入历史弹窗键盘处理
            if (inputHistory.handleKeyDown(e)) {
              if (inputHistory.popup.open && (e.key === 'Tab' || e.key === 'Enter')) {
                const text = inputHistory.confirm();
                if (text) setInputMessage(text);
              }
              return;
            }

            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSubmit();
            }
          }}
          className="w-full"
          {...dragHandlers}
        >
          {/* 快捷指令面板 */}
          <CommandPalette
            open={showCommandPalette}
            items={commandItems}
            selectedIndex={commandSelectedIndex}
            onSelect={executeCommand}
            anchorEl={inputRef.current}
          />

          {/* @ 引用面板 */}
          <ReferenceMentionPopover
            open={showReferenceMention}
            results={referenceMentionResults}
            selectedIndex={referenceMentionSelectedIndex}
            query={referenceMentionQuery}
            onSelect={(reference) => selectReference(reference, setInputMessage)}
            anchorEl={inputRef.current}
          />

          {/* 拖拽上传 Overlay */}
          {isDragging && (
            <div className="absolute inset-0 z-50 flex items-center justify-center bg-primary/10 backdrop-blur-sm border-2 border-dashed border-primary rounded-lg pointer-events-none">
              <div className="text-center">
                <div className="text-2xl font-semibold text-primary mb-2">{chatT('dragDrop.title')}</div>
                <div className="text-sm text-muted-foreground">{chatT('dragDrop.description')}</div>
              </div>
            </div>
          )}

          {/* 消息排队提示 */}
          <QueuedMessagesList queue={queue} editMessage={editMessage} removeMessage={removeMessage} reorder={reorder} />

          {/* 文件列表显示区域 */}
          {!hideAttachList && files.length > 0 && (
            <AttachList
              files={files}
              setFiles={setFiles}
              clearCurrentSessionMessageId={clearCurrentSessionMessageId}
              setHideAttachList={setHideAttachList}
            />
          )}

          {/* @ 引用列表 */}
          {mentionReferences.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-2">
              {mentionReferences.map((f) => (
                <span
                  key={mentionReferenceKey(f)}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary/10 text-primary text-xs border border-primary/20"
                >
                  <span className="truncate max-w-[180px]" title={f.path ?? f.fileId ?? f.url ?? f.label}>
                    {f.label}
                  </span>
                  <button
                    type="button"
                    onClick={() => removeMentionReference(mentionReferenceKey(f))}
                    className="hover:text-destructive transition-colors"
                    aria-label={chatT('fileMention.removeReference', { label: f.label })}
                  >
                    <X size={12} />
                  </button>
                </span>
              ))}
            </div>
          )}

          {/* 动态工作记忆面板 (Active Working Memory) */}
          <ActiveWorkingMemoryPanel />

          <div className="flex flex-col bg-secondary px-3 sm:px-5 pt-5 pb-2 rounded-lg w-full border border-border relative">
            {/* 输入历史弹窗 */}
            <InputHistoryPopup
              popup={inputHistory.popup}
              onSelect={(index) => {
                const text = inputHistory.confirm(index);
                if (text) setInputMessage(text);
              }}
              onHover={inputHistory.setActiveIndex}
              onClose={inputHistory.close}
            />
            <QuoteCard />
            {isComposerClarifyMode && pendingClarification ? (
              <ClarificationInput
                messageId={pendingClarification.messageId}
                answered={pendingClarification.clarification.answered}
                options={pendingClarification.clarification.options}
                allowMultiple={pendingClarification.clarification.allowMultiple}
                isResumeMode={pendingClarification.clarification.isResumeMode}
                title={pendingClarification.clarification.title}
                form={pendingClarification.clarification.form}
                variant="composer"
              />
            ) : (
              <>
            {pendingExplicitSkillActivation ? (
              <SkillActivationChips
                skillNames={pendingExplicitSkillActivation.skillNames}
                instruction={pendingExplicitSkillActivation.instruction}
                className="mb-2"
                onRemove={() => setPendingExplicitSkillActivation(null)}
              />
            ) : null}
            <TextareaAutosize
              ref={inputRef}
              data-chat-input
              value={inputMessage}
              onChange={(e) => {
                handleInputChange(e);
                updateCursorPosition();
                if (inputHistory.popup.open) inputHistory.close();
              }}
              onPaste={handlePaste}
              onKeyUp={updateCursorPosition}
              onClick={updateCursorPosition}
              minRows={2}
              className={`bg-transparent placeholder:text-muted-foreground/50 text-sm text-black dark:text-white resize-none focus:outline-none w-full ${isExpanded ? 'max-h-[75vh]' : 'max-h-24 sm:max-h-[35vh] lg:max-h-[40vh]'}`}
              placeholder={
                inputHistory.ghostText
                  ? inputHistory.ghostText
                  : isUploadingPaste
                    ? chatT('input.uploadingImage')
                    : loading
                      ? chatT('queue.placeholder')
                      : chatT('input.placeholder')
              }
              readOnly={isUploadingPaste}
            />
            {/* 操作栏 */}
            <div className="flex flex-row items-center justify-between mt-4 gap-2">
              {/* 左侧：功能按钮 */}
              <div className="flex flex-row items-center gap-1 sm:gap-2 min-w-0 flex-1">
                {/* 移动端精简版：+ 按钮触发 ActionSheet + 核心快捷入口 */}
                <div className="flex sm:hidden flex-row items-center gap-1 shrink-0">
                  <button
                    type="button"
                    onClick={() => setIsMobileSheetOpen(true)}
                    className="flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground hover:bg-muted-foreground/20 transition-colors"
                    aria-label={chatT('input.expandToolbar')}
                    data-testid="sendbox-mobile-plus-btn"
                  >
                    <Plus size={16} />
                  </button>
                  <SearchModeSelector actionMode={actionMode} setActionMode={setActionMode} />
                </div>
                {/* 桌面版：可横向滚动，避免工具栏互相挤压 */}
                <div className="hidden sm:flex flex-row flex-nowrap items-center gap-2 min-w-0 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden [&>*]:shrink-0">
                  <SearchModeSelector actionMode={actionMode} setActionMode={setActionMode} />
                  <DeepSearchToggle />
                  <WorkflowModeToggle />
                  <BaseModelSelector />
                  <ThinkingIntensityButton actionMode={actionMode} agentConfig={agentConfig} />
                  <GoalModeToggle />
                  <IncognitoModeToggle />
                  <SandboxModeToggle />
                  <SecurityPresetSelector />
                  <FocusFlushButton />
                  {chatId && messages.length > 0 && !loading && (
                    <ForkButton chatId={chatId} messageIndex={messages.length - 1} />
                  )}
                  <AgentIndicator />
                  <SessionSkillsToggle />
                  <TurnCapabilityToggle
                    selection={turnCapabilitySelection}
                    onSelectionChange={setTurnCapabilitySelection}
                    disabled={loading}
                  />
                  <ToolsPanel />
                  {!hideChatWorkspacePicker && <WorkspaceDirPicker />}
                  <button
                    type="button"
                    onClick={() => setIsExpanded((prev) => !prev)}
                    className="flex size-7 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                    aria-label={isExpanded ? 'Collapse editor' : 'Expand editor'}
                    title="Ctrl+Shift+Enter"
                  >
                    {isExpanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
                  </button>
                </div>
              </div>
              {/* 右侧：发送操作 */}
              <div className="flex flex-row items-center gap-1 sm:gap-2 flex-shrink-0">
                <div className="flex items-center gap-1 overflow-x-auto max-w-[45vw] sm:max-w-none">
                  <WorkUnitBalanceBar compact className="shrink-0" />
                  <SessionSpendSurface className="shrink-0" />
                  <ContextUsageIndicator />
                  <ReadinessBadge />
                  <LivenessIndicator />
                  <div className="hidden sm:flex items-center gap-1">
                    <EnvironmentShield />
                    <BudgetBadge />
                  </div>
                </div>
                {/* 附件按钮在所有设备上都显示在右侧 */}
                {actionMode !== 'fast' && <AttachButton files={files} setFiles={setFiles} />}
                {isVoiceEnabled && (
                  <SpeechInputButton onTranscript={handleTranscript} disabled={loading} keyterms={keyterms} />
                )}
                {isVoiceEnabled && <VoiceSessionButton disabled={loading} keyterms={keyterms} />}
                {loading ? (
                  <div className="flex items-center gap-1">
                    {inputMessage.trim().length > 0 || pendingExplicitSkillActivation ? (
                      <>
                        <button
                          type="button"
                          onClick={handleRedirectSubmit}
                          className="bg-primary text-primary-foreground hover:bg-primary/80 transition duration-100 rounded-full p-2"
                          aria-label={chatT('redirect.send')}
                          title={chatT('redirect.tooltip')}
                        >
                          <CornerDownLeft size={17} />
                        </button>
                        <button
                          type="button"
                          onClick={handleSteerSubmit}
                          className="bg-muted-foreground/20 text-foreground hover:bg-muted-foreground/30 transition duration-100 rounded-full p-2"
                          aria-label={chatT('steer.send')}
                          title={chatT('steer.tooltip')}
                        >
                          <Navigation size={17} />
                        </button>
                        <button
                          type="button"
                          onClick={handleQueueSubmit}
                          className="bg-accent/60 text-white hover:bg-accent/80 transition duration-100 rounded-full p-2"
                          aria-label={chatT('queue.sendLater')}
                          title={chatT('queue.sendLaterTooltip')}
                        >
                          <ListPlus size={17} />
                        </button>
                      </>
                    ) : null}
                    <button
                      type="button"
                      onClick={stopMessage}
                      className="bg-slate-500 dark:bg-white text-white dark:text-black hover:bg-black/80 dark:hover:bg-white/80 transition duration-100 rounded-full p-2"
                      aria-label="Stop"
                    >
                      <Square size={17} />
                    </button>
                  </div>
                ) : (
                  <span className="brand-elevation-slot">
                    <button
                      type="button"
                      onClick={() => {
                        void handleSubmit();
                      }}
                      disabled={
                        inputMessage.trim().length === 0 &&
                        files.length === 0 &&
                        !pendingExplicitSkillActivation
                      }
                      className="message-send-btn btn-brand-elevation bg-primary text-primary-foreground disabled:text-black/50 dark:disabled:text-white/50 disabled:bg-muted dark:disabled:bg-muted/30 hover:bg-primary-hover rounded-full p-2"
                      aria-label={commonT('send')}
                    >
                      <ArrowRight size={17} />
                    </button>
                  </span>
                )}
              </div>
            </div>
              </>
            )}
          </div>
        </form>
      </div>

      {/* 链接检测对话框 */}
      <LinkDetectionDialog
        open={showLinkDialog}
        onOpenChange={setShowLinkDialog}
        dontRemindAgain={dontRemindAgain}
        setDontRemindAgain={setDontRemindAgain}
        onAddAtSymbol={handleAddAtSymbol}
        onSkip={handleSkipAtSymbol}
      />

      {/* 压缩确认对话框 */}
      <AlertDialog open={showCompactConfirm} onOpenChange={setShowCompactConfirm}>
        <AlertDialogContent className="sm:max-w-[425px]">
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2 text-amber-500">
              <AlertTriangle size={20} />
              {chatT('compact.confirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription className="text-base pt-2">
              {chatT('compact.confirmDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>

          <div className="flex items-center space-x-2 py-2">
            <input
              type="checkbox"
              id="dontRemindCompact"
              checked={dontRemindCompact}
              onChange={(e) => setDontRemindCompact(e.target.checked)}
              className="h-4 w-4 text-primary border-gray-300 rounded focus:ring-primary"
            />
            <label htmlFor="dontRemindCompact" className="text-sm text-muted-foreground">
              {chatT('compact.dontRemindAgain')}
            </label>
          </div>

          <AlertDialogFooter>
            <AlertDialogCancel>{commonT('cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={confirmCompact} className="bg-amber-500 text-white hover:bg-amber-600">
              {chatT('compact.confirmButton')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* 移动端 ActionSheet */}
      <MobileActionSheet
        open={isMobileSheetOpen}
        onClose={() => setIsMobileSheetOpen(false)}
        title={chatT('input.expandToolbar')}
        entries={mobileSheetEntries}
        footer={
          <>
            <DeepSearchToggle />
            <WorkflowModeToggle />
            <IncognitoModeToggle />
            <SandboxModeToggle />
            <SecurityPresetSelector />
            <AgentIndicator />
            <TurnCapabilityToggle
              selection={turnCapabilitySelection}
              onSelectionChange={setTurnCapabilitySelection}
              disabled={loading}
            />
          </>
        }
      />
    </>
  );
};

export default MessageInput;
