'use client';

import { Settings } from 'lucide-react';
import { Label } from '@/components/primitives/label';
import { cn } from '@/lib/utils/classnameUtils';

export interface SelectableCardProps {
  id: string;
  label: string;
  description?: string;
  checked: boolean;
  onCheckedChange: () => void;
  icon?: React.ReactNode;
  colorClass?: string;
  rightElement?: React.ReactNode;
  disabled?: boolean;
}

export function SelectableCard({
  id,
  label,
  description,
  checked,
  onCheckedChange,
  icon,
  colorClass = 'text-primary',
  rightElement,
  disabled = false,
}: SelectableCardProps) {
  return (
    <div
      data-testid={id}
      className={cn(
        'group relative flex items-start gap-3 p-3 rounded-xl',
        'border transition-all duration-200',
        disabled
          ? 'cursor-not-allowed opacity-60 bg-muted/20 border-border/40'
          : cn(
              'cursor-pointer',
              checked ? 'bg-primary/5 border-primary/30' : 'bg-card/50 border-border/40 hover:border-border hover:bg-muted/30',
            ),
      )}
      onClick={(e) => {
        if (disabled) return;
        if ((e.target as HTMLElement).closest('.no-card-click')) return;
        onCheckedChange();
      }}
    >
      {icon && (
        <div
          className={cn(
            'shrink-0 w-7 h-7 rounded-lg flex items-center justify-center',
            'bg-muted/60 transition-colors',
            checked && 'bg-primary/10',
            colorClass,
          )}
        >
          {icon}
        </div>
      )}
      <div className="flex-1 min-w-0 pt-0.5">
        <div className="flex items-center gap-2">
          <Label htmlFor={id} className="text-sm font-medium cursor-pointer leading-tight text-foreground">
            {label}
          </Label>
        </div>
        {description && <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{description}</p>}
      </div>
      {rightElement && <div className="shrink-0 flex items-center">{rightElement}</div>}
      {!rightElement && (
        <div
          className={cn(
            'shrink-0 w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all',
            checked ? 'bg-primary border-primary' : 'border-border/60 group-hover:border-muted-foreground/40',
          )}
        >
          {checked && (
            <svg width="10" height="8" viewBox="0 0 10 8" fill="none" className="text-primary-foreground">
              <path
                d="M1 4L3.5 6.5L9 1"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          )}
        </div>
      )}
    </div>
  );
}

export interface AddMoreButtonProps {
  label: string;
  onClick: () => void;
}

export function AddMoreButton({ label, onClick }: AddMoreButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex items-center justify-center gap-2 w-full py-2.5 rounded-xl',
        'border border-dashed border-border/60',
        'text-sm text-muted-foreground',
        'hover:border-primary/40 hover:text-primary hover:bg-primary/5',
        'transition-all duration-200',
      )}
    >
      <Settings size={14} />
      {label}
    </button>
  );
}
