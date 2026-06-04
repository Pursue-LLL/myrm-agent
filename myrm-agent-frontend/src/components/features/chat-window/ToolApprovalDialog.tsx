'use client';

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { ShieldAlert, CheckCircle2, Hand, MessageSquareX } from 'lucide-react';

import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { ScrollArea } from '@/components/primitives/scroll-area';
import { partitionApprovalQueue } from '@/lib/approval/visualApprovalSurface';
import { useToolApprovalResolve } from '@/hooks/useToolApprovalResolve';
import type { ToolApprovalRequest } from '@/store/chat/types';
import SingleApprovalCard from './SingleApprovalCard';

function groupModalRequests(modalQueue: ToolApprovalRequest[]) {
  const batches: Map<string, ToolApprovalRequest[]> = new Map();
  const singles: ToolApprovalRequest[] = [];

  for (const req of modalQueue) {
    if (req.batchId) {
      const group = batches.get(req.batchId) || [];
      group.push(req);
      batches.set(req.batchId, group);
    } else {
      singles.push(req);
    }
  }

  for (const group of batches.values()) {
    group.sort((a, b) => (a.batchIndex ?? 0) - (b.batchIndex ?? 0));
  }

  return {
    batchGroups: Array.from(batches.entries()),
    singleRequests: singles,
  };
}

export default function ToolApprovalDialog() {
  const t = useTranslations('toolApproval');
  const { queue, resolveRequest, approveAll, rejectAll, isLoading } = useToolApprovalResolve();

  const modalQueue = useMemo(() => partitionApprovalQueue(queue).modalRequests, [queue]);

  const { batchGroups, singleRequests } = useMemo(() => groupModalRequests(modalQueue), [modalQueue]);

  if (modalQueue.length === 0) return null;

  const allHandover = modalQueue.every((r) => r.displayMode === 'handover');

  return (
    <Dialog open={modalQueue.length > 0} onOpenChange={() => {}}>
      <DialogContent className="sm:max-w-lg max-h-[80vh]" onPointerDownOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {allHandover ? (
              <Hand className="h-5 w-5 text-primary" />
            ) : (
              <ShieldAlert className="h-5 w-5 text-amber-500" />
            )}
            {allHandover
              ? t('handoverDialogTitle')
              : modalQueue.length > 1
                ? t('batchTitle', { count: modalQueue.length })
                : t('title')}
          </DialogTitle>
          <DialogDescription>{allHandover ? t('handoverDialogDescription') : t('description')}</DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-[50vh]">
          <div className="space-y-3 pr-3">
            {batchGroups.map(([batchId, requests]) => (
              <div key={batchId} className="space-y-3 p-4 rounded-lg border-2 border-primary/20 bg-primary/5">
                <div className="flex items-center gap-2 text-sm font-medium text-primary mb-2">
                  <ShieldAlert className="h-4 w-4" />
                  {t('batchGroup', { count: requests.length })}
                </div>
                {requests.map((req) => (
                  <SingleApprovalCard
                    key={req.requestId}
                    request={req}
                    onResolve={resolveRequest}
                    isLoading={isLoading}
                  />
                ))}
              </div>
            ))}
            {singleRequests.map((req) => (
              <SingleApprovalCard key={req.requestId} request={req} onResolve={resolveRequest} isLoading={isLoading} />
            ))}
          </div>
        </ScrollArea>

        {modalQueue.length > 1 && (
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => void rejectAll(modalQueue)} disabled={isLoading}>
              <MessageSquareX className="mr-1 h-4 w-4" />
              {t('rejectAll')}
            </Button>
            <Button onClick={() => void approveAll(modalQueue)} disabled={isLoading}>
              <CheckCircle2 className="mr-1 h-4 w-4" />
              {t('approveAll')}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
