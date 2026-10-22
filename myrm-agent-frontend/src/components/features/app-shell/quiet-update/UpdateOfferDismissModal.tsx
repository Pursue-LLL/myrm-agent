'use client';

/**
 * 安静时刻「有更新可用」CTA 编排套件 - 稍后提醒与版本跳过弹窗
 *
 * 提供“4 小时后”、“明天此时”或“永久跳过当前版本”的精细化推迟选项。
 */

import React, { useState, useCallback } from 'react';
import { Clock, ShieldAlert, X, Check } from 'lucide-react';
import { useQuietMomentUpdateStore } from './useQuietMomentUpdateStore';

export interface UpdateOfferDismissModalProps {
  className?: string;
}

type SnoozeChoice = '4h' | '24h' | 'skip_version';

export const UpdateOfferDismissModal: React.FC<UpdateOfferDismissModalProps> = ({
  className = '',
}) => {
  const isDismissModalOpen = useQuietMomentUpdateStore((state) => state.isDismissModalOpen);
  const snapshot = useQuietMomentUpdateStore((state) => state.snapshot);
  const closeDismissModal = useQuietMomentUpdateStore((state) => state.closeDismissModal);
  const dismissVersion = useQuietMomentUpdateStore((state) => state.dismissVersion);

  const [selectedChoice, setSelectedChoice] = useState<SnoozeChoice>('4h');

  const handleConfirm = useCallback(() => {
    if (!snapshot?.version) {
      closeDismissModal();
      return;
    }

    if (selectedChoice === '4h') {
      dismissVersion(snapshot.version, 4);
    } else if (selectedChoice === '24h') {
      dismissVersion(snapshot.version, 24);
    } else {
      // 永久跳过该版本
      dismissVersion(snapshot.version);
    }
  }, [snapshot?.version, selectedChoice, dismissVersion, closeDismissModal]);

  if (!isDismissModalOpen || !snapshot) {
    return null;
  }

  return (
    <dialog
      open
      aria-labelledby="dismiss-modal-title"
      className="fixed inset-0 z-[10000] flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm animate-in fade-in duration-200 border-none m-0 w-full h-full max-w-none max-h-none"
      data-testid="update-offer-dismiss-modal"
    >
      <div
        className={`w-full max-w-md bg-background border border-border shadow-2xl rounded-2xl overflow-hidden p-5 ${className}`}
      >
        <div className="flex items-center justify-between pb-3 border-b border-border/60">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-muted text-muted-foreground flex items-center justify-center">
              <Clock className="w-4 h-4" />
            </div>
            <h3 id="dismiss-modal-title" className="text-sm font-semibold text-foreground">
              调整更新提醒时机
            </h3>
          </div>
          <button
            type="button"
            onClick={closeDismissModal}
            className="text-muted-foreground hover:text-foreground p-1 rounded-md hover:bg-muted transition-colors"
            aria-label="取消关闭"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <p className="mt-3 text-xs text-muted-foreground leading-relaxed">
          已为您保留版本 <span className="font-mono text-foreground font-medium">v{snapshot.version}</span> 的就绪状态。请选择后续的静默触达偏好：
        </p>

        <div className="mt-4 space-y-2">
          <label
            aria-label="4 小时后再提醒"
            className={`flex items-center justify-between p-3 rounded-xl border text-xs cursor-pointer transition-colors ${
              selectedChoice === '4h'
                ? 'border-primary bg-primary/5 text-foreground'
                : 'border-border/70 hover:bg-muted/40 text-muted-foreground'
            }`}
          >
            <div className="flex items-center gap-2.5">
              <Clock className="w-4 h-4 text-primary" />
              <div>
                <p className="font-medium text-foreground">稍后 4 小时再提醒</p>
                <p className="text-[11px] text-muted-foreground">在当前工作区间专注推进，稍后再行更新</p>
              </div>
            </div>
            <input
              type="radio"
              name="snooze-option"
              value="4h"
              checked={selectedChoice === '4h'}
              onChange={() => {
                setSelectedChoice('4h');
              }}
              className="sr-only"
            />
            {selectedChoice === '4h' && <Check className="w-4 h-4 text-primary" />}
          </label>

          <label
            aria-label="明天此时再提醒"
            className={`flex items-center justify-between p-3 rounded-xl border text-xs cursor-pointer transition-colors ${
              selectedChoice === '24h'
                ? 'border-primary bg-primary/5 text-foreground'
                : 'border-border/70 hover:bg-muted/40 text-muted-foreground'
            }`}
          >
            <div className="flex items-center gap-2.5">
              <Clock className="w-4 h-4 text-primary" />
              <div>
                <p className="font-medium text-foreground">明天此时再提醒</p>
                <p className="text-[11px] text-muted-foreground">推迟 24 小时，届时在安静时刻唤起</p>
              </div>
            </div>
            <input
              type="radio"
              name="snooze-option"
              value="24h"
              checked={selectedChoice === '24h'}
              onChange={() => {
                setSelectedChoice('24h');
              }}
              className="sr-only"
            />
            {selectedChoice === '24h' && <Check className="w-4 h-4 text-primary" />}
          </label>

          <label
            aria-label="跳过此版本"
            className={`flex items-center justify-between p-3 rounded-xl border text-xs cursor-pointer transition-colors ${
              selectedChoice === 'skip_version'
                ? 'border-destructive/60 bg-destructive/5 text-foreground'
                : 'border-border/70 hover:bg-muted/40 text-muted-foreground'
            }`}
          >
            <div className="flex items-center gap-2.5">
              <ShieldAlert className="w-4 h-4 text-amber-500" />
              <div>
                <p className="font-medium text-foreground">跳过此版本 (v{snapshot.version})</p>
                <p className="text-[11px] text-muted-foreground">不再提示该版本，直到下一个更新发布</p>
              </div>
            </div>
            <input
              type="radio"
              name="snooze-option"
              value="skip_version"
              checked={selectedChoice === 'skip_version'}
              onChange={() => {
                setSelectedChoice('skip_version');
              }}
              className="sr-only"
            />
            {selectedChoice === 'skip_version' && <Check className="w-4 h-4 text-destructive" />}
          </label>
        </div>

        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={closeDismissModal}
            className="px-3 py-1.5 rounded-lg border border-border text-xs text-muted-foreground hover:bg-muted transition-colors"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            className="px-4 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 transition-colors"
            data-testid="confirm-snooze-btn"
          >
            确认设定
          </button>
        </div>
      </div>
    </dialog>
  );
};
