'use client';

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import {
  MousePointerClick,
  Type,
  ChevronDown,
  CheckSquare,
  Navigation,
  Upload,
  Trash2,
  Lock,
} from 'lucide-react';
import type { RecordedStep } from '@/store/useBrowserRecordingStore';

const ACTION_ICONS: Record<string, React.ElementType> = {
  click: MousePointerClick,
  dblclick: MousePointerClick,
  type: Type,
  fill: Type,
  select: ChevronDown,
  check: CheckSquare,
  uncheck: CheckSquare,
  navigate: Navigation,
  upload: Upload,
  press: Type,
};

const ACTION_LABELS: Record<string, string> = {
  click: 'Click',
  dblclick: 'Double Click',
  type: 'Type',
  fill: 'Fill',
  select: 'Select',
  check: 'Check',
  uncheck: 'Uncheck',
  navigate: 'Navigate',
  upload: 'Upload',
  press: 'Press Key',
  scroll: 'Scroll',
  hover: 'Hover',
  drag: 'Drag',
};

interface RecordingStepCardProps {
  step: RecordedStep;
  onDelete?: (seq: number) => void;
  readonly?: boolean;
}

const RecordingStepCard: React.FC<RecordingStepCardProps> = ({ step, onDelete, readonly }) => {
  const Icon = ACTION_ICONS[step.action] || MousePointerClick;
  const label = ACTION_LABELS[step.action] || step.action;

  return (
    <div
      className={cn(
        'group flex items-start gap-2 p-2 rounded-lg border border-border',
        'bg-card hover:bg-accent/50 transition-colors',
      )}
    >
      <div className="flex-shrink-0 mt-0.5">
        <div
          className={cn(
            'w-7 h-7 rounded-md flex items-center justify-center',
            'bg-primary/10 text-primary',
          )}
        >
          <Icon size={14} />
        </div>
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">{step.seq}.</span>
          <span className="text-sm font-medium">{label}</span>
          {step.isPassword && <Lock size={12} className="text-destructive" />}
        </div>

        {step.elementText && (
          <p className="text-xs text-muted-foreground truncate mt-0.5">
            {step.elementText}
          </p>
        )}

        {step.value && !step.isPassword && (
          <p className="text-xs text-muted-foreground/70 truncate mt-0.5 font-mono">
            {step.value}
          </p>
        )}
        {step.value && step.isPassword && (
          <p className="text-xs text-destructive/70 mt-0.5 font-mono">***</p>
        )}

        {step.screenshotB64 && (
          <div className="mt-1.5 rounded overflow-hidden border border-border max-h-24">
            <img
              src={`data:image/png;base64,${step.screenshotB64}`}
              alt={`Step ${step.seq}`}
              className="w-full h-auto object-cover"
              loading="lazy"
            />
          </div>
        )}
      </div>

      {!readonly && onDelete && (
        <button
          type="button"
          onClick={() => onDelete(step.seq)}
          className={cn(
            'flex-shrink-0 p-1 rounded opacity-0 group-hover:opacity-100',
            'text-muted-foreground hover:text-destructive transition-all',
          )}
          aria-label="Delete step"
        >
          <Trash2 size={14} />
        </button>
      )}
    </div>
  );
};

export default React.memo(RecordingStepCard);
