import { useState, useCallback, type KeyboardEvent } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Input } from '@/components/primitives/input';
import { Textarea } from '@/components/primitives/textarea';
import {
  IconBriefcase,
  IconZap,
  IconBook,
  IconGraduation,
  IconPalette,
  IconBrain,
} from '@/components/features/icons/PremiumIcons';
import { Switch } from '@/components/primitives/switch';
import {
  Anchor,
  Cat,
  Drama,
  Eye,
  Flame,
  Heart,
  MessageCircleHeartIcon,
  Shield,
  Smile,
  Sparkles,
  Unlock,
  Waves,
  X,
  Zap,
} from 'lucide-react';

const PERSONALITY_STYLES: Array<{ value: string; emoji: React.ReactNode; category: 'practical' | 'fun' }> = [
  { value: 'professional', emoji: <IconBriefcase className="w-5 h-5" />, category: 'practical' },
  { value: 'friendly', emoji: <Smile className="w-5 h-5" />, category: 'practical' },
  { value: 'concise', emoji: <IconZap className="w-5 h-5" />, category: 'practical' },
  { value: 'detailed', emoji: <IconBook className="w-5 h-5" />, category: 'practical' },
  { value: 'humorous', emoji: <MessageCircleHeartIcon className="w-5 h-5" />, category: 'practical' },
  { value: 'academic', emoji: <IconGraduation className="w-5 h-5" />, category: 'practical' },
  { value: 'creative', emoji: <IconPalette className="w-5 h-5" />, category: 'practical' },
  { value: 'socratic', emoji: <IconBrain className="w-5 h-5" />, category: 'practical' },
  { value: 'pirate', emoji: <Anchor className="w-5 h-5" />, category: 'fun' },
  { value: 'shakespeare', emoji: <Drama className="w-5 h-5" />, category: 'fun' },
  { value: 'noir', emoji: <Eye className="w-5 h-5" />, category: 'fun' },
  { value: 'kawaii', emoji: <Sparkles className="w-5 h-5" />, category: 'fun' },
  { value: 'catgirl', emoji: <Cat className="w-5 h-5" />, category: 'fun' },
  { value: 'hype', emoji: <Flame className="w-5 h-5" />, category: 'fun' },
  { value: 'uwu', emoji: <Heart className="w-5 h-5" />, category: 'fun' },
  { value: 'surfer', emoji: <Waves className="w-5 h-5" />, category: 'fun' },
];

const MAX_SUGGESTION_PROMPTS = 8;

interface AgentBasicInfoTabProps {
  name: string;
  description: string;
  personalityStyle: string;
  promptMode: 'full' | 'lean' | 'naked';
  allowDiscovery: boolean;
  suggestionPrompts: string[];
  readonly?: boolean;
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onPersonalityChange: (value: string) => void;
  onPromptModeChange: (value: 'full' | 'lean' | 'naked') => void;
  onAllowDiscoveryChange: (value: boolean) => void;
  onSuggestionPromptsChange: (value: string[]) => void;
}

const PROMPT_MODES: Array<{ value: 'full' | 'lean' | 'naked'; icon: React.ReactNode }> = [
  { value: 'full', icon: <Shield className="w-5 h-5" /> },
  { value: 'lean', icon: <Zap className="w-5 h-5" /> },
  { value: 'naked', icon: <Unlock className="w-5 h-5" /> },
];

export function AgentBasicInfoTab({
  name,
  description,
  personalityStyle,
  promptMode,
  allowDiscovery,
  suggestionPrompts,
  readonly: isReadonly = false,
  onNameChange,
  onDescriptionChange,
  onPersonalityChange,
  onPromptModeChange,
  onAllowDiscoveryChange,
  onSuggestionPromptsChange,
}: AgentBasicInfoTabProps) {
  const t = useTranslations();
  const [promptInput, setPromptInput] = useState('');

  const handleAddPrompt = useCallback(() => {
    const trimmed = promptInput.trim();
    if (!trimmed || suggestionPrompts.length >= MAX_SUGGESTION_PROMPTS) return;
    if (suggestionPrompts.includes(trimmed)) return;
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
            <span className="text-destructive">*</span>
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
                      className="text-muted-foreground hover:text-destructive transition-colors"
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
              <label className="text-sm font-medium text-foreground">{t('agent.allowDiscovery.title', { fallback: '允许被其他智能体发现并委派 (Allow Discovery)' })}</label>
              <p className="text-xs text-muted-foreground">{t('agent.allowDiscovery.description', { fallback: '开启后，其他智能体可以通过 @ 提及或自动组队时发现并调用此智能体。关闭可隐藏半成品。' })}</p>
            </div>
            <Switch
              checked={allowDiscovery}
              onCheckedChange={onAllowDiscoveryChange}
              disabled={isReadonly}
            />
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">{t('agent.promptMode.title')}</label>
          <p className="text-xs text-muted-foreground">{t('agent.promptMode.description')}</p>
          <div className="grid grid-cols-3 gap-2">
            {PROMPT_MODES.map((mode) => {
              const isSelected = promptMode === mode.value;
              return (
                <button
                  key={mode.value}
                  type="button"
                  onClick={() => !isReadonly && onPromptModeChange(mode.value)}
                  disabled={isReadonly}
                  className={cn(
                    'flex flex-col items-center gap-1.5 p-3 rounded-xl',
                    'border transition-all duration-200',
                    isReadonly ? 'cursor-not-allowed opacity-70' : 'cursor-pointer',
                    isSelected
                      ? 'border-primary/40 bg-primary/5 ring-1 ring-primary/20'
                      : 'border-border/40 bg-background hover:border-border hover:bg-muted/30',
                  )}
                >
                  <span className="text-xl leading-none">{mode.icon}</span>
                  <span
                    className={cn(
                      'text-xs font-medium leading-tight text-center',
                      isSelected ? 'text-primary' : 'text-muted-foreground',
                    )}
                  >
                    {t(`agent.promptMode.modes.${mode.value}`)}
                  </span>
                </button>
              );
            })}
          </div>
          <p className="text-xs text-muted-foreground/80 italic">{t(`agent.promptMode.hints.${promptMode}`)}</p>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">{t('agent.personality.title')}</label>
          <p className="text-xs text-muted-foreground">{t('agent.personality.description')}</p>
          {(['practical', 'fun'] as const).map((category) => {
            const styles = PERSONALITY_STYLES.filter((s) => s.category === category);
            return (
              <div key={category} className="space-y-1.5">
                <span className="text-xs font-medium text-muted-foreground/70">
                  {t(`agent.personality.category.${category}`)}
                </span>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {styles.map((style) => {
                    const isSelected = personalityStyle === style.value;
                    return (
                      <button
                        key={style.value}
                        type="button"
                        onClick={() => !isReadonly && onPersonalityChange(style.value)}
                        disabled={isReadonly}
                        className={cn(
                          'flex flex-col items-center gap-1.5 p-3 rounded-xl',
                          'border transition-all duration-200',
                          isReadonly ? 'cursor-not-allowed opacity-70' : 'cursor-pointer',
                          isSelected
                            ? 'border-primary/40 bg-primary/5 ring-1 ring-primary/20'
                            : 'border-border/40 bg-background hover:border-border hover:bg-muted/30',
                        )}
                      >
                        <span className="text-xl leading-none">{style.emoji}</span>
                        <span
                          className={cn(
                            'text-xs font-medium leading-tight text-center',
                            isSelected ? 'text-primary' : 'text-muted-foreground',
                          )}
                        >
                          {t(`agent.personality.styles.${style.value}`)}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
