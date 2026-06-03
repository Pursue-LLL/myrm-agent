import React, { useMemo, useState } from 'react';
import { cn } from '@/lib/utils/classnameUtils';

interface SlotData {
  start: string;
  end: string;
  duration_minutes: number;
}

interface PickerData {
  status: string;
  message?: string;
  slots?: SlotData[];
  attendees?: string[];
}

export default function TimeSlotPicker({ data }: { data?: string }) {
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);

  const parsedData = useMemo<PickerData | null>(() => {
    if (!data) return null;
    try {
      // Decode HTML entities if necessary
      const decoded = data.replace(/&#39;/g, "'").replace(/&quot;/g, '"');
      return JSON.parse(decoded) as PickerData;
    } catch (e) {
      console.error('Failed to parse TimeSlotPicker data', e);
      return null;
    }
  }, [data]);

  if (!parsedData) return null;

  if (parsedData.status === 'no_slots_found') {
    return (
      <div className="my-4 p-4 rounded-xl bg-orange-500/10 border border-orange-500/20 text-orange-600 dark:text-orange-400 text-sm">
        <div className="flex items-center gap-2 mb-1 font-medium">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          无合适的共同空闲时间
        </div>
        <div className="opacity-90">{parsedData.message}</div>
      </div>
    );
  }

  const { slots = [], attendees = [] } = parsedData;

  const formatDate = (isoStr: string) => {
    const d = new Date(isoStr);
    const dateStr = d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', weekday: 'short' });
    const timeStr = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
    return { dateStr, timeStr };
  };

  return (
    <div className="my-4 rounded-2xl overflow-hidden border border-border/50 bg-secondary/20 w-full max-w-md">
      <div className="bg-primary/5 px-4 py-3 border-b border-border/30">
        <div className="flex items-center gap-2 text-primary font-medium text-sm">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
            <line x1="16" y1="2" x2="16" y2="6"></line>
            <line x1="8" y1="2" x2="8" y2="6"></line>
            <line x1="3" y1="10" x2="21" y2="10"></line>
          </svg>
          建议会议时段
        </div>
        {attendees.length > 0 && (
          <div className="text-xs text-muted-foreground mt-1 opacity-80">参与人: {attendees.join(', ')}</div>
        )}
      </div>

      <div className="p-3 flex flex-col gap-2">
        {slots.map((slot, idx) => {
          const { dateStr, timeStr: startTime } = formatDate(slot.start);
          const { timeStr: endTime } = formatDate(slot.end);
          const isSelected = selectedIdx === idx;

          return (
            <button
              key={idx}
              onClick={() => setSelectedIdx(idx)}
              className={cn(
                'flex items-center justify-between p-3 rounded-xl border text-left transition-all duration-200 group',
                isSelected
                  ? 'bg-primary text-primary-foreground border-transparent shadow-md transform scale-[1.02]'
                  : 'bg-background border-border/50 hover:border-primary/40 hover:bg-primary/5 hover:',
              )}
            >
              <div className="flex flex-col gap-0.5">
                <span
                  className={cn(
                    'text-xs font-medium uppercase tracking-wider',
                    isSelected ? 'text-primary-foreground/80' : 'text-muted-foreground',
                  )}
                >
                  {dateStr}
                </span>
                <span className="text-base font-bold tracking-tight">
                  {startTime} <span className="opacity-60 text-sm font-normal mx-1">至</span> {endTime}
                </span>
              </div>
              <div
                className={cn(
                  'h-6 w-6 rounded-full border-2 flex items-center justify-center transition-colors',
                  isSelected ? 'border-white bg-white/20' : 'border-muted-foreground/30 group-hover:border-primary/40',
                )}
              >
                {isSelected && (
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="text-white"
                  >
                    <polyline points="20 6 9 17 4 12"></polyline>
                  </svg>
                )}
              </div>
            </button>
          );
        })}
      </div>

      {selectedIdx !== null && (
        <div className="px-4 py-3 bg-secondary/30 text-xs text-muted-foreground flex justify-between items-center animate-in fade-in slide-in-from-bottom-2">
          <span>已选择此时段</span>
          <span className="opacity-80">请告知 Agent 确认排期</span>
        </div>
      )}
    </div>
  );
}
