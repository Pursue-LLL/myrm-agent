'use client';

/**
 * [INPUT]
 * - digitalSelfTypes::DigitalSelfDraftItem, ToneStyle, TONE_STYLE_CONFIGS, RELATIONSHIP_CONFIGS, CHANNEL_CONFIGS (POS: Contracts)
 * - DigitalSelfToneSelector (POS: Tone pill selector)
 * - lucide-react::Lock, Send, Trash2, ChevronDown, ChevronRight, ShieldCheck, ExternalLink, MessageCircle (POS: Icons)
 *
 * [OUTPUT]
 * - ToneDraftApprovalCard: Human review card with tone adjustment & outbound hard-gate.
 *
 * [POS]
 * Reviewable draft inbox card enforcing absolute human confirmation before
 * messages are dispatched to external corporate IMs (Feishu, DingTalk, Email).
 */

import React, { useState } from 'react';
import {
  Lock,
  Send,
  Trash2,
  ChevronDown,
  ChevronRight,
  ShieldCheck,
  ExternalLink,
  MessageCircle,
  Loader2,
} from 'lucide-react';
import {
  type DigitalSelfDraftItem,
  type ToneStyle,
  CHANNEL_CONFIGS,
  RELATIONSHIP_CONFIGS,
} from './digitalSelfTypes';
import DigitalSelfToneSelector from './DigitalSelfToneSelector';

export interface ToneDraftApprovalCardProps {
  draft: DigitalSelfDraftItem;
  onConfirmSend: (draftId: string) => Promise<void> | void;
  onDiscard: (draftId: string) => void;
  onUpdateContent: (draftId: string, content: string) => void;
  onChangeTone: (draftId: string, tone: ToneStyle) => void;
  isSending?: boolean;
  className?: string;
}

export default function ToneDraftApprovalCard({
  draft,
  onConfirmSend,
  onDiscard,
  onUpdateContent,
  onChangeTone,
  isSending = false,
  className = '',
}: ToneDraftApprovalCardProps) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);

  const channelConfig = CHANNEL_CONFIGS[draft.channel] ?? { channel: draft.channel, displayName: draft.channel };
  const relationConfig = RELATIONSHIP_CONFIGS[draft.relationship] ?? {
    relationship: draft.relationship,
    displayName: draft.relationship,
    colorClass: 'text-muted-foreground bg-muted',
  };

  const isConfirmedSent = draft.status === 'confirmed_sent';
  const isDiscarded = draft.status === 'discarded';

  const handleSendClick = async () => {
    if (isSending || isConfirmedSent || isDiscarded) {
      return;
    }
    await onConfirmSend(draft.id);
  };

  return (
    <div
      data-testid="tone-draft-approval-card"
      className={`rounded-xl border border-border/80 bg-card/95 p-4 shadow-sm backdrop-blur-xs transition-all ${className}`}
    >
      {/* Outbound Hard-Gate Banner */}
      <div
        data-testid="outbound-hard-gate-banner"
        className="flex items-center justify-between px-3 py-2 rounded-lg border border-indigo-500/30 bg-indigo-500/10 mb-3 text-xs"
      >
        <div className="flex items-center gap-2 text-indigo-700 dark:text-indigo-300 font-medium">
          <Lock className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
          <span>出站发送物理安全门禁：未经人工显式确认，绝对禁止直接发送</span>
        </div>
        <ShieldCheck className="w-4 h-4 text-indigo-600 dark:text-indigo-400 shrink-0" aria-hidden="true" />
      </div>

      {/* Recipient & Channel Info Header */}
      <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-muted text-xs font-semibold text-foreground">
            <MessageCircle className="w-3.5 h-3.5 text-primary" aria-hidden="true" />
            <span>{channelConfig.displayName}</span>
          </div>
          <span className="text-sm font-semibold text-foreground">{draft.recipientName}</span>
          <span
            className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${relationConfig.colorClass}`}
          >
            {relationConfig.displayName}
          </span>
        </div>

        {/* Tone Selector */}
        {!isConfirmedSent && !isDiscarded && (
          <DigitalSelfToneSelector
            currentTone={draft.toneStyle}
            onSelectTone={(tone) => {
              onChangeTone(draft.id, tone);
            }}
            disabled={isSending}
          />
        )}
      </div>

      {/* Original Incoming Message Quote */}
      <div className="rounded-lg border border-border/40 bg-muted/40 p-2.5 mb-3 text-xs text-muted-foreground">
        <div className="font-medium text-foreground mb-1">原消息摘要：</div>
        <div className="line-clamp-3 italic leading-relaxed">“{draft.originalMessage}”</div>
      </div>

      {/* Reference Context Sources (Collapsible) */}
      {draft.contextSources.length > 0 && (
        <div className="mb-3">
          <button
            type="button"
            onClick={() => {
              setSourcesOpen((prev) => !prev);
            }}
            data-testid="toggle-sources-btn"
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground font-medium transition-colors"
          >
            {sourcesOpen ? (
              <ChevronDown className="w-3.5 h-3.5" aria-hidden="true" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5" aria-hidden="true" />
            )}
            <span>事实参考依据（{draft.contextSources.length} 条）</span>
          </button>

          {sourcesOpen && (
            <div
              data-testid="context-sources-list"
              className="mt-2 space-y-1.5 pl-4 border-l-2 border-border/60"
            >
              {draft.contextSources.map((source) => {
                return (
                  <div key={source.id} className="text-xs text-muted-foreground">
                    <div className="flex items-center gap-1 font-medium text-foreground">
                      <span>{source.title}</span>
                      {source.url && (
                        <a
                          href={source.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-primary hover:underline"
                        >
                          <ExternalLink className="w-3 h-3 inline" />
                        </a>
                      )}
                    </div>
                    <p className="line-clamp-2 text-[11px] opacity-80 mt-0.5">{source.excerpt}</p>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Draft Content Inline Editor */}
      <div className="mb-3">
        <div className="flex items-center justify-between mb-1.5">
          <label htmlFor={`draft-input-${draft.id}`} className="text-xs font-semibold text-foreground">
            数字分身拟答草案：
          </label>
          <span className="text-[11px] text-muted-foreground">
            {isConfirmedSent ? '已确认出站' : isDiscarded ? '已放弃' : '可直接点击修改文字'}
          </span>
        </div>

        <textarea
          id={`draft-input-${draft.id}`}
          data-testid="draft-content-textarea"
          value={draft.draftContent}
          disabled={isSending || isConfirmedSent || isDiscarded}
          onChange={(event) => {
            onUpdateContent(draft.id, event.target.value);
            setIsEditing(true);
          }}
          rows={4}
          className="w-full text-xs p-2.5 rounded-lg border border-border/80 bg-background text-foreground focus:outline-hidden focus:ring-1 focus:ring-primary disabled:opacity-60 resize-y leading-relaxed font-sans"
          placeholder="草拟回复内容..."
        />
      </div>

      {/* Action Footer */}
      <div className="flex items-center justify-between pt-2 border-t border-border/40">
        <div>
          {isConfirmedSent ? (
            <span
              data-testid="sent-status-badge"
              className="text-xs font-medium text-emerald-600 dark:text-emerald-400 inline-flex items-center gap-1"
            >
              <ShieldCheck className="w-3.5 h-3.5" aria-hidden="true" />
              已于 {new Date(draft.confirmedAt ?? Date.now()).toLocaleTimeString()} 显式授权发送
            </span>
          ) : isDiscarded ? (
            <span className="text-xs font-medium text-muted-foreground">该草稿已作废</span>
          ) : isEditing ? (
            <span className="text-[11px] text-amber-600 dark:text-amber-400">已做人工修改</span>
          ) : (
            <span className="text-[11px] text-muted-foreground">等待人工确认</span>
          )}
        </div>

        {!isConfirmedSent && !isDiscarded && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={isSending}
              data-testid="discard-draft-btn"
              onClick={() => {
                onDiscard(draft.id);
              }}
              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-md border border-border hover:bg-muted text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
            >
              <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
              <span>放弃</span>
            </button>

            <button
              type="button"
              disabled={isSending || !draft.draftContent.trim()}
              data-testid="confirm-send-btn"
              onClick={handleSendClick}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-md bg-primary text-primary-foreground hover:bg-primary/90 shadow-xs transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSending ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />
                  <span>正在出站发送...</span>
                </>
              ) : (
                <>
                  <Send className="w-3.5 h-3.5" aria-hidden="true" />
                  <span>确认出站发送</span>
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
