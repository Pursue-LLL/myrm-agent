import { useMemo, useState } from 'react';
import { BarChart3, ChevronDown, ChevronRight } from 'lucide-react';
import type { TreeNode } from '@/lib/utils/subagentTree';

const STATUS_BAR_COLOR: Record<string, string> = {
  running: 'bg-blue-500',
  verifying: 'bg-amber-500',
  completed: 'bg-green-500',
  failed: 'bg-red-500',
  timed_out: 'bg-yellow-500',
  cancelled: 'bg-gray-400',
  interrupted: 'bg-orange-500',
  checkpoint: 'bg-purple-500',
};

export const MiniGantt = ({ nodes, t }: { nodes: TreeNode[]; t: (key: string) => string }) => {
  const [open, setOpen] = useState(false);

  const spans = useMemo(() => {
    const now = Date.now();
    return nodes
      .flatMap((n) => {
        const start = n.startedAt;
        if (start === undefined || start === null) {return [];}
        const duration = n.duration_seconds;
        const end = duration !== undefined && duration !== null ? start + duration * 1000 : now;
        return [{ id: n.task_id, label: n.description || n.agent_type, status: n.status, start, end }];
      })
      .filter((s) => s.end >= s.start);
  }, [nodes]);

  if (spans.length < 2) {return null;}

  const globalStart = Math.min(...spans.map((s) => s.start));
  const globalEnd = Math.max(...spans.map((s) => s.end));
  const totalSpan = Math.max(1, globalEnd - globalStart);
  const totalSec = totalSpan / 1000;

  return (
    <div className="mb-2" data-testid="subagent-gantt">
      <button
        data-testid="subagent-gantt-toggle"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
      >
        <BarChart3 className="w-3.5 h-3.5" />
        <span>
          {t('ganttTitle')} · {totalSec < 60 ? `${Math.round(totalSec)}s` : `${Math.floor(totalSec / 60)}m${Math.round(totalSec % 60)}s`}
        </span>
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
      </button>
      {open && (
        <div className="mt-1.5 space-y-1">
          {spans.map((s) => {
            const left = ((s.start - globalStart) / totalSpan) * 100;
            const width = Math.max(1, ((s.end - s.start) / totalSpan) * 100);
            return (
              <div key={s.id} className="flex items-center gap-2 text-[10px]">
                <span className="w-20 truncate text-muted-foreground shrink-0" title={s.label}>
                  {s.label}
                </span>
                <div className="flex-1 h-3 bg-muted/30 rounded-sm relative overflow-hidden">
                  <div
                    className={`absolute top-0 h-full rounded-sm ${STATUS_BAR_COLOR[s.status] ?? 'bg-gray-400'}`}
                    style={{ left: `${left}%`, width: `${width}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
