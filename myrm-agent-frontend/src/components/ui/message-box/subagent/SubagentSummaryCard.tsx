import React, { useState, useEffect } from 'react';
import {
  Bot,
  Clock,
  Loader2,
  CheckCircle2,
  XCircle,
  Ban,
  MessageSquarePlus,
  TerminalSquare,
  AlertTriangle,
} from 'lucide-react';
import useSubagentStore from '@/store/useSubagentStore';
import { toast } from '@/lib/utils/toast';
import { SubagentLogDrawer } from './SubagentLogDrawer';
import { useTranslations } from 'next-intl';

interface Props {
  taskId: string;
  messageId: string;
}

const postSubagentAction = async (messageId: string, taskId: string, action: 'cancel' | 'steer', message?: string) => {
  const response = await fetch(`/api/chats/${messageId}/subagents/${taskId}/${action}`, {
    method: 'POST',
    headers: action === 'steer' ? { 'Content-Type': 'application/json' } : undefined,
    body: action === 'steer' ? JSON.stringify({ message }) : undefined,
  });

  if (!response.ok) {
    throw new Error(`Failed to ${action} subagent`);
  }
};

const OVERTIME_THRESHOLD_MS = 60_000;
const OVERTIME_NO_ETA_THRESHOLD_MS = 90_000;

export const SubagentSummaryCard: React.FC<Props> = ({ taskId, messageId }) => {
  const t = useTranslations('subagentDashboard');
  const subagent = useSubagentStore((state) => state.subagents[taskId]);
  const [isLogOpen, setIsLogOpen] = useState(false);
  const [isSteering, setIsSteering] = useState(false);
  const [steerText, setSteerText] = useState('');
  const [overtimeDismissed, setOvertimeDismissed] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);

  const isRunning = subagent?.status === 'running';
  useEffect(() => {
    if (!isRunning || !subagent?.createdAt) return;
    setElapsedMs(Date.now() - subagent.createdAt);
    const timer = setInterval(() => setElapsedMs(Date.now() - subagent.createdAt), 1000);
    return () => clearInterval(timer);
  }, [isRunning, subagent?.createdAt]);

  if (!subagent) return null;

  const isOvertime =
    isRunning &&
    !overtimeDismissed &&
    elapsedMs > OVERTIME_THRESHOLD_MS &&
    (subagent.progressPercent < 30 || elapsedMs > OVERTIME_NO_ETA_THRESHOLD_MS);

  const handleCancel = async () => {
    if (!isRunning) return;
    try {
      await postSubagentAction(messageId, taskId, 'cancel');
      useSubagentStore.getState().cancelSubagent(taskId, 'user_cancelled');
      toast.success('Agent task cancelled');
    } catch {
      toast.error('Failed to cancel agent');
    }
  };

  const handleSteer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!steerText.trim() || !isRunning) return;

    try {
      await postSubagentAction(messageId, taskId, 'steer', steerText);
      useSubagentStore.getState().addLog({
        task_id: taskId,
        level: 'INFO',
        message: `User Steered: ${steerText}`,
      });
      setSteerText('');
      setIsSteering(false);
      toast.success('Steering instruction sent');
    } catch {
      toast.error('Failed to send instruction');
    }
  };

  return (
    <div className="flex flex-col mb-3 border dark:border-zinc-800 rounded-lg overflow-hidden bg-white dark:bg-zinc-900/50 text-sm">
      <div className="flex items-center justify-between p-3 border-b dark:border-zinc-800/50">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <div className="p-1.5 rounded-full bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400">
            <Bot className="w-4 h-4" />
          </div>
          <div className="flex flex-col min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-zinc-900 dark:text-zinc-100 truncate">
                {subagent.description || subagent.agentType}
              </span>
              <span className="text-xs text-zinc-500 dark:text-zinc-400 font-mono">
                #{subagent.taskId.substring(0, 6)}
              </span>
            </div>
            <div className="flex items-center gap-2 mt-0.5 text-xs text-zinc-500">
              {isRunning && <Loader2 className="w-3 h-3 animate-spin text-blue-500" />}
              {subagent.status === 'completed' && <CheckCircle2 className="w-3 h-3 text-green-500" />}
              {subagent.status === 'error' && <XCircle className="w-3 h-3 text-red-500" />}
              {subagent.status === 'cancelled' && <Ban className="w-3 h-3 text-amber-500" />}
              <span className="truncate max-w-[200px]">{subagent.currentStep}</span>
              {subagent.etaReadable && isRunning && (
                <span className="flex items-center gap-1 text-zinc-400 ml-2 border-l border-zinc-200 dark:border-zinc-700 pl-2">
                  <Clock className="w-3 h-3" /> ETA: {subagent.etaReadable}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 ml-4 shrink-0">
          <button
            onClick={() => setIsLogOpen(!isLogOpen)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
          >
            <TerminalSquare className="w-3.5 h-3.5" />
            {isLogOpen ? 'Hide X-Ray' : 'X-Ray View'}
          </button>

          {isRunning && (
            <>
              <button
                onClick={() => setIsSteering(!isSteering)}
                className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
              >
                <MessageSquarePlus className="w-3.5 h-3.5" />
                Steer
              </button>
              <button
                onClick={handleCancel}
                className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
              >
                <Ban className="w-3.5 h-3.5" />
                Stop
              </button>
            </>
          )}
        </div>
      </div>

      {/* Overtime Warning */}
      {isOvertime && (
        <div className="flex items-start gap-2 px-3 py-2 bg-amber-50 dark:bg-amber-950/40 border-b border-amber-200 dark:border-amber-800 text-xs text-amber-800 dark:text-amber-200">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          <span className="flex-1">{t('overtimeDescription')}</span>
          <button
            onClick={() => setOvertimeDismissed(true)}
            className="text-amber-500 hover:text-amber-700 dark:hover:text-amber-300 shrink-0"
          >
            ✕
          </button>
        </div>
      )}

      {/* Progress Bar */}
      {isRunning && (
        <div className="h-1 bg-zinc-100 dark:bg-zinc-800 w-full overflow-hidden">
          <div
            className="h-full bg-blue-500 transition-all duration-300 ease-out"
            style={{ width: `${subagent.progressPercent}%` }}
          />
        </div>
      )}

      {/* Steering Input Area */}
      {isSteering && isRunning && (
        <div className="p-3 bg-zinc-50 dark:bg-zinc-800/50 border-b dark:border-zinc-800/50">
          <form onSubmit={handleSteer} className="flex gap-2">
            <input
              type="text"
              value={steerText}
              onChange={(e) => setSteerText(e.target.value)}
              placeholder="Give new instructions to steer the agent..."
              className="flex-1 bg-white dark:bg-zinc-900 border dark:border-zinc-700 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50"
              autoFocus
            />
            <button
              type="submit"
              disabled={!steerText.trim()}
              className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Send
            </button>
          </form>
        </div>
      )}

      {/* X-Ray Log Drawer */}
      {isLogOpen && (
        <div className="border-t dark:border-zinc-800/50 bg-zinc-50 dark:bg-zinc-900/50">
          <SubagentLogDrawer logs={subagent.logs} />
        </div>
      )}
    </div>
  );
};
