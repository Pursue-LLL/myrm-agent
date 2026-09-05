'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: 多语言国际化)
 * - next/navigation::useRouter (POS: 页面路由跳转)
 * - lucide-react::Icons (POS: 现代矢量图标)
 * - sonner::toast (POS: 全局通知提示)
 * - @/store/useProviderStore::useProviderStore (POS: 提供商与模型状态中枢)
 * - ./modelOrchestrationRecipes (POS: 编排预设与就绪度计算引擎)
 *
 * [OUTPUT]
 * - ModelOrchestrationPlaybookDialog: 交互式模型编排最佳实践看板弹窗
 *
 * [POS]
 * 空聊天与设置中心复用的模型编排指南。向用户清晰解释 Brain/Hands 分工、Routing 与 MoA
 * 正交概念、Agent 4x Token 经济学，并支持根据已启用模型一键应用黄金预设。
 */

import React, { memo, useCallback, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import {
  Brain,
  Wrench,
  GitFork,
  Users,
  Coins,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  Sparkles,
  Sliders,
  ShieldCheck,
} from 'lucide-react';
import useProviderStore from '@/store/useProviderStore';
import { useShallow } from 'zustand/react/shallow';
import { toast } from 'sonner';
import {
  MODEL_ORCHESTRATION_RECIPES,
  resolveRecipeReadiness,
  applyOrchestrationRecipe,
  type ModelOrchestrationRecipe,
  type RecipeTierId,
} from './modelOrchestrationRecipes';
import { cn } from '@/lib/utils/classnameUtils';

interface ModelOrchestrationPlaybookDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const ModelOrchestrationPlaybookDialog = memo(function ModelOrchestrationPlaybookDialog({
  open,
  onOpenChange,
}: ModelOrchestrationPlaybookDialogProps) {
  const t = useTranslations('chat.modelPlaybook');
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<'recipes' | 'principles' | 'economics'>('recipes');

  const {
    providers,
    defaultModelConfig,
    getEnabledModels,
    setBaseModel,
    setLiteModel,
    setRoutingEnabled,
    setRoutingLightModel,
    setRoutingReasoningModel,
    setAutoMoaReasoning,
  } = useProviderStore(
    useShallow((s) => ({
      providers: s.providers,
      defaultModelConfig: s.defaultModelConfig,
      getEnabledModels: s.getEnabledModels,
      setBaseModel: s.setBaseModel,
      setLiteModel: s.setLiteModel,
      setRoutingEnabled: s.setRoutingEnabled,
      setRoutingLightModel: s.setRoutingLightModel,
      setRoutingReasoningModel: s.setRoutingReasoningModel,
      setAutoMoaReasoning: s.setAutoMoaReasoning,
    })),
  );

  const enabledModels = useMemo(() => {
    // Explicitly reference providers to re-calculate enabled models upon provider mutations
    void providers;
    return getEnabledModels();
  }, [getEnabledModels, providers]);

  const recipeReadinessMap = useMemo(() => {
    const map = new Map<RecipeTierId, ReturnType<typeof resolveRecipeReadiness>>();
    for (const recipe of MODEL_ORCHESTRATION_RECIPES) {
      map.set(recipe.id, resolveRecipeReadiness(recipe, enabledModels));
    }
    return map;
  }, [enabledModels]);

  const handleApplyRecipe = useCallback(
    (recipe: ModelOrchestrationRecipe) => {
      const readiness = recipeReadinessMap.get(recipe.id);
      if (!readiness || !readiness.isReady) {
        toast.error(t('cannotApplyMissingModels'));
        return;
      }

      const success = applyOrchestrationRecipe(recipe, readiness, {
        setBaseModel,
        setLiteModel,
        setRoutingEnabled,
        setRoutingLightModel,
        setRoutingReasoningModel,
        setAutoMoaReasoning,
      });

      if (success) {
        toast.success(t('recipeAppliedSuccess', { title: t(recipe.titleKey) }));
        onOpenChange(false);
      }
    },
    [
      recipeReadinessMap,
      setBaseModel,
      setLiteModel,
      setRoutingEnabled,
      setRoutingLightModel,
      setRoutingReasoningModel,
      setAutoMoaReasoning,
      t,
      onOpenChange,
    ],
  );

  const handleNavigateToSettings = useCallback(() => {
    onOpenChange(false);
    router.push('/settings/models?focus=routing');
  }, [onOpenChange, router]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="model-orchestration-playbook-dialog"
        className="max-w-3xl max-h-[90vh] flex flex-col p-0 overflow-hidden bg-background/95 backdrop-blur-xl border-border/60 shadow-2xl"
      >
        <DialogHeader className="p-6 pb-4 border-b border-border/40">
          <div className="flex items-center gap-2 text-purple-600 dark:text-purple-400 mb-1">
            <Sparkles className="w-5 h-5" />
            <span className="text-xs font-semibold tracking-wider uppercase">{t('subtitle')}</span>
          </div>
          <DialogTitle className="text-xl font-bold tracking-tight text-foreground">
            {t('title')}
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground mt-1">
            {t('description')}
          </DialogDescription>

          <div className="flex items-center gap-2 mt-4 p-1 rounded-xl bg-muted/40 border border-border/30 w-full sm:w-auto">
            <button
              type="button"
              data-testid="playbook-tab-recipes"
              onClick={() => setActiveTab('recipes')}
              className={cn(
                'flex-1 sm:flex-none px-3.5 py-1.5 text-xs font-medium rounded-lg transition-all',
                activeTab === 'recipes'
                  ? 'bg-background text-foreground shadow-xs font-semibold'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {t('tabRecipes')}
            </button>
            <button
              type="button"
              data-testid="playbook-tab-principles"
              onClick={() => setActiveTab('principles')}
              className={cn(
                'flex-1 sm:flex-none px-3.5 py-1.5 text-xs font-medium rounded-lg transition-all',
                activeTab === 'principles'
                  ? 'bg-background text-foreground shadow-xs font-semibold'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {t('tabPrinciples')}
            </button>
            <button
              type="button"
              data-testid="playbook-tab-economics"
              onClick={() => setActiveTab('economics')}
              className={cn(
                'flex-1 sm:flex-none px-3.5 py-1.5 text-xs font-medium rounded-lg transition-all',
                activeTab === 'economics'
                  ? 'bg-background text-foreground shadow-xs font-semibold'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {t('tabEconomics')}
            </button>
          </div>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {activeTab === 'recipes' && (
            <div className="space-y-4">
              <div className="text-xs text-muted-foreground leading-relaxed">
                {t('recipesIntro')}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
                {MODEL_ORCHESTRATION_RECIPES.map((recipe) => {
                  const readiness = recipeReadinessMap.get(recipe.id);
                  const isReady = Boolean(readiness?.isReady);

                  return (
                    <div
                      key={recipe.id}
                      className={cn(
                        'flex flex-col justify-between p-4 rounded-xl border transition-all duration-200',
                        recipe.accentColor === 'emerald' &&
                          'border-emerald-500/20 bg-emerald-500/5 hover:border-emerald-500/40',
                        recipe.accentColor === 'purple' &&
                          'border-purple-500/20 bg-purple-500/5 hover:border-purple-500/40',
                        recipe.accentColor === 'amber' &&
                          'border-amber-500/20 bg-amber-500/5 hover:border-amber-500/40',
                      )}
                    >
                      <div className="space-y-3">
                        <div className="flex items-center justify-between gap-2">
                          <span
                            className={cn(
                              'text-[10px] font-semibold px-2 py-0.5 rounded-full border',
                              recipe.accentColor === 'emerald' &&
                                'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20',
                              recipe.accentColor === 'purple' &&
                                'bg-purple-500/10 text-purple-700 dark:text-purple-300 border-purple-500/20',
                              recipe.accentColor === 'amber' &&
                                'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20',
                            )}
                          >
                            {t(recipe.badgeKey)}
                          </span>
                          {isReady ? (
                            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                              <CheckCircle2 className="w-3 h-3" />
                              {t('statusReady')}
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-muted-foreground">
                              <AlertCircle className="w-3 h-3" />
                              {t('statusMissing')}
                            </span>
                          )}
                        </div>

                        <div>
                          <h4 className="text-sm font-semibold text-foreground">{t(recipe.titleKey)}</h4>
                          <p className="text-xs text-muted-foreground mt-1 leading-snug">
                            {t(recipe.descriptionKey)}
                          </p>
                        </div>

                        <div className="space-y-1.5 pt-2 border-t border-border/40 text-xs">
                          <div className="flex items-start gap-1.5">
                            <Brain className="w-3.5 h-3.5 text-purple-500 shrink-0 mt-0.5" />
                            <div className="min-w-0">
                              <span className="font-medium text-foreground">{t('brainLabel')}: </span>
                              <span className="text-muted-foreground break-all">
                                {readiness?.reasoningMatch
                                  ? readiness.reasoningMatch.model
                                  : t(recipe.brainRoleKey)}
                              </span>
                            </div>
                          </div>
                          <div className="flex items-start gap-1.5">
                            <Wrench className="w-3.5 h-3.5 text-emerald-500 shrink-0 mt-0.5" />
                            <div className="min-w-0">
                              <span className="font-medium text-foreground">{t('handsLabel')}: </span>
                              <span className="text-muted-foreground break-all">
                                {readiness?.lightMatch ? readiness.lightMatch.model : t(recipe.handsRoleKey)}
                              </span>
                            </div>
                          </div>
                        </div>

                        <div className="text-[11px] font-medium text-muted-foreground bg-background/60 p-2 rounded-lg border border-border/40">
                          {t(recipe.costBenefitKey)}
                        </div>

                        {recipe.caveatKey && (
                          <div className="text-[10px] text-amber-600 dark:text-amber-400 bg-amber-500/10 p-2 rounded-lg border border-amber-500/20">
                            {t(recipe.caveatKey)}
                          </div>
                        )}
                      </div>

                      <div className="pt-4 mt-2">
                        {isReady ? (
                          <Button
                            size="sm"
                            onClick={() => handleApplyRecipe(recipe)}
                            className={cn(
                              'w-full text-xs font-semibold transition-all',
                              recipe.accentColor === 'emerald' &&
                                'bg-emerald-600 hover:bg-emerald-700 text-white',
                              recipe.accentColor === 'purple' &&
                                'bg-purple-600 hover:bg-purple-700 text-white',
                              recipe.accentColor === 'amber' &&
                                'bg-amber-600 hover:bg-amber-700 text-white',
                            )}
                          >
                            {t('applyRecipeButton')}
                          </Button>
                        ) : (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handleNavigateToSettings}
                            className="w-full text-xs text-muted-foreground"
                          >
                            {t('configureProviderButton')}
                          </Button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {activeTab === 'principles' && (
            <div className="space-y-5">
              <div className="p-4 rounded-xl border border-purple-500/20 bg-purple-500/5 space-y-2">
                <div className="flex items-center gap-2 text-purple-700 dark:text-purple-300 font-semibold text-sm">
                  <Brain className="w-4 h-4" />
                  <span>{t('brainVsHandsTitle')}</span>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {t('brainVsHandsDesc')}
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                  <div className="p-3 rounded-lg bg-background/80 border border-border/40">
                    <span className="text-xs font-semibold text-foreground flex items-center gap-1.5 mb-1">
                      <Brain className="w-3.5 h-3.5 text-purple-500" />
                      {t('brainSpecTitle')}
                    </span>
                    <p className="text-[11px] text-muted-foreground">{t('brainSpecDesc')}</p>
                  </div>
                  <div className="p-3 rounded-lg bg-background/80 border border-border/40">
                    <span className="text-xs font-semibold text-foreground flex items-center gap-1.5 mb-1">
                      <Wrench className="w-3.5 h-3.5 text-emerald-500" />
                      {t('handsSpecTitle')}
                    </span>
                    <p className="text-[11px] text-muted-foreground">{t('handsSpecDesc')}</p>
                  </div>
                </div>
              </div>

              <div className="p-4 rounded-xl border border-border/60 bg-muted/20 space-y-2">
                <div className="flex items-center gap-2 text-foreground font-semibold text-sm">
                  <GitFork className="w-4 h-4 text-sky-500" />
                  <span>{t('routingVsMoaTitle')}</span>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {t('routingVsMoaDesc')}
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                  <div className="p-3 rounded-lg bg-background/80 border border-border/40">
                    <span className="text-xs font-semibold text-foreground flex items-center gap-1.5 mb-1">
                      <GitFork className="w-3.5 h-3.5 text-sky-500" />
                      {t('routingFeatureTitle')}
                    </span>
                    <p className="text-[11px] text-muted-foreground">{t('routingFeatureDesc')}</p>
                  </div>
                  <div className="p-3 rounded-lg bg-background/80 border border-border/40">
                    <span className="text-xs font-semibold text-foreground flex items-center gap-1.5 mb-1">
                      <Users className="w-3.5 h-3.5 text-amber-500" />
                      {t('moaFeatureTitle')}
                    </span>
                    <p className="text-[11px] text-muted-foreground">{t('moaFeatureDesc')}</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'economics' && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl border border-amber-500/20 bg-amber-500/5 space-y-3">
                <div className="flex items-center gap-2 text-amber-700 dark:text-amber-300 font-semibold text-sm">
                  <Coins className="w-4 h-4" />
                  <span>{t('economicsTitle')}</span>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {t('economicsDesc')}
                </p>
                <div className="space-y-2 pt-1 text-xs text-muted-foreground">
                  <div className="flex items-start gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0 mt-1.5" />
                    <span>{t('economicsPoint1')}</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0 mt-1.5" />
                    <span>{t('economicsPoint2')}</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0 mt-1.5" />
                    <span>{t('economicsPoint3')}</span>
                  </div>
                </div>
              </div>

              <div className="p-4 rounded-xl border border-border/40 bg-muted/10 flex items-center justify-between gap-4">
                <div className="space-y-0.5">
                  <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
                    {t('externalStacksTitle')}
                  </span>
                  <p className="text-[11px] text-muted-foreground">{t('externalStacksDesc')}</p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleNavigateToSettings}
                  className="text-xs shrink-0"
                >
                  <Sliders className="w-3.5 h-3.5 mr-1" />
                  {t('advancedSettingsButton')}
                </Button>
              </div>
            </div>
          )}
        </div>

        <div className="p-4 px-6 border-t border-border/40 bg-muted/20 flex items-center justify-between">
          <button
            type="button"
            onClick={handleNavigateToSettings}
            className="text-xs font-medium text-muted-foreground hover:text-foreground inline-flex items-center gap-1 transition-colors"
          >
            <Sliders className="w-3.5 h-3.5" />
            <span>{t('openModelCenter')}</span>
            <ArrowRight className="w-3 h-3" />
          </button>
          <Button
            size="sm"
            variant="ghost"
            data-testid="playbook-close-button"
            onClick={() => onOpenChange(false)}
            className="text-xs"
          >
            {t('closeButton')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
});

ModelOrchestrationPlaybookDialog.displayName = 'ModelOrchestrationPlaybookDialog';
