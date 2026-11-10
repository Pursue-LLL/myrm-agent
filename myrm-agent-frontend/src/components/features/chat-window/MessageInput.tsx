/**
 * [INPUT]
 * - @/hooks/message-input/useMessageInput::useMessageInput (POS: 聊天输入状态与提交编排)
 * - ./composer/* (POS: 输入区的文本区、发送控制、面板开合、拖放与按键分流)
 * - ./composer-options/{ComposerPrimaryControls,ComposerOptionsRegion} (POS: 桌面主行与选项区)
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线)
 *
 * [OUTPUT]
 * - MessageInput: 聊天输入区：把输入状态、各面板与发送控制装配成一个表单。
 *
 * [POS]
 * 聊天输入区的装配层：持有各块之间需要共享的状态（编辑器是否全屏、光标位置、斜杠与 @ 面板、历史弹窗），
 * 把它们接到 `composer/` 下各自负责展示或分流的单元上。桌面主行与选项区由 composer-options 承载，手机用「+」打开操作表。
 */
import { useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';

import { CommandPalette } from '@/components/features/app-shell/command-palette';
import { useMessageInput } from '@/hooks/message-input/useMessageInput';
import { useComposerContextChips } from '@/hooks/message-input/useComposerContextChips';
import { useInputHistory } from '@/hooks/message-input/useInputHistory';
import { useReferenceMention } from '@/hooks/message-input/useReferenceMention';
import { useSlashCommand } from '@/hooks/message-input/useSlashCommand';
import { findActivePendingClarification } from '@/store/chat/clarificationState';
import useChatStore from '@/store/useChatStore';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';

import ActiveFilesPanel from '../message-input-actions/ActiveFilesPanel';
import AttachButton from '../message-input-actions/AttachButton';
import AttachList from '../message-input-actions/AttachList';
import ProviderLowBalanceWarningHUD from '../message-input-actions/ProviderLowBalanceWarningHUD';
import ClarificationInput from '../message-box/ClarificationInput';
import { ContextSpilloverBadge } from '../message-box/ContextSpilloverBadge';
import { FeaturedExpertChips } from './agent-config-panel/FeaturedExpertChips';
import { CompactConfirmDialog } from './composer/CompactConfirmDialog';
import { ComposerDropOverlay } from './composer/ComposerDropOverlay';
import { ComposerSendControls } from './composer/ComposerSendControls';
import { ComposerStatusIndicators } from './composer/ComposerStatusIndicators';
import { ComposerTextarea } from './composer/ComposerTextarea';
import { ComposerVoiceActions } from './composer/ComposerVoiceActions';
import { handleComposerKeyDown } from './composer/composerKeyDown';
import { MobileComposerEntry } from './composer/MobileComposerEntry';
import { MobileComposerSheet } from './composer/MobileComposerSheet';
import { useCaretPosition } from './composer/useCaretPosition';
import { useComposerDragDrop } from './composer/useComposerDragDrop';
import { useComposerPanels } from './composer/useComposerPanels';
import { useHideChatWorkspacePicker } from './composer/useHideChatWorkspacePicker';
import { ComposerOptionsRegion } from './composer-options/ComposerOptionsRegion';
import { ComposerPrimaryControls } from './composer-options/ComposerPrimaryControls';
import { ComposerContextChipStrip } from './context-strip/ComposerContextChipStrip';
import { SkillRequiredConnectorsPreflightBanner } from './context-strip/SkillRequiredConnectorsPreflightBanner';
import InputHistoryPopup from './InputHistoryPopup';
import { LinkDetectionDialog } from './LinkDetectionDialog';
import ProjectBoundaryBadge from './ProjectBoundaryBadge';
import { QueuedMessagesList } from './QueuedMessagesList';
import { QuoteCard } from './QuoteCard';
import { ReferenceMentionPopover } from './ReferenceMentionPopover';
import { ScopedArtifactChip } from './ScopedArtifactChip';
import SessionAccessRootsBar from './SessionAccessRootsBar';
import { ChatInlineTeamRunVisibilityStrip } from './subagent/ChatInlineTeamRunVisibilityStrip';
import { WechatArticleComposerHint } from './WechatArticleComposerHint';
import WorkspaceDirPicker from './WorkspaceDirPicker';

interface MessageInputProps {
  loading: boolean;
  /** The empty chat's composer takes the cursor on mount, where a keyboard is at hand. */
  focusOnMount?: boolean;
}

const MessageInput = ({ loading, focusOnMount }: MessageInputProps) => {
  const commandsT = useTranslations('commands');
  const messages = useChatStore((s) => s.messages);
  const agentId = useChatStore((s) => s.agentConfig?.agentId);
  const mentionReferences = useChatStore((s) => s.mentionReferences);
  const removeMentionReference = useChatStore((s) => s.removeMentionReference);
  const isVoiceEnabled = useFeatureGateStore((s) => s.isEnabled('voice_interaction'));
  const hideChatWorkspacePicker = useHideChatWorkspacePicker();
  const pendingClarification = useMemo(() => findActivePendingClarification(messages), [messages]);

  const [isExpanded, setIsExpanded] = useState(false);
  const panels = useComposerPanels();

  const {
    showLinkDialog,
    dontRemindAgain,
    setDontRemindAgain,
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
    queuePausedReason,
    queueEditingId,
    editMessage,
    removeMessage,
    reorder,
    setQueueEditingId,
    resumeQueue,
  } = useMessageInput();

  const showBtwDisambiguation = useMemo(
    () => loading && /^\/(?:btw|bg)\b/i.test(inputMessage.trim()),
    [loading, inputMessage],
  );

  const inputHistory = useInputHistory({
    agentId,
    getInputValue: () => inputMessage,
  });

  const { chips: composerContextChips, summary: composerContextSummary } = useComposerContextChips({
    turnCapabilitySelection,
    setTurnCapabilitySelection,
    files,
    setFiles,
    clearCurrentSessionMessageId,
    mentionReferences,
    removeMentionReference,
    onOpenCapabilityEditor: panels.openCapabilityEditor,
    hideAttachList,
  });

  const { caret, syncCaret } = useCaretPosition(inputRef, inputMessage);

  const {
    showCommandPalette,
    filteredItems: commandItems,
    selectedIndex: commandSelectedIndex,
    executeCommand,
    handleKeyDown: handleCommandKeyDown,
  } = useSlashCommand(inputMessage, caret);

  const {
    isOpen: showReferenceMention,
    results: referenceMentionResults,
    selectedIndex: referenceMentionSelectedIndex,
    query: referenceMentionQuery,
    selectReference,
    handleKeyDown: handleReferenceMentionKeyDown,
  } = useReferenceMention(inputMessage, caret);

  const { dragHandlers, isDragging, isSessionDragging } = useComposerDragDrop({
    disabled: loading || actionMode === 'fast',
    onFilesSelected: handleDroppedFiles,
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
        {/* oxlint-disable-next-line jsx-a11y/no-noninteractive-element-interactions -- key delegation from focusable children */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void handleSubmit();
          }}
          onKeyDown={(e) =>
            handleComposerKeyDown(e, {
              inputMessage,
              setInputMessage,
              chips: composerContextChips,
              loading,
              editorExpanded: isExpanded,
              setEditorExpanded: setIsExpanded,
              showCommandPalette,
              onCommandKeyDown: handleCommandKeyDown,
              showReferenceMention,
              onReferenceMentionKeyDown: handleReferenceMentionKeyDown,
              inputHistory,
              submit: handleSubmit,
              queue: handleQueueSubmit,
            })
          }
          className="w-full"
          {...dragHandlers}
        >
          <CommandPalette
            open={showCommandPalette}
            items={commandItems}
            selectedIndex={commandSelectedIndex}
            onSelect={executeCommand}
            anchorRef={inputRef}
          />

          <ReferenceMentionPopover
            open={showReferenceMention}
            results={referenceMentionResults}
            selectedIndex={referenceMentionSelectedIndex}
            query={referenceMentionQuery}
            onSelect={(reference) => selectReference(reference, setInputMessage)}
            anchorRef={inputRef}
          />

          {isDragging && <ComposerDropOverlay session={isSessionDragging} />}

          <QueuedMessagesList
            queue={queue}
            pausedReason={queuePausedReason}
            editingId={queueEditingId}
            setEditingId={setQueueEditingId}
            editMessage={editMessage}
            removeMessage={removeMessage}
            reorder={reorder}
            resume={resumeQueue}
          />

          {!hideAttachList && files.length > 0 && (
            <AttachList
              files={files}
              setFiles={setFiles}
              clearCurrentSessionMessageId={clearCurrentSessionMessageId}
              setHideAttachList={setHideAttachList}
            />
          )}

          <ActiveFilesPanel />

          <ChatInlineTeamRunVisibilityStrip />

          <div
            className="flex flex-col bg-secondary px-3 sm:px-5 pt-5 pb-2 rounded-lg w-full border border-border relative"
            data-chat-composer
          >
            <InputHistoryPopup
              popup={inputHistory.popup}
              onSelect={(index) => {
                const text = inputHistory.confirm(index);
                if (text) {
                  setInputMessage(text);
                }
              }}
              onHover={inputHistory.setActiveIndex}
              onClose={inputHistory.close}
            />
            <QuoteCard />
            <ProjectBoundaryBadge />
            <SessionAccessRootsBar />
            {pendingClarification ? (
              <ClarificationInput
                messageId={pendingClarification.messageId}
                answered={pendingClarification.clarification.answered}
                options={pendingClarification.clarification.options}
                allowMultiple={pendingClarification.clarification.allowMultiple}
                title={pendingClarification.clarification.title}
                form={pendingClarification.clarification.form}
                variant="composer"
              />
            ) : (
              <>
                <ProviderLowBalanceWarningHUD className="mb-2" />
                <FeaturedExpertChips />
                <ScopedArtifactChip />
                <SkillRequiredConnectorsPreflightBanner
                  activeSkillIds={turnCapabilitySelection?.skillIds ?? null}
                  onOpenCapabilityEditor={panels.openCapabilityEditor}
                />
                <ComposerContextChipStrip
                  chips={composerContextChips}
                  summary={composerContextSummary}
                  disabled={loading}
                  onOpenCapabilityEditor={panels.openCapabilityEditor}
                />
                <ContextSpilloverBadge text={inputMessage} />
                <WechatArticleComposerHint inputMessage={inputMessage} />
                {showBtwDisambiguation ? (
                  <p className="mb-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
                    {commandsT('builtin.btwDisambiguation')}
                  </p>
                ) : null}
                <ComposerTextarea
                  inputRef={inputRef}
                  value={inputMessage}
                  loading={loading}
                  hasFiles={files.length > 0}
                  expanded={isExpanded}
                  ghostText={inputHistory.ghostText}
                  focusOnMount={focusOnMount}
                  onChange={(e) => {
                    handleInputChange(e);
                    syncCaret();
                    if (inputHistory.popup.open) {
                      inputHistory.close();
                    }
                  }}
                  onPaste={handlePaste}
                  onCaretMove={syncCaret}
                />
                {!hideChatWorkspacePicker && <WorkspaceDirPicker />}
                <div className="flex flex-row items-center justify-between mt-4 gap-2">
                  <div className="flex flex-row items-center gap-1 sm:gap-2 min-w-0 flex-1">
                    <MobileComposerEntry
                      actionMode={actionMode}
                      setActionMode={setActionMode}
                      onOpenSheet={panels.openMobileSheet}
                    />
                    <ComposerPrimaryControls
                      optionsExpanded={panels.optionsExpanded}
                      optionsRegionId={panels.optionsRegionId}
                      onToggleOptions={panels.toggleOptions}
                      actionMode={actionMode}
                      setActionMode={setActionMode}
                      editorExpanded={isExpanded}
                      onToggleEditor={() => setIsExpanded((prev) => !prev)}
                    />
                  </div>
                  <div className="flex flex-row items-center gap-1 sm:gap-2 flex-shrink-0">
                    <ComposerStatusIndicators />
                    {actionMode !== 'fast' && <AttachButton files={files} setFiles={setFiles} />}
                    {isVoiceEnabled && (
                      <ComposerVoiceActions inputRef={inputRef} setInputMessage={setInputMessage} disabled={loading} />
                    )}
                    <ComposerSendControls
                      loading={loading}
                      inputMessage={inputMessage}
                      hasFiles={files.length > 0}
                      onStop={stopMessage}
                      onRedirect={handleRedirectSubmit}
                      onSteer={handleSteerSubmit}
                      onQueue={handleQueueSubmit}
                      onSend={handleSubmit}
                    />
                  </div>
                </div>
                <ComposerOptionsRegion
                  id={panels.optionsRegionId}
                  expanded={panels.optionsExpanded}
                  loading={loading}
                  turnCapabilitySelection={turnCapabilitySelection}
                  onTurnCapabilityChange={setTurnCapabilitySelection}
                  turnCapabilityOpen={panels.isTurnCapabilityOpen}
                  onTurnCapabilityOpenChange={panels.setIsTurnCapabilityOpen}
                />
              </>
            )}
          </div>
        </form>
      </div>

      <LinkDetectionDialog
        open={showLinkDialog}
        dontRemindAgain={dontRemindAgain}
        setDontRemindAgain={setDontRemindAgain}
        onAddAtSymbol={handleAddAtSymbol}
        onSkip={handleSkipAtSymbol}
      />

      <CompactConfirmDialog
        open={showCompactConfirm}
        onOpenChange={setShowCompactConfirm}
        dontRemind={dontRemindCompact}
        onDontRemindChange={setDontRemindCompact}
        onConfirm={confirmCompact}
      />

      <MobileComposerSheet
        open={panels.isMobileSheetOpen}
        onClose={panels.closeMobileSheet}
        loading={loading}
        turnCapabilitySelection={turnCapabilitySelection}
        onTurnCapabilityChange={setTurnCapabilitySelection}
      />
    </>
  );
};

export default MessageInput;
