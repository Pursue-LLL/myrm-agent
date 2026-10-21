import React, { useState } from 'react';
import {
  X,
  Send,
  Sparkles,
  Bot,
  User,
  Clock,
  CheckCircle2,
  Minimize2,
  Maximize2,
  Trash2,
  Activity,
  Layers,
} from 'lucide-react';
import { useSideChatStore } from './useSideChatStore';
import { SideChatMessage } from './sideChatTypes';

export interface SideChatDrawerProps {
  onClose?: () => void;
  className?: string;
}

export const SideChatDrawer: React.FC<SideChatDrawerProps> = ({
  onClose,
  className = '',
}) => {
  const {
    isOpen,
    isDocked,
    messages,
    steeringQueue,
    mainTask,
    setOpen,
    setDocked,
    sendSideMessage,
    dismissSteeringItem,
  } = useSideChatStore();

  const [inputText, setInputText] = useState('');

  if (!isOpen) {
    return null;
  }

  const handleClose = () => {
    setOpen(false);
    if (onClose) {
      onClose();
    }
  };

  const handleSend = (e?: React.FormEvent) => {
    if (e) {
      e.preventDefault();
    }
    if (!inputText.trim()) {
      return;
    }
    sendSideMessage(inputText);
    setInputText('');
  };

  const handleQuickPrompt = (prompt: string) => {
    sendSideMessage(prompt);
  };

  const pendingCount = steeringQueue.filter((i) => i.status === 'pending').length;

  const renderStatusBadge = (msg: SideChatMessage) => {
    if (msg.steeringStatus === 'pending_injection') {
      const queueItem = steeringQueue.find(
        (i) => i.sourceMessageId === msg.id && i.status === 'pending'
      );
      return (
        <div className="flex items-center gap-1.5 mt-1 text-[11px] text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
          <Clock className="w-3 h-3 animate-spin" />
          <span>已挂入缓冲队列 · 主任务在下一步平滑吸收</span>
          {queueItem && (
            <button
              type="button"
              onClick={() => {
                dismissSteeringItem(queueItem.id);
              }}
              className="text-zinc-400 hover:text-red-400 ml-1 p-0.5 rounded"
              title="撤回该微调"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          )}
        </div>
      );
    }

    if (msg.steeringStatus === 'injected_to_main') {
      return (
        <div className="flex items-center gap-1 mt-1 text-[11px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
          <CheckCircle2 className="w-3 h-3" />
          <span>已在第 {msg.injectedAtStep || 1} 步成功吸收合入主任务</span>
        </div>
      );
    }

    if (msg.steeringStatus === 'instant_answered') {
      return (
        <div className="flex items-center gap-1 mt-1 text-[11px] text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded border border-indigo-500/20">
          <Sparkles className="w-3 h-3" />
          <span>协作者即时响应 · 未中断主任务沙箱</span>
        </div>
      );
    }

    return null;
  };

  return (
    <div
      data-testid="side-chat-drawer"
      className={`fixed inset-y-0 right-0 z-50 flex flex-col bg-zinc-900/98 backdrop-blur-md border-l border-zinc-800 shadow-2xl transition-all duration-300 ${
        isDocked ? 'w-[440px]' : 'w-96'
      } ${className}`}
    >
      {/* 头部状态与控制栏 */}
      <div className="flex items-center justify-between p-3.5 border-b border-zinc-800 bg-zinc-950/40">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <Layers className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <h3 className="text-xs font-bold text-zinc-100">平行支线对话 (Side Chat)</h3>
              {pendingCount > 0 && (
                <span className="px-1.5 py-0.2 rounded-full text-[10px] font-mono bg-amber-500/20 text-amber-300 border border-amber-500/30">
                  {pendingCount} 待吸收
                </span>
              )}
            </div>
            <div className="flex items-center gap-1 text-[10px] text-zinc-400 mt-0.5">
              <Activity className="w-2.5 h-2.5 text-emerald-400 animate-pulse" />
              <span>主任务: 第 {mainTask.currentStep}/{mainTask.totalSteps} 步运行中</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => {
              setDocked(!isDocked);
            }}
            title={isDocked ? '收窄抽屉' : '展开宽屏停靠'}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
          >
            {isDocked ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
          <button
            type="button"
            onClick={handleClose}
            title="关闭支线抽屉"
            aria-label="关闭支线抽屉"
            className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 消息历史对话流 */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-3">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-4 text-zinc-500 space-y-2">
            <Sparkles className="w-6 h-6 text-zinc-600 mb-1" />
            <p className="text-xs font-medium text-zinc-400">长任务进行中，随时发起支线交流</p>
            <p className="text-[11px] leading-relaxed max-w-[240px]">
              主任务在沙箱中推进，您在此处追加的小需求将自动排队，步间平滑吸收，绝不粗暴中断。
            </p>
          </div>
        ) : (
          messages.map((msg) => {
            if (msg.role === 'system') {
              return (
                <div
                  key={msg.id}
                  className="p-2 rounded-lg bg-zinc-950/80 border border-indigo-500/20 text-[11px] text-indigo-300 font-mono text-center leading-normal"
                >
                  {msg.content}
                </div>
              );
            }

            const isUser = msg.role === 'user';
            return (
              <div
                key={msg.id}
                className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}
              >
                <div className="flex items-center gap-1.5 mb-1 text-[10px] text-zinc-500">
                  {isUser ? (
                    <>
                      <span>您 (支线意图)</span>
                      <User className="w-3 h-3 text-indigo-400" />
                    </>
                  ) : (
                    <>
                      <Bot className="w-3 h-3 text-emerald-400" />
                      <span>轻量协作者 Agent</span>
                    </>
                  )}
                </div>

                <div
                  className={`p-2.5 rounded-xl max-w-[90%] text-xs leading-relaxed ${
                    isUser
                      ? 'bg-indigo-600 text-white rounded-tr-none shadow-md'
                      : 'bg-zinc-800 text-zinc-200 rounded-tl-none border border-zinc-700/80'
                  }`}
                >
                  {msg.content}
                  {isUser && renderStatusBadge(msg)}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* 快速意图推荐芯片 */}
      <div className="px-3 pt-2 pb-1 border-t border-zinc-850 bg-zinc-950/40">
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-[11px]">
          <span className="text-zinc-500 text-[10px] shrink-0">快捷微调:</span>
          <button
            type="button"
            onClick={() => {
              handleQuickPrompt('现在进行到哪一步了？');
            }}
            className="px-2 py-0.5 rounded-full bg-zinc-800 hover:bg-zinc-750 text-zinc-300 whitespace-nowrap shrink-0 border border-zinc-700 transition-colors"
          >
            询问进度
          </button>
          <button
            type="button"
            onClick={() => {
              handleQuickPrompt('顺手增加 Excel 导出功能');
            }}
            className="px-2 py-0.5 rounded-full bg-zinc-800 hover:bg-zinc-750 text-zinc-300 whitespace-nowrap shrink-0 border border-zinc-700 transition-colors"
          >
            + 增加导出 Excel
          </button>
          <button
            type="button"
            onClick={() => {
              handleQuickPrompt('把公式工时系数调整为 1.2');
            }}
            className="px-2 py-0.5 rounded-full bg-zinc-800 hover:bg-zinc-750 text-zinc-300 whitespace-nowrap shrink-0 border border-zinc-700 transition-colors"
          >
            调整计算系数
          </button>
        </div>
      </div>

      {/* 底部输入框 */}
      <form onSubmit={handleSend} className="p-3 border-t border-zinc-800 bg-zinc-950/80">
        <div className="relative flex items-center">
          <input
            type="text"
            value={inputText}
            onChange={(e) => {
              setInputText(e.target.value);
            }}
            placeholder="随时补充小需求或询问进度..."
            className="w-full pl-3 pr-10 py-2 text-xs bg-zinc-900 text-zinc-200 rounded-xl border border-zinc-750 focus:outline-none focus:border-indigo-500 shadow-inner font-sans"
          />
          <button
            type="submit"
            disabled={!inputText.trim()}
            className="absolute right-1.5 p-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            title="发送支线消息"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </div>
      </form>
    </div>
  );
};
