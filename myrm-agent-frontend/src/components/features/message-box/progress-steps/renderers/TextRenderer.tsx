import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';

interface TextRendererProps {
  text: string;
}

const TextRenderer: React.FC<TextRendererProps> = ({ text }) => {
  return (
    <div className="relative">
      <div
        className={cn(
          'p-4 rounded-xl bg-gradient-to-br',
          'from-primary/5 via-background to-primary/10',
          'dark:from-primary/10 dark:via-background dark:to-primary/5',
          'border border-primary/20 dark:border-primary/30',
          'backdrop-blur-sm',
          'transition-all duration-300',
        )}
      >
        <div className="absolute inset-0 bg-gradient-to-r from-primary/5 to-transparent rounded-xl" />
        <p
          className={cn(
            'relative text-sm leading-relaxed',
            'text-foreground/90 dark:text-foreground/80',
            'whitespace-pre-wrap break-words',
          )}
        >
          {text}
        </p>
      </div>
    </div>
  );
};

export default TextRenderer;
