'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { AlertCircle, KanbanSquare } from 'lucide-react';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { listBoards, type KanbanBoard } from '@/services/kanban';
import {
  readKanbanLastBoardId,
  resolveKanbanChatBoardId,
  shouldShowKanbanBoardPicker,
  writeKanbanLastBoardId,
} from '@/lib/kanban/kanbanChatBoard';

interface KanbanConfigSectionProps {
  tPanel: (key: string) => string;
}

export function KanbanConfigSection({ tPanel }: KanbanConfigSectionProps) {
  const [boards, setBoards] = useState<KanbanBoard[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedBoardId, setSelectedBoardId] = useState<string | null>(() => readKanbanLastBoardId());

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const result = await listBoards();
        if (cancelled) return;
        const items = result.items;
        setBoards(items);
        const resolved = resolveKanbanChatBoardId(items);
        if (resolved) {
          writeKanbanLastBoardId(resolved);
          setSelectedBoardId(resolved);
        } else {
          setSelectedBoardId(readKanbanLastBoardId());
        }
      } catch {
        if (!cancelled) {
          setBoards([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="p-3 rounded-xl bg-muted/30 border border-border/50">
        <p className="text-xs text-muted-foreground">{tPanel('kanbanBoardLoading')}</p>
      </div>
    );
  }

  if (boards.length === 0) {
    return (
      <div className="space-y-3 p-3 rounded-xl bg-muted/30 border border-border/50">
        <p className="text-xs text-amber-600 dark:text-amber-400 flex items-start gap-1.5">
          <AlertCircle size={12} className="mt-0.5 shrink-0" />
          {tPanel('kanbanNoBoardsHint')}
        </p>
        <Link
          href="/settings/kanban"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:text-primary/80 transition-colors"
        >
          <KanbanSquare size={12} />
          {tPanel('kanbanOpenSettings')}
        </Link>
      </div>
    );
  }

  const showPicker = shouldShowKanbanBoardPicker(boards);
  const activeBoard =
    boards.find((b) => b.board_id === (selectedBoardId ?? resolveKanbanChatBoardId(boards))) ?? boards[0]!;

  return (
    <div className="space-y-3 p-3 rounded-xl bg-muted/30 border border-border/50">
      <p className="text-xs text-muted-foreground leading-relaxed">{tPanel('kanbanBoardHint')}</p>
      {showPicker ? (
        <div className="space-y-2">
          <Label className="text-sm font-medium flex items-center gap-2">
            <KanbanSquare size={14} className="text-violet-500" />
            {tPanel('kanbanTargetBoard')}
          </Label>
          <Select
            value={selectedBoardId ?? undefined}
            onValueChange={(value) => {
              setSelectedBoardId(value);
              writeKanbanLastBoardId(value);
            }}
          >
            <SelectTrigger className="w-full bg-background">
              <SelectValue placeholder={tPanel('kanbanSelectBoardPlaceholder')} />
            </SelectTrigger>
            <SelectContent>
              {boards.map((board) => (
                <SelectItem key={board.board_id} value={board.board_id}>
                  {board.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          {tPanel('kanbanActiveBoard')}: <span className="font-medium text-foreground">{activeBoard.name}</span>
        </p>
      )}
    </div>
  );
}
