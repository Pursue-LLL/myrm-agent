/**
 * Fork Dialog Component
 *
 * Dialog for forking conversation from specific message index.
 * P0-3 implementation.
 */

'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { GitFork } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives/dialog';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { forkConversation } from '@/services/fork-api';
import { useToast } from '@/hooks/useToast';

interface ForkDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  chatId: string;
  messageIndex: number;
  messageSnippet?: string;
}

export function ForkDialog({ open, onOpenChange, chatId, messageIndex, messageSnippet }: ForkDialogProps) {
  const router = useRouter();
  const { toast } = useToast();
  const [title, setTitle] = useState(messageSnippet ? `Branch from: ${messageSnippet.slice(0, 30)}...` : '');
  const [isForking, setIsForking] = useState(false);

  const handleFork = async () => {
    setIsForking(true);

    try {
      const response = await forkConversation(chatId, messageIndex, title || undefined);

      if (response.success && response.data.new_chat_id) {
        toast({
          title: 'Conversation forked successfully',
          description: `New branch created from message #${messageIndex}`,
        });

        // Navigate to new fork
        router.push(`/${response.data.new_chat_id}`);
        onOpenChange(false);
      } else {
        throw new Error('Fork failed');
      }
    } catch (error) {
      toast({
        title: 'Fork failed',
        description: error instanceof Error ? error.message : 'Unknown error occurred',
        variant: 'destructive',
      });
    } finally {
      setIsForking(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <GitFork className="h-5 w-5" />
            Fork Conversation
          </DialogTitle>
          <DialogDescription>
            Create a new conversation branch from message #{messageIndex}. The forked conversation will preserve the
            complete state at this point.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="fork-title">New conversation title</Label>
            <Input
              id="fork-title"
              placeholder="Enter title (optional)"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={255}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isForking}>
            Cancel
          </Button>
          <Button onClick={handleFork} disabled={isForking}>
            {isForking ? 'Creating branch...' : 'Create Branch'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
