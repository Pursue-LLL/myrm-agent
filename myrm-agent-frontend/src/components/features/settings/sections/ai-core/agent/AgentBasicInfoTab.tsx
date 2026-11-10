import { useState, useCallback, type KeyboardEvent } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Input } from '@/components/primitives/input';
import { Textarea } from '@/components/primitives/textarea';
import { Switch } from '@/components/primitives/switch';
import { X } from 'lucide-react';

const MAX_SUGGESTION_PROMPTS = 8;

interface AgentBasicInfoTabProps {
  name: string;
  description: string;
  allowDiscovery: boolean;
  formalKoreanReplies: boolean;
  suggestionPrompts: string[];
  readonly?: boolean;
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onAllowDiscoveryChange: (value: boolean) => void;
  onFormalKoreanRepliesChange: (value: boolean) => void;
  onSuggestionPromptsChange: (value: string[]) => void;
}

export function AgentBasicInfoTab({
  name,
  description,
  allowDiscovery,
  formalKoreanReplies,
  suggestionPrompts,
  readonly: isReadonly = false,
  onNameChange,
  onDescriptionChange,
  onAllowDiscoveryChange,
  onFormalKoreanRepliesChange,
  onSuggestionPromptsChange,
}: AgentBasicInfoTabProps) {
  const t = useTranslations();
  const [promptInput, setPromptInput] = useState('');

  const handleAddPrompt = useCallback(() => {
    const trimmed = promptInput.trim();
    if (!trimmed || suggestionPrompts.length >= MAX_SUGGESTION_PROMPTS) {
      return;
    }
    if (suggestionPrompts.includes(trimmed)) {
      return;
    }
    onSuggestionPromptsChange([...suggestionPrompts, trimmed]);
    setPromptInput('');
  }, [promptInput, suggestionPrompts, onSuggestionPromptsChange]);

  const handleRemovePrompt = useCallback(
    (index: number) => {
      onSuggestionPromptsChange(suggestionPrompts.filter((_, i) => i !== index));
    },
    [suggestionPrompts, onSuggestionPromptsChange],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleAddPrompt();
      }
    },
    [handleAddPrompt],
  );

  return (
    <div
      className={cn(
        'rounded-2xl overflow-hidden',
        'bg-card border border-border/50',
        'animate-in fade-in-50 duration-300',
      )}
    >
      <div className="p-6 space-y-6">
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground flex items-center gap-2">
            {t('agent.name')}
            <span className="text-destructive-text">*</span>
          </label>
          <Input
            value={name}
            onChange={(e) => onNameChange(e.target.value)}
            placeholder={t('agent.namePlaceholder')}
            disabled={isReadonly}
            className={cn(
              'h-12 rounded-xl',
              'bg-background border-border/50',
              'focus:ring-2 focus:ring-primary/20 focus:border-primary/50',
              isReadonly && 'opacity-70 cursor-not-allowed',
            )}
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">{t('agent.descriptionLabel')}</label>
          <Textarea
            value={description}
            onChange={(e) => onDescriptionChange(e.target.value)}
            placeholder={t('agent.descriptionPlaceholder')}
            rows={4}
            disabled={isReadonly}
            className={cn(
              'rounded-xl resize-none',
              'bg-background border-border/50',
              'focus:ring-2 focus:ring-primary/20 focus:border-primary/50',
              isReadonly && 'opacity-70 cursor-not-allowed',
            )}
          />
          <p className="text-xs text-muted-foreground">{description.length}/200</p>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">{t('agent.suggestionPrompts.title')}</label>
          <p className="text-xs text-muted-foreground">{t('agent.suggestionPrompts.description')}</p>
          {suggestionPrompts.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {suggestionPrompts.map((prompt, idx) => (
                <span
                  key={idx}
                  className={cn(
                    'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm',
                    'bg-primary/5 border border-primary/20 text-foreground',
                  )}
                >
                  <span className="max-w-[200px] truncate">{prompt}</span>
                  {!isReadonly && (
                    <button
                      type="button"
                      onClick={() => handleRemovePrompt(idx)}
                      className="text-muted-foreground hover:text-destructive-text transition-colors"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                </span>
              ))}
            </div>
          )}
          {!isReadonly && suggestionPrompts.length < MAX_SUGGESTION_PROMPTS && (
            <div className="flex gap-2">
              <Input
                value={promptInput}
                onChange={(e) => setPromptInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t('agent.suggestionPrompts.placeholder')}
                className={cn(
                  'flex-1 h-10 rounded-xl',
                  'bg-background border-border/50',
                  'focus:ring-2 focus:ring-primary/20 focus:border-primary/50',
                )}
              />
            </div>
          )}
          {suggestionPrompts.length > 0 && (
            <p className="text-xs text-muted-foreground">
              {suggestionPrompts.length}/{MAX_SUGGESTION_PROMPTS}
            </p>
          )}
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div>
              <label className="text-sm font-medium text-foreground">{t('agent.allowDiscovery.title')}</label>
              <p className="text-xs text-muted-foreground">{t('agent.allowDiscovery.description')}</p>
            </div>
            <Switch checked={allowDiscovery} onCheckedChange={onAllowDiscoveryChange} disabled={isReadonly} />
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-4">
            <div>
              <label className="text-sm font-medium text-foreground">{t('agent.formalKoreanReplies.title')}</label>
              <p className="text-xs text-muted-foreground">{t('agent.formalKoreanReplies.description')}</p>
            </div>
            <Switch checked={formalKoreanReplies} onCheckedChange={onFormalKoreanRepliesChange} disabled={isReadonly} />
          </div>
        </div>
      </div>
    </div>
  );
}
