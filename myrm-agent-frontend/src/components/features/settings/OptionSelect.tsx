'use client';

import { cn } from '@/lib/utils/classnameUtils';
import { useState, useRef, useEffect } from 'react';
import { IconCheck, IconChevronDown } from '@/components/features/icons/PremiumIcons';

export interface OptionItem {
  value: string;
  label: string;
  description?: string;
  disabled?: boolean;
}

interface OptionSelectProps<T extends string = string> {
  value: T;
  options: OptionItem[];
  onChange: (value: T) => void;
  placeholder?: string;
  error?: string;
  className?: string;
  hideDescription?: boolean;
  disabled?: boolean;
}

const OptionSelect = <T extends string = string>({
  value,
  options,
  onChange,
  placeholder = 'Select an option',
  error,
  className,
  hideDescription = false,
  disabled = false,
}: OptionSelectProps<T>) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedOption = options.find((opt) => opt.value === value);

  // 点击外部关闭
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const handleSelect = (optionValue: string) => {
    onChange(optionValue as T);
    setIsOpen(false);
  };

  return (
    <div ref={containerRef} className={cn('relative', className)}>
      {/* 触发按钮 */}
      <button
        type="button"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className={cn(
          'w-full flex items-center justify-between gap-2 px-3 py-2.5 rounded-lg border transition-colors text-left',
          'bg-secondary/50 hover:bg-secondary',
          error ? 'border-red-500' : 'border-border hover:border-primary/50',
          isOpen && 'border-primary/50 ring-1 ring-primary/20',
          disabled && 'opacity-50 cursor-not-allowed',
        )}
      >
        <span className={cn('text-sm', selectedOption ? 'text-foreground' : 'text-muted-foreground')}>
          {selectedOption?.label || placeholder}
        </span>
        <IconChevronDown
          className={cn('w-4 h-4 text-muted-foreground transition-transform duration-200', isOpen && 'rotate-180')}
        />
      </button>

      {/* 下拉选项 */}
      {isOpen && (
        <div className="absolute z-50 w-full mt-1 py-1 bg-popover border border-border rounded-lg shadow-lg max-h-64 overflow-y-auto animate-in fade-in-0 zoom-in-95 slide-in-from-top-2 duration-150">
          {options.map((option) => {
            const isSelected = option.value === value;
            return (
              <button
                key={option.value}
                type="button"
                onClick={() => !option.disabled && handleSelect(option.value)}
                disabled={option.disabled}
                className={cn(
                  'w-full flex items-center justify-between gap-2 px-3 py-2.5 text-left transition-colors',
                  option.disabled ? 'opacity-50 cursor-not-allowed' : 'hover:bg-accent cursor-pointer',
                  isSelected && 'bg-primary/10',
                )}
              >
                <div className="flex flex-col">
                  <span className={cn('text-sm font-medium', isSelected ? 'text-primary' : 'text-foreground')}>
                    {option.label}
                  </span>
                  {!hideDescription && option.description && (
                    <span className="text-xs text-muted-foreground mt-0.5">{option.description}</span>
                  )}
                </div>
                {isSelected && <IconCheck className="w-4 h-4 text-primary shrink-0" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default OptionSelect;
