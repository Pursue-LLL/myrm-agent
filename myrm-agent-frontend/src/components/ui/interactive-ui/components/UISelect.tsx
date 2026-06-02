import React from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { UIComponentProps } from '../UIComponentRegistry';
import { getValueByPath } from '../utils';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

type SelectOption = string | { value: string; label: string };

export const UISelect: React.FC<UIComponentProps> = ({
  props,
  bindings,
  data,
  onDataChange,
  validationError,
  onBlur,
}) => {
  const t = useTranslations('interactiveUI');
  const label = (props.label as string) || '';
  const options = (props.options as SelectOption[]) || [];
  const placeholder = (props.placeholder as string) || t('selectPlaceholder');
  const disabled = (props.disabled as boolean) || false;
  const required = (props.required as boolean) || false;
  const className = (props.className as string) || '';

  const valuePath = bindings.value;
  const value = valuePath ? (getValueByPath(data, valuePath) as string) || '' : '';

  const handleValueChange = (newValue: string) => {
    if (valuePath) {
      onDataChange(valuePath, newValue);
    }
  };

  const handleOpenChange = (open: boolean) => {
    if (!open && valuePath && onBlur) {
      onBlur(valuePath);
    }
  };

  const hasError = !!validationError;

  const normalizedOptions = options.map((opt) => (typeof opt === 'string' ? { value: opt, label: opt } : opt));

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      {label && (
        <label className="text-sm font-medium text-foreground">
          {label}
          {required && <span className="text-destructive ml-1">*</span>}
        </label>
      )}
      <Select
        value={value || undefined}
        onValueChange={handleValueChange}
        onOpenChange={handleOpenChange}
        disabled={disabled}
      >
        <SelectTrigger className={cn('w-full', hasError && 'border-destructive focus:ring-destructive')}>
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          {normalizedOptions.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {hasError && (
        <p className="text-xs text-destructive flex items-center gap-1 animate-in fade-in-0 slide-in-from-top-1 duration-200">
          <svg className="w-3.5 h-3.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
              clipRule="evenodd"
            />
          </svg>
          {validationError}
        </p>
      )}
    </div>
  );
};
