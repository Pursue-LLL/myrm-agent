import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  MODEL_ORCHESTRATION_RECIPES,
  resolveRecipeReadiness,
  applyOrchestrationRecipe,
  type EnabledModelOption,
} from '../modelOrchestrationRecipes';

describe('ModelOrchestrationRecipes Engine', () => {
  const mockModels: EnabledModelOption[] = [
    { providerId: 'anthropic', providerName: 'Anthropic', model: 'claude-3-5-sonnet-20241022' },
    { providerId: 'deepseek', providerName: 'DeepSeek', model: 'deepseek-chat' },
    { providerId: 'deepseek', providerName: 'DeepSeek', model: 'deepseek-reasoner' },
    { providerId: 'openai', providerName: 'OpenAI', model: 'gpt-4o-mini' },
  ];

  it('correctly resolves readiness for frugal recipe', () => {
    const frugalRecipe = MODEL_ORCHESTRATION_RECIPES.find((r) => r.id === 'frugal')!;
    const readiness = resolveRecipeReadiness(frugalRecipe, mockModels);

    expect(readiness.isReady).toBe(true);
    expect(readiness.primaryMatch).toBeDefined();
    expect(readiness.primaryMatch?.model).toMatch(/deepseek|mini|flash|qwen/i);
  });

  it('correctly resolves readiness for balanced brain & hands recipe', () => {
    const balancedRecipe = MODEL_ORCHESTRATION_RECIPES.find((r) => r.id === 'balanced')!;
    const readiness = resolveRecipeReadiness(balancedRecipe, mockModels);

    expect(readiness.isReady).toBe(true);
    expect(readiness.primaryMatch?.model).toBe('claude-3-5-sonnet-20241022');
    expect(readiness.lightMatch?.model).toMatch(/deepseek|mini/i);
    expect(readiness.primaryMatch?.model).not.toBe(readiness.lightMatch?.model);
  });

  it('handles missing models gracefully', () => {
    const balancedRecipe = MODEL_ORCHESTRATION_RECIPES.find((r) => r.id === 'balanced')!;
    const readiness = resolveRecipeReadiness(balancedRecipe, []);

    expect(readiness.isReady).toBe(false);
    expect(readiness.primaryMatch).toBeNull();
    expect(readiness.missingRoleKey).toBe('noModelsEnabled');
  });

  it('correctly dispatches state updates when applying a recipe', () => {
    const balancedRecipe = MODEL_ORCHESTRATION_RECIPES.find((r) => r.id === 'balanced')!;
    const readiness = resolveRecipeReadiness(balancedRecipe, mockModels);

    const setBaseModel = vi.fn();
    const setLiteModel = vi.fn();
    const setRoutingEnabled = vi.fn();
    const setRoutingLightModel = vi.fn();
    const setRoutingReasoningModel = vi.fn();
    const setAutoMoaReasoning = vi.fn();

    const success = applyOrchestrationRecipe(balancedRecipe, readiness, {
      setBaseModel,
      setLiteModel,
      setRoutingEnabled,
      setRoutingLightModel,
      setRoutingReasoningModel,
      setAutoMoaReasoning,
    });

    expect(success).toBe(true);
    expect(setBaseModel).toHaveBeenCalledWith({
      providerId: 'anthropic',
      model: 'claude-3-5-sonnet-20241022',
    });
    expect(setRoutingEnabled).toHaveBeenCalledWith(true);
    expect(setRoutingLightModel).toHaveBeenCalled();
    expect(setAutoMoaReasoning).toHaveBeenCalledWith(false);
  });
});
