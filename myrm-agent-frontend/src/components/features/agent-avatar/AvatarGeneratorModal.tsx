'use client';

/**
 * Avatar Generator Modal Component for Agent Bot Personalization.
 *
 * [INPUT] agentId: string, initialMetadata?: AvatarMetadata, isOpen: boolean, onClose: () => void, onSave: (meta: AvatarMetadata) => void
 * [OUTPUT] AvatarGeneratorModal: Dual-mode dialog supporting Dice-roll seeds and AI-prompt generation.
 * [POS] src/components/features/agent-avatar/AvatarGeneratorModal.tsx
 */

import { memo, useState, useCallback } from 'react';
import {
  Sparkles,
  Dices,
  Wand2,
  X,
  Save,
  Loader2,
  Bot,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import type { AvatarMetadata, AvatarStyle } from './avatarTypes';
import { generateDeterministicSvg } from './avatarGenerator';
import { avatarService } from './avatarService';
import { AvatarLockWidget } from './AvatarLockWidget';

export interface AvatarGeneratorModalProps {
  agentId: string;
  isOpen: boolean;
  onClose: () => void;
  onSave: (metadata: AvatarMetadata) => void;
  initialMetadata?: AvatarMetadata;
  className?: string;
}

export const AvatarGeneratorModal = memo(function AvatarGeneratorModal({
  agentId,
  isOpen,
  onClose,
  onSave,
  initialMetadata,
  className,
}: AvatarGeneratorModalProps) {
  const t = useTranslations('agentAvatar');
  const [activeTab, setActiveTab] = useState<'dice' | 'ai'>('dice');

  const [metadata, setMetadata] = useState<AvatarMetadata>(() => {
    if (initialMetadata) {
      return initialMetadata;
    }
    const defaultSvg = generateDeterministicSvg(agentId, 'beam', '#6366f1');
    return {
      seed: agentId,
      style: 'beam',
      backgroundColor: '#6366f1',
      isLocked: false,
      svgData: defaultSvg,
    };
  });

  const [aiPrompt, setAiPrompt] = useState('Cyberpunk friendly robotic owl with illuminated visor');
  const [isGeneratingAi, setIsGeneratingAi] = useState(false);

  const handleToggleLock = useCallback(() => {
    setMetadata((prev) => ({ ...prev, isLocked: !prev.isLocked }));
  }, []);

  const handleRollSeed = useCallback((newSeed: string) => {
    setMetadata((prev) => {
      const newSvg = generateDeterministicSvg(newSeed, prev.style, prev.backgroundColor);
      return {
        ...prev,
        seed: newSeed,
        svgData: newSvg,
        imageUrl: null,
      };
    });
  }, []);

  const handleChangeStyle = useCallback((newStyle: AvatarStyle) => {
    setMetadata((prev) => {
      const newSvg = generateDeterministicSvg(prev.seed, newStyle, prev.backgroundColor);
      return {
        ...prev,
        style: newStyle,
        svgData: newSvg,
      };
    });
  }, []);

  const handleChangeBgColor = useCallback((newColor: string) => {
    setMetadata((prev) => {
      const newSvg = generateDeterministicSvg(prev.seed, prev.style, newColor);
      return {
        ...prev,
        backgroundColor: newColor,
        svgData: newSvg,
      };
    });
  }, []);

  const handleGenerateAi = useCallback(async () => {
    if (!aiPrompt.trim() || isGeneratingAi) {
      return;
    }

    setIsGeneratingAi(true);
    try {
      const imgUrl = await avatarService.generateAiAvatar({
        prompt: aiPrompt,
        style: metadata.style,
      });
      setMetadata((prev) => ({
        ...prev,
        imageUrl: imgUrl,
      }));
    } finally {
      setIsGeneratingAi(false);
    }
  }, [aiPrompt, isGeneratingAi, metadata.style]);

  const handleSaveAndLock = useCallback(() => {
    const lockedMeta: AvatarMetadata = {
      ...metadata,
      isLocked: true,
    };
    onSave(lockedMeta);
    onClose();
  }, [metadata, onSave, onClose]);

  if (!isOpen) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-150"
      data-testid="avatar-generator-modal"
    >
      <div
        className={cn(
          'w-full max-w-md rounded-2xl border border-border bg-background shadow-2xl overflow-hidden flex flex-col text-foreground',
          className,
        )}
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border/80 bg-muted/20">
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-primary" />
            <span className="font-semibold text-xs">
              {t('modalTitle') || 'Agent Avatar Studio & Dice Lock'}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            title={t('close') || 'Close'}
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Mode Switch Tabs */}
        <div className="flex border-b border-border/60 bg-muted/30 p-1">
          <button
            type="button"
            onClick={() => {
              setActiveTab('dice');
            }}
            className={cn(
              'flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium transition-all',
              activeTab === 'dice'
                ? 'bg-card text-foreground shadow-xs font-semibold'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <Dices className="h-3.5 w-3.5 text-primary" />
            <span>{t('tabDice') || 'Deterministic Dice Roll'}</span>
          </button>

          <button
            type="button"
            onClick={() => {
              setActiveTab('ai');
            }}
            className={cn(
              'flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium transition-all',
              activeTab === 'ai'
                ? 'bg-card text-foreground shadow-xs font-semibold'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <Wand2 className="h-3.5 w-3.5 text-amber-500" />
            <span>{t('tabAi') || 'AI Generative Avatar'}</span>
          </button>
        </div>

        {/* Body Content */}
        <div className="p-4 flex flex-col gap-4 max-h-[75vh] overflow-y-auto">
          {/* Central Interactive Preview */}
          <AvatarLockWidget
            metadata={metadata}
            onToggleLock={handleToggleLock}
            onRollSeed={handleRollSeed}
            onChangeStyle={handleChangeStyle}
            onChangeBgColor={handleChangeBgColor}
            size="lg"
          />

          {/* AI Mode Specific Prompt Controls */}
          {activeTab === 'ai' && (
            <div className="flex flex-col gap-2 p-3 rounded-xl border border-border/80 bg-muted/20 text-xs">
              <label className="font-medium text-muted-foreground flex items-center gap-1">
                <Sparkles className="h-3.5 w-3.5 text-amber-500" />
                <span>{t('aiPromptLabel') || 'Avatar Persona Prompt'}</span>
              </label>
              <textarea
                rows={2}
                value={aiPrompt}
                onChange={(e) => {
                  setAiPrompt(e.target.value);
                }}
                placeholder={t('aiPromptPlaceholder') || 'Describe bot appearance or persona...'}
                className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary/50 text-foreground resize-none"
              />
              <button
                type="button"
                onClick={handleGenerateAi}
                disabled={isGeneratingAi || !aiPrompt.trim()}
                className={cn(
                  'flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-semibold transition-all shadow-xs',
                  isGeneratingAi || !aiPrompt.trim()
                    ? 'bg-muted text-muted-foreground cursor-not-allowed'
                    : 'bg-primary text-primary-foreground hover:opacity-90 active:scale-98',
                )}
              >
                {isGeneratingAi ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span>{t('generating') || 'Generating...'}</span>
                  </>
                ) : (
                  <>
                    <Wand2 className="h-3.5 w-3.5" />
                    <span>{t('generateAiCta') || 'Cast AI Avatar'}</span>
                  </>
                )}
              </button>
            </div>
          )}
        </div>

        {/* Modal Actions Footer */}
        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-border/80 bg-muted/20">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded-lg text-xs font-medium border border-border hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
          >
            {t('cancel') || 'Cancel'}
          </button>

          <button
            type="button"
            onClick={handleSaveAndLock}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-primary text-primary-foreground hover:opacity-90 active:scale-95 shadow-xs transition-all"
          >
            <Save className="h-3.5 w-3.5" />
            <span>{t('saveAndLock') || 'Save & Lock Avatar'}</span>
          </button>
        </div>
      </div>
    </div>
  );
});
