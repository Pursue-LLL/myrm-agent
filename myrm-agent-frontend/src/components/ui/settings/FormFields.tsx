import { IconEye, IconEyeOff, IconHelpCircle, IconLoader, IconCheck } from '@/components/ui/icons/PremiumIcons';
import { useState, useEffect } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import Tooltip from './Tooltip';

interface FormLabelProps {
  label: string;
  required?: boolean;
  tooltip?: string;
}

export const FormLabel = ({ label, required, tooltip }: FormLabelProps) => (
  <div className="flex items-center space-x-1">
    <p className="text-black/70 dark:text-white/70 text-sm">
      {label} {required && <span className="text-red-500">*</span>}
    </p>
    {tooltip && (
      <Tooltip content={tooltip}>
        <IconHelpCircle className="w-3.5 h-3.5 text-black/50 dark:text-white/50 cursor-help" />
      </Tooltip>
    )}
  </div>
);

interface InputFieldProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
  required?: boolean;
  tooltip?: string;
  isSaving?: boolean;
  onSave?: (value: string) => void;
  onBlur?: (event: React.FocusEvent<HTMLInputElement>) => void;
  isPassword?: boolean;
  error?: string;
}

export const InputField = ({
  label,
  required,
  tooltip,
  className,
  isSaving,
  onSave,
  onBlur,
  isPassword,
  error,
  ...restProps
}: InputFieldProps) => {
  const [showPassword, setShowPassword] = useState(false);
  const [value, setValue] = useState((restProps.value as string) || '');

  const handleBlur = (e: React.FocusEvent<HTMLInputElement>) => {
    if (onBlur) {
      onBlur(e);
    } else if (onSave) {
      onSave(e.target.value);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setValue(e.target.value);
    restProps.onChange?.(e);
  };

  const type = isPassword ? (showPassword ? 'text' : 'password') : restProps.type;

  return (
    <div className="flex flex-col space-y-1">
      <FormLabel label={label} required={required} tooltip={tooltip} />
      <div className="relative">
        <input
          {...restProps}
          type={type}
          value={restProps.value ?? value}
          onChange={handleChange}
          onBlur={handleBlur}
          className={cn(
            'bg-secondary w-full px-3 py-2 flex items-center overflow-hidden border border-border dark:text-white rounded-lg text-sm',
            error && 'border-red-500',
            isSaving && 'pr-10',
            isPassword && 'pr-10',
            className,
          )}
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-black/70 dark:text-white/70"
          >
            {showPassword ? <IconEyeOff className="w-4 h-4" /> : <IconEye className="w-4 h-4" />}
          </button>
        )}
        {isSaving && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2">
            <IconLoader className="w-4 h-4 animate-spin text-black/70 dark:text-white/70" />
          </div>
        )}
      </div>
      {error && <p className="text-xs text-red-500 font-medium mt-1">{error}</p>}
    </div>
  );
};

interface TextareaFieldProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  required?: boolean;
  tooltip?: string;
  isSaving?: boolean;
  onSave?: (value: string) => void;
  onBlur?: (event: React.FocusEvent<HTMLTextAreaElement>) => void;
  error?: string;
  helpText?: string;
  maxLength?: number;
  showConfirmButton?: boolean;
}

export const TextareaField = ({
  label,
  required,
  tooltip,
  className,
  isSaving,
  onSave,
  onBlur,
  error,
  helpText,
  maxLength,
  showConfirmButton = false,
  ...restProps
}: TextareaFieldProps) => {
  const [value, setValue] = useState((restProps.value as string) || '');
  const [initialValue, setInitialValue] = useState((restProps.value as string) || '');
  const [hasChanges, setHasChanges] = useState(false);

  // 同步外部value变化到内部state
  useEffect(() => {
    if (restProps.value !== undefined) {
      const newValue = restProps.value as string;
      setValue(newValue);
      setInitialValue(newValue);
    }
  }, [restProps.value]);

  const handleBlur = (e: React.FocusEvent<HTMLTextAreaElement>) => {
    if (onBlur) {
      onBlur(e);
    } else if (onSave && !showConfirmButton) {
      onSave(e.target.value);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = e.target.value;

    // 如果设置了最大长度限制，则截断文本
    if (maxLength && newValue.length > maxLength) {
      return;
    }
    setValue(newValue);
    // 比较当前值与初始值来设置hasChanges
    setHasChanges(newValue !== initialValue);
    restProps.onChange?.(e);
  };

  const handleSave = () => {
    if (onSave && hasChanges) {
      onSave(value); // 使用内部value而不是外部value
      setInitialValue(value); // 更新initialValue为当前value
      setHasChanges(false);
    }
  };

  const currentLength = (restProps.value !== undefined ? (restProps.value as string) : value).length;

  return (
    <div className="flex flex-col space-y-1">
      <FormLabel label={label} required={required} tooltip={tooltip} />
      <div className="relative">
        <textarea
          {...restProps}
          value={restProps.value !== undefined ? restProps.value : value}
          onChange={handleChange}
          onBlur={handleBlur}
          className={cn(
            'text-sm w-full flex items-center justify-between p-3 bg-secondary rounded-lg hover:bg-muted dark:hover:bg-muted transition-colors resize-none',
            error && 'border border-red-500',
            showConfirmButton && 'pb-12',
            className,
          )}
          rows={4}
        />
        {isSaving && (
          <div className="absolute right-3 top-3">
            <IconLoader className="w-4 h-4 animate-spin text-black/70 dark:text-white/70" />
          </div>
        )}

        {/* 字数统计和确认按钮 */}
        {(maxLength || showConfirmButton) && (
          <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between">
            {maxLength && (
              <span
                className={cn(
                  'text-xs',
                  currentLength > maxLength * 0.9 ? 'text-orange-500' : 'text-black/60 dark:text-white/60',
                  currentLength >= maxLength ? 'text-red-500' : '',
                )}
              >
                {currentLength}/{maxLength}
              </span>
            )}

            {showConfirmButton && (
              <button
                onClick={handleSave}
                disabled={!hasChanges || isSaving}
                className={cn(
                  'ml-auto h-8 px-3 rounded-full text-sm font-medium transition-colors flex items-center space-x-1',
                  'bg-primary text-primary-foreground hover:bg-primary/90',
                  'disabled:opacity-50 disabled:pointer-events-none',
                )}
              >
                {isSaving ? (
                  <IconLoader className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <>
                    <IconCheck className="w-3.5 h-3.5" />
                    <span>确认</span>
                  </>
                )}
              </button>
            )}
          </div>
        )}
      </div>
      {helpText && <p className="text-xs text-black/60 dark:text-white/60 mt-1">{helpText}</p>}
      {error && <p className="text-xs text-red-500 font-medium mt-1">{error}</p>}
    </div>
  );
};
