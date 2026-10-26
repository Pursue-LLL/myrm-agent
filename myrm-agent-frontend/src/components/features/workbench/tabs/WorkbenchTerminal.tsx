'use client';

/**
 * [INPUT]
 * - executeTerminalCommand, TERMINAL_TIMEOUT_SECONDS from @/services/workbench
 * - useWorkbenchStore from @/store/useWorkbenchStore
 * - useChatStore from @/store/useChatStore (POS: the composer a command's output is handed to)
 * - ./terminalOutput (POS: snippet building and failure classification)
 * - useTranslations from next-intl (namespace: 'workbench.terminal')
 *
 * [OUTPUT]
 * - WorkbenchTerminal: Command terminal of one chat's workspace with command history & chat injection
 *
 * [POS]
 * Auxiliary Workbench Terminal tab component. A request that fails is written into the history in the user's
 * language; the server's own message never reaches the screen.
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import {
  Terminal,
  Play,
  Trash2,
  Share2,
  Loader2,
  CheckCircle2,
  AlertCircle,
  CornerDownLeft,
} from 'lucide-react';
import { executeTerminalCommand, TERMINAL_TIMEOUT_SECONDS } from '@/services/workbench';
import useChatStore from '@/store/useChatStore';
import { useWorkbenchStore, type TerminalLogEntry } from '@/store/useWorkbenchStore';
import { appendToComposer, buildTerminalSnippet, classifyTerminalFailure } from './terminalOutput';

interface WorkbenchTerminalProps {
  chatId: string;
}

export function WorkbenchTerminal({ chatId }: WorkbenchTerminalProps) {
  const t = useTranslations('workbench.terminal');
  const [inputCommand, setInputCommand] = useState<string>('');
  const [isExecuting, setIsExecuting] = useState<boolean>(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const logs = useWorkbenchStore((s) => s.terminalLogs);
  const addTerminalLog = useWorkbenchStore((s) => s.addTerminalLog);
  const clearTerminalLogs = useWorkbenchStore((s) => s.clearTerminalLogs);

  // Auto-scroll to bottom on new logs
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  const handleRunCommand = useCallback(async () => {
    const cmd = inputCommand.trim();
    if (!cmd || isExecuting) {
      return;
    }

    setIsExecuting(true);
    setInputCommand('');

    // Output belongs to the session that ran the command; after a chat switch it is dropped.
    const { sessionEpoch } = useWorkbenchStore.getState();
    const isCurrentSession = (): boolean => useWorkbenchStore.getState().sessionEpoch === sessionEpoch;

    try {
      const res = await executeTerminalCommand(chatId, cmd);
      if (!isCurrentSession()) {
        return;
      }
      const output = res.stdout || res.stderr || t('noOutput');
      addTerminalLog({
        command: cmd,
        output: res.truncated ? `${output}\n${t('outputTruncated')}` : output,
        exitCode: res.exit_code,
      });
    } catch (err: unknown) {
      if (!isCurrentSession()) {
        return;
      }
      const explanations = {
        blocked: t('blocked'),
        workspaceUnavailable: t('workspaceUnavailable'),
        timedOut: t('timedOut', { seconds: TERMINAL_TIMEOUT_SECONDS }),
        failed: t('runFailed'),
      };
      addTerminalLog({ command: cmd, output: explanations[classifyTerminalFailure(err)], exitCode: null });
    } finally {
      setIsExecuting(false);
    }
  }, [chatId, inputCommand, isExecuting, addTerminalLog, t]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      void handleRunCommand();
    }
  };

  const handleInjectToChat = useCallback(
    (log: TerminalLogEntry) => {
      const snippet = buildTerminalSnippet({
        command: log.command,
        output: log.output,
        omittedMarker: t('injectOmitted'),
      });
      const { inputMessage, setInputMessage } = useChatStore.getState();
      setInputMessage(appendToComposer(inputMessage, snippet));
      toast.success(t('injected'));
    },
    [t],
  );

  return (
    <div className="flex flex-col h-full overflow-hidden text-foreground bg-background">
      {/* Terminal Header Toolbar */}
      <div className="p-2 border-b border-border/60 flex items-center justify-between gap-2 bg-card/60 text-xs">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-emerald-500" />
          <span className="font-mono font-semibold">{t('headerTitle')}</span>
          <span className="text-[10px] text-muted-foreground font-mono">
            {logs.length} {t('historyEntries')}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={clearTerminalLogs}
            disabled={logs.length === 0}
            className="flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-mono text-muted-foreground hover:text-foreground hover:bg-muted transition-colors disabled:opacity-40"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>{t('clearAction')}</span>
          </button>
        </div>
      </div>

      {/* Terminal Log Console */}
      <div
        ref={scrollRef}
        className="flex-1 p-3 overflow-y-auto font-mono text-xs flex flex-col gap-3 bg-black/90 text-emerald-400 select-text"
      >
        {logs.length === 0 ? (
          <div className="text-muted-foreground/60 text-center my-auto flex flex-col items-center gap-2">
            <Terminal className="w-8 h-8 opacity-40 text-muted-foreground" />
            <span>{t('emptyTerminalHint')}</span>
          </div>
        ) : (
          logs.map((log) => (
            <div
              key={log.id}
              className="flex flex-col gap-1 p-2 rounded-lg bg-zinc-900/80 border border-zinc-800 text-foreground"
            >
              <div className="flex items-center justify-between gap-2 text-[11px] border-b border-zinc-800/80 pb-1">
                <div className="flex items-center gap-1.5 font-mono text-amber-400 truncate">
                  <span className="text-emerald-500 select-none">$</span>
                  <span className="font-bold">{log.command}</span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span
                    className={`flex items-center gap-1 px-1.5 py-0.2 rounded text-[10px] font-mono ${
                      log.exitCode === 0
                        ? 'bg-emerald-500/20 text-emerald-400'
                        : 'bg-rose-500/20 text-rose-400'
                    }`}
                  >
                    {log.exitCode === 0 ? (
                      <CheckCircle2 className="w-2.5 h-2.5" />
                    ) : (
                      <AlertCircle className="w-2.5 h-2.5" />
                    )}
                    <span>{log.exitCode === null ? t('failedBadge') : t('exitCode', { code: log.exitCode })}</span>
                  </span>

                  {log.exitCode !== null && (
                    <button
                      type="button"
                      onClick={() => handleInjectToChat(log)}
                      className="p-1 rounded text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
                      title={t('injectToChat')}
                      aria-label={t('injectToChat')}
                    >
                      <Share2 className="w-3 h-3" />
                    </button>
                  )}
                </div>
              </div>

              <pre className="whitespace-pre-wrap text-[11px] font-mono leading-relaxed text-zinc-300 max-h-48 overflow-y-auto pt-1">
                {log.output}
              </pre>
            </div>
          ))
        )}
      </div>

      {/* Terminal Input Prompt */}
      <div className="p-2 border-t border-border/60 bg-card/70 flex items-center gap-2">
        <span className="font-mono text-emerald-500 font-bold select-none text-xs pl-1">
          $
        </span>
        <input
          type="text"
          value={inputCommand}
          onChange={(e) => setInputCommand(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isExecuting}
          placeholder={t('inputPlaceholder')}
          className="flex-1 bg-background border border-border/80 rounded-lg px-2.5 py-1 text-xs font-mono focus:outline-hidden focus:ring-1 focus:ring-primary disabled:opacity-50"
        />
        <button
          type="button"
          onClick={() => void handleRunCommand()}
          disabled={!inputCommand.trim() || isExecuting}
          className="flex items-center gap-1 px-3 py-1 rounded-lg bg-primary text-primary-foreground font-medium text-xs hover:bg-primary/90 transition-colors disabled:opacity-40"
        >
          {isExecuting ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Play className="w-3.5 h-3.5" />
          )}
          <span>{t('runAction')}</span>
        </button>
      </div>
    </div>
  );
}
