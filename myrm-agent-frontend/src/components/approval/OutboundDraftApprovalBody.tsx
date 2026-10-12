'use client';

import { useTranslations } from 'next-intl';
import { MessageSquare, Paperclip } from 'lucide-react';
import type { ApprovalPayloadData, OutboundDraftAttachment } from '@/store/useApprovalStore';

/** The name the recipient will see for an attachment. */
function attachmentName(attachment: OutboundDraftAttachment): string {
  return attachment.filename || attachment.path?.split(/[\\/]/).pop() || attachment.url || attachment.media_type;
}

/** Review body of a held channel reply: the customer's message, the drafted reply with its attachments, and routing. */
export function OutboundDraftApprovalBody({ payload }: { payload?: ApprovalPayloadData }) {
  const t = useTranslations('toolApproval');
  const draftContent = payload?.draft_content || '';
  const originalContent = payload?.original_content || '';
  const channelName = payload?.channel || '';
  const recipientId = payload?.recipient_id || '';
  const topicId = payload?.topic_id || '';
  const attachments = payload?.outbound?.media ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3">
        <MessageSquare className="h-5 w-5 flex-shrink-0 text-amber-600 dark:text-amber-400" />
        <div>
          <h4 className="font-semibold text-sm text-amber-700 dark:text-amber-300">{t('outboundDraftTitle')}</h4>
          <p className="text-xs text-amber-600/80 dark:text-amber-400/80 mt-0.5">{t('outboundDraftDescription')}</p>
        </div>
      </div>

      {originalContent && (
        <div className="rounded-lg border bg-muted/30 p-3">
          <div className="text-xs font-medium text-muted-foreground mb-1.5">{t('outboundDraftOriginal')}</div>
          <p className="text-sm text-foreground whitespace-pre-wrap">{originalContent}</p>
        </div>
      )}

      <div className="rounded-lg border bg-background p-3">
        <div className="text-xs font-medium text-muted-foreground mb-1.5">{t('outboundDraftReply')}</div>
        <p className="text-sm text-foreground whitespace-pre-wrap">{draftContent}</p>
        {attachments.length > 0 && (
          <ul className="mt-3 flex flex-wrap gap-2">
            {attachments.map((attachment, index) => {
              const name = attachmentName(attachment);
              return (
                <li
                  key={`${name}-${index}`}
                  className="inline-flex max-w-full items-center gap-1.5 rounded-full border bg-muted/50 px-2.5 py-1 text-xs text-muted-foreground"
                >
                  <Paperclip className="h-3 w-3 flex-shrink-0" aria-hidden="true" />
                  <span className="truncate" title={name}>
                    {name}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="flex items-center gap-3 text-xs text-muted-foreground px-1 flex-wrap">
        {channelName && (
          <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5">{channelName}</span>
        )}
        {recipientId && (
          <span className="truncate" title={recipientId}>
            {recipientId}
          </span>
        )}
        {topicId && (
          <span className="truncate opacity-60" title={topicId}>
            {topicId}
          </span>
        )}
      </div>
    </div>
  );
}
