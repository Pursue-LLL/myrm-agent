import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils/classnameUtils';

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default:
          'border-0 border-none bg-[var(--button-fill)] text-[var(--button-fill-foreground)] shadow-[var(--shadow-brand)] animate-button-float motion-reduce:animate-none hover:animate-none hover:bg-[var(--button-fill-hover)] hover:-translate-y-2 hover:shadow-[var(--shadow-brand-lg)] active:animate-none active:translate-y-0 active:shadow-[var(--shadow-brand-sm)] transition-[transform,box-shadow,background-color] duration-1000 ease-[cubic-bezier(0.22,1,0.36,1)]',
        destructive: 'bg-destructive text-destructive-foreground shadow-none hover:bg-destructive/90',
        outline: 'border border-input bg-background shadow-none hover:bg-accent hover:text-accent-foreground',
        secondary: 'bg-secondary text-secondary-foreground shadow-none hover:bg-secondary/80',
        ghost: 'hover:bg-accent hover:text-accent-foreground',
        link: 'text-primary underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-9 px-4 py-2',
        sm: 'h-8 rounded-full px-3 text-xs',
        lg: 'h-10 rounded-full px-8',
        icon: 'h-9 w-9',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  },
);
Button.displayName = 'Button';

export { Button, buttonVariants };
