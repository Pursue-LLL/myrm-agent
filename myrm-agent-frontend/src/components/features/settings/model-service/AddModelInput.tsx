import { memo, useState, useRef, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Plus, X } from 'lucide-react';

interface AddModelInputProps {
  onAdd: (modelName: string) => void;
  existingModels: string[];
}

/**
 * 添加模型输入框组件
 * 支持键盘快捷键（Enter提交、Escape取消）
 */
export const AddModelInput = memo<AddModelInputProps>(({ onAdd, existingModels }) => {
  const t = useTranslations('settings.modelService');
  const [isAdding, setIsAdding] = useState(false);
  const [modelName, setModelName] = useState('');
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isAdding) {
      inputRef.current?.focus();
    }
  }, [isAdding]);

  const handleAdd = () => {
    const trimmed = modelName.trim();
    if (!trimmed) {
      setError(t('modelNameRequired'));
      return;
    }
    if (existingModels.includes(trimmed)) {
      setError(t('modelAlreadyExists'));
      return;
    }
    onAdd(trimmed);
    setModelName('');
    setError('');
    setIsAdding(false);
  };

  const handleCancel = () => {
    setIsAdding(false);
    setModelName('');
    setError('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleAdd();
    } else if (e.key === 'Escape') {
      handleCancel();
    }
  };

  if (!isAdding) {
    return (
      <button
        onClick={() => setIsAdding(true)}
        className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl border border-dashed border-border hover:border-primary/50 hover:bg-primary/5 text-muted-foreground hover:text-primary transition-all"
      >
        <Plus className="w-4 h-4" />
        <span className="text-sm font-medium">{t('addModel')}</span>
      </button>
    );
  }

  return (
    <div className="w-full space-y-2">
      <div className="flex gap-2">
        <input
          ref={inputRef}
          type="text"
          value={modelName}
          onChange={(e) => {
            setModelName(e.target.value);
            setError('');
          }}
          onKeyDown={handleKeyDown}
          placeholder={t('modelNamePlaceholder')}
          className="flex-1 px-3 py-2 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/50"
        />
        <button
          onClick={handleAdd}
          disabled={!modelName.trim()}
          className="px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
        >
          {t('add')}
        </button>
        <button
          onClick={handleCancel}
          className="p-2 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-all"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
      {error && <p className="text-xs text-destructive pl-3">{error}</p>}
    </div>
  );
});

AddModelInput.displayName = 'AddModelInput';
