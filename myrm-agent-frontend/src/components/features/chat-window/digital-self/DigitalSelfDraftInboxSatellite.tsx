'use client';

/**
 * [INPUT]
 * - useDigitalSelfDraftStore::useDigitalSelfDraftStore (POS: Draft queue store)
 * - ToneDraftApprovalCard::ToneDraftApprovalCard (POS: Approval card)
 * - lucide-react::Mail, ChevronDown, ChevronUp, ShieldCheck (POS: Icons)
 *
 * [OUTPUT]
 * - DigitalSelfDraftInboxSatellite: Floating dock for pending digital self tone drafts.
 *
 * [POS]
 * Satellite widget mounted globally in chat window, alerting users when
 * autonomous drafts are staged and enforcing human review before outbound delivery.
 */

import React, { useState } from 'react';
import { Mail, ChevronDown, ChevronUp, ShieldCheck } from 'lucide-react';
import { useDigitalSelfDraftStore } from './useDigitalSelfDraftStore';
import ToneDraftApprovalCard from './ToneDraftApprovalCard';

export interface DigitalSelfDraftInboxSatelliteProps {
  className?: string;
}

export default function DigitalSelfDraftInboxSatellite({
  className = '',
}: DigitalSelfDraftInboxSatelliteProps) {
  const drafts = useDigitalSelfDraftStore((state) => state.drafts);
  const confirmAndSendOutbound = useDigitalSelfDraftStore((state) => state.confirmAndSendOutbound);
  const discardDraft = useDigitalSelfDraftStore((state) => state.discardDraft);
  const updateDraftContent = useDigitalSelfDraftStore((state) => state.updateDraftContent);
  const changeToneStyle = useDigitalSelfDraftStore((state) => state.changeToneStyle);

  const [expanded, setExpanded] = useState(false);
  const [sendingDraftId, setSendingDraftId] = useState<string | null>(null);

  const pendingDrafts = drafts.filter(
    (d) => d.status === 'pending_review' || d.status === 'edited',
  );

  if (pendingDrafts.length === 0) {
    return null;
  }

  const activeDraft = pendingDrafts[0];

  const handleSend = async (draftId: string) => {
    setSendingDraftId(draftId);
    try {
      await confirmAndSendOutbound(draftId);
    } finally {
      setSendingDraftId(null);
    }
  };

  return (
    <div
      data-testid="digital-self-draft-inbox-satellite"
      className={`fixed top-24 right-6 z-40 max-w-md w-full select-none animate-in fade-in slide-in-from-top-3 ${className}`}
    >
      {/* Floating pill header badge */}
      <button
        type="button"
        data-testid="draft-satellite-header"
        onClick={() => {
          setExpanded((prev) => !prev);
        }}
        className="w-full text-left flex items-center justify-between p-2.5 rounded-xl border border-indigo-500/40 bg-card/95 shadow-md backdrop-blur-md cursor-pointer hover:border-indigo-500/70 transition-all text-xs"
      >
        <div className="flex items-center gap-2">
          <div className="relative flex items-center justify-center w-6 h-6 rounded-full bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
            <Mail className="w-3.5 h-3.5" aria-hidden="true" />
            <span className="absolute -top-0.5 -right-0.5 flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500" />
            </span>
          </div>
          <div>
            <span className="font-semibold text-foreground">数字分身待审草稿</span>
            <span className="text-[11px] text-muted-foreground ml-1.5">
              （{pendingDrafts.length} 封待确认）
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1.5 text-muted-foreground">
          <ShieldCheck className="w-3.5 h-3.5 text-indigo-500" aria-hidden="true" />
          <span className="text-[11px] font-medium text-indigo-600 dark:text-indigo-400">门禁就绪</span>
          {expanded ? (
            <ChevronUp className="w-3.5 h-3.5" aria-hidden="true" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5" aria-hidden="true" />
          )}
        </div>
      </button>

      {/* Expanded approval card preview */}
      {expanded && activeDraft && (
        <div data-testid="draft-satellite-card-container" className="mt-2 animate-in fade-in-50 zoom-in-95">
          <ToneDraftApprovalCard
            draft={activeDraft}
            onConfirmSend={handleSend}
            onDiscard={discardDraft}
            onUpdateContent={updateDraftContent}
            onChangeTone={changeToneStyle}
            isSending={sendingDraftId === activeDraft.id}
          />
        </div>
      )}
    </div>
  );
}
