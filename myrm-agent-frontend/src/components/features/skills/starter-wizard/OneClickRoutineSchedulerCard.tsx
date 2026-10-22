import React from 'react';
import { Clock, Check, Bell, MessageSquare, Webhook, Power } from 'lucide-react';
import type { CronHostingBlueprint } from './starterWizardTypes';

interface OneClickRoutineSchedulerCardProps {
  cronBlueprint: CronHostingBlueprint;
  onToggleCronHosting: (enable: boolean) => void;
  onUpdateChannel: (channel: 'chat' | 'desktop_notification' | 'webhook') => void;
}

export const OneClickRoutineSchedulerCard: React.FC<OneClickRoutineSchedulerCardProps> = ({
  cronBlueprint,
  onToggleCronHosting,
  onUpdateChannel,
}) => {
  const isEnabled = cronBlueprint.isEnabled;

  return (
    <div className={`space-y-3 rounded-lg border p-3.5 backdrop-blur-sm transition-all ${
      isEnabled
        ? 'border-emerald-500/40 bg-emerald-950/20 shadow-sm'
        : 'border-slate-700/60 bg-slate-900/60'
    }`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Clock className={`h-4 w-4 ${isEnabled ? 'text-emerald-400' : 'text-slate-400'}`} />
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-xs font-semibold text-slate-200">
                开启 {cronBlueprint.humanReadableTime} 自动生成
              </span>
              {isEnabled && (
                <span className="inline-flex items-center space-x-1 rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-medium text-emerald-300">
                  <Check className="h-2.5 w-2.5" />
                  <span>后台静默托管中</span>
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-400">
              免配置 Crontab 表达式，系统已自动注册韧性定时调度任务
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => {
            onToggleCronHosting(!isEnabled);
          }}
          className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-slate-900 ${
            isEnabled ? 'bg-emerald-600' : 'bg-slate-700'
          }`}
          role="switch"
          aria-checked={isEnabled}
          aria-label="一键开启或关闭后台定时托管"
        >
          <span
            className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
              isEnabled ? 'translate-x-5' : 'translate-x-0'
            }`}
          />
        </button>
      </div>

      {isEnabled && (
        <div className="space-y-2 border-t border-slate-800/80 pt-2.5 text-xs">
          <div className="flex items-center justify-between text-slate-300">
            <span className="text-[11px] text-slate-400">推送接收渠道:</span>
            <div className="flex items-center space-x-1.5">
              <button
                type="button"
                onClick={() => {
                  onUpdateChannel('chat');
                }}
                className={`inline-flex items-center space-x-1 rounded px-2 py-1 text-[11px] transition-colors ${
                  cronBlueprint.targetChannel === 'chat'
                    ? 'bg-blue-600 text-white font-medium'
                    : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                <MessageSquare className="h-3 w-3" />
                <span>主会话</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  onUpdateChannel('desktop_notification');
                }}
                className={`inline-flex items-center space-x-1 rounded px-2 py-1 text-[11px] transition-colors ${
                  cronBlueprint.targetChannel === 'desktop_notification'
                    ? 'bg-blue-600 text-white font-medium'
                    : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                <Bell className="h-3 w-3" />
                <span>系统通知</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  onUpdateChannel('webhook');
                }}
                className={`inline-flex items-center space-x-1 rounded px-2 py-1 text-[11px] transition-colors ${
                  cronBlueprint.targetChannel === 'webhook'
                    ? 'bg-blue-600 text-white font-medium'
                    : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                }`}
              >
                <Webhook className="h-3 w-3" />
                <span>Webhook</span>
              </button>
            </div>
          </div>

          {cronBlueprint.scheduledJobId && (
            <div className="flex items-center justify-between text-[10px] text-slate-400">
              <span className="font-mono">调度标识: {cronBlueprint.scheduledJobId}</span>
              <span className="flex items-center space-x-1 text-emerald-400">
                <Power className="h-2.5 w-2.5" />
                <span>Cron 表达式: {cronBlueprint.cronExpression}</span>
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
