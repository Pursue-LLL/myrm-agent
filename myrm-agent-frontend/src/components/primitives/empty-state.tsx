/**
 * [INPUT] classnameUtils::cn (POS: Tailwind 类名合并工具)
 * [OUTPUT] EmptyState: 通用空状态/过渡态展示基元组件, emptyStateVariants: 样式变体配置
 * [POS] UI基元层。提供符合 Maka UI 视觉体系的标准化空状态布局、图标光晕及操作按钮槽位。
 */

import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils/classnameUtils';

const emptyStateVariants = cva(
  'flex flex-col items-center justify-center text-center transition-all duration-200 animate-in fade-in-50',
  {
    variants: {
      variant: {
        default: 'py-12 px-4',
        dashed: 'rounded-xl border border-dashed border-border/60 bg-muted/10 py-10 px-4',
        compact: 'py-6 px-3',
        card: 'rounded-xl border border-border/50 bg-card/60 p-6 shadow-sm',
        error: 'rounded-xl border border-destructive/20 bg-destructive/5 py-10 px-4',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

export interface EmptyStateProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof emptyStateVariants> {
  icon?: React.ComponentType<{ className?: string }>;
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  secondaryAction?: React.ReactNode;
}

const EmptyState = React.forwardRef<HTMLDivElement, EmptyStateProps>(
  (
    {
      className,
      variant,
      icon: Icon,
      title,
      description,
      action,
      secondaryAction,
      ...props
    },
    ref,
  ) => {
    return (
      <div
        ref={ref}
        role="status"
        aria-live="polite"
        className={cn(emptyStateVariants({ variant, className }))}
        {...props}
      >
        {Icon && (
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-muted/80 text-muted-foreground shadow-sm transition-transform duration-200 hover:scale-105">
            <Icon className="h-7 w-7 text-primary/80" />
          </div>
        )}
        <h3 className="text-base font-semibold tracking-tight text-foreground">
          {title}
        </h3>
        {description && (
          <p className="mt-1.5 max-w-sm text-sm text-muted-foreground leading-relaxed">
            {description}
          </p>
        )}
        {(action || secondaryAction) && (
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            {action}
            {secondaryAction}
          </div>
        )}
      </div>
    );
  },
);

EmptyState.displayName = 'EmptyState';

export { EmptyState, emptyStateVariants };
