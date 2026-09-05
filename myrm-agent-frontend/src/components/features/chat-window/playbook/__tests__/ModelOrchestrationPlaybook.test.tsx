import { describe, it, expect, vi } from 'vitest';
import {
  MODEL_ORCHESTRATION_RECIPES,
  resolveRecipeReadiness,
  applyOrchestrationRecipe,
  findBestModelMatch,
  type EnabledModelOption,
} from '../modelOrchestrationRecipes';

describe('modelOrchestrationRecipes', () => {
  const mockModels: EnabledModelOption[] = [
    { providerId: 'anthropic', providerName: 'Anthropic', model: 'claude-3-5-sonnet-20241022' },
    { providerId: 'deepseek', providerName: 'DeepSeek', model: 'deepseek-chat' },
    { providerId: 'deepseek', providerName: 'DeepSeek', model: 'deepseek-reasoner' },
    { providerId: 'openai', providerName: 'OpenAI', model: 'gpt-4o-mini' },
  ];

  it('defines the three golden recipes correctly', () => {
    expect(MODEL_ORCHESTRATION_RECIPES).toHaveLength(3);
    const [frugal, balanced, consensus] = MODEL_ORCHESTRATION_RECIPES;

    expect(frugal.id).toBe('frugal');
    expect(frugal.routingEnabled).toBe(false);
    expect(frugal.autoMoaReasoning).toBe(false);

    expect(balanced.id).toBe('balanced');
    expect(balanced.routingEnabled).toBe(true);
    expect(balanced.autoMoaReasoning).toBe(false);

    expect(consensus.id).toBe('consensus');
    expect(consensus.routingEnabled).toBe(true);
    expect(consensus.autoMoaReasoning).toBe(true);
  });

  describe('findBestModelMatch', () => {
    it('returns null when no enabled models are present', () => {
      expect(findBestModelMatch([], [/deepseek/i])).toBeNull();
    });

    it('matches target pattern successfully', () => {
      const match = findBestModelMatch(mockModels, [/sonnet/i]);
      expect(match).toEqual({
        providerId: 'anthropic',
        model: 'claude-3-5-sonnet-20241022',
      });
    });

    it('respects fallback exclusion to prevent brain and hands colliding when avoidable', () => {
      const exclude = { providerId: 'deepseek', model: 'deepseek-chat' };
      const match = findBestModelMatch(mockModels, [/deepseek/i, /mini/i], exclude);
      expect(match?.model).toBe('deepseek-reasoner');
    });
  });

  describe('resolveRecipeReadiness', () => {
    it('flags unreadiness when models are empty', () => {
      const recipe = MODEL_ORCHESTRATION_RECIPES[0];
      const readiness = resolveRecipeReadiness(recipe, []);
      expect(readiness.isReady).toBe(false);
      expect(readiness.missingRoleKey).toBe('noModelsEnabled');
    });

    it('resolves frugal recipe readiness with lightweight model', () => {
      const recipe = MODEL_ORCHESTRATION_RECIPES.find((r) => r.id === 'frugal');
      expect(recipe).toBeDefined();
      if (!recipe) {
        return;
      }
      const readiness = resolveRecipeReadiness(recipe, mockModels);
      expect(readiness.isReady).toBe(true);
      expect(readiness.primaryMatch?.model).toMatch(/deepseek|mini/i);
    });

    it('resolves balanced recipe readiness with both brain and hands matched', () => {
      const recipe = MODEL_ORCHESTRATION_RECIPES.find((r) => r.id === 'balanced');
      expect(recipe).toBeDefined();
      if (!recipe) {
        return;
      }
      const readiness = resolveRecipeReadiness(recipe, mockModels);
      expect(readiness.isReady).toBe(true);
      expect(readiness.reasoningMatch?.model).toContain('claude-3-5-sonnet');
      expect(readiness.lightMatch?.model).toMatch(/deepseek|mini/i);
    });

    it('resolves consensus recipe readiness with moa capability', () => {
      const recipe = MODEL_ORCHESTRATION_RECIPES.find((r) => r.id === 'consensus');
      expect(recipe).toBeDefined();
      if (!recipe) {
        return;
      }
      const readiness = resolveRecipeReadiness(recipe, mockModels);
      expect(readiness.isReady).toBe(true);
      expect(readiness.reasoningMatch).not.toBeNull();
      expect(readiness.lightMatch).not.toBeNull();
    });
  });

  describe('applyOrchestrationRecipe', () => {
    it('applies balanced recipe with atomic store actions', () => {
      const recipe = MODEL_ORCHESTRATION_RECIPES.find((r) => r.id === 'balanced');
      expect(recipe).toBeDefined();
      if (!recipe) {
        return;
      }
      const readiness = resolveRecipeReadiness(recipe, mockModels);

      const setBaseModel = vi.fn();
      const setLiteModel = vi.fn();
      const setRoutingEnabled = vi.fn();
      const setRoutingLightModel = vi.fn();
      const setRoutingReasoningModel = vi.fn();
      const setAutoMoaReasoning = vi.fn();

      const success = applyOrchestrationRecipe(recipe, readiness, {
        setBaseModel,
        setLiteModel,
        setRoutingEnabled,
        setRoutingLightModel,
        setRoutingReasoningModel,
        setAutoMoaReasoning,
      });

      expect(success).toBe(true);
      expect(setBaseModel).toHaveBeenCalledWith(readiness.primaryMatch);
      expect(setLiteModel).toHaveBeenCalledWith(readiness.lightMatch);
      expect(setRoutingEnabled).toHaveBeenCalledWith(true);
      expect(setRoutingLightModel).toHaveBeenCalledWith(readiness.lightMatch);
      expect(setRoutingReasoningModel).toHaveBeenCalledWith(readiness.reasoningMatch);
      expect(setAutoMoaReasoning).toHaveBeenCalledWith(false);
    });

    it('returns false and performs no mutations if recipe is not ready', () => {
      const recipe = MODEL_ORCHESTRATION_RECIPES.find((r) => r.id === 'balanced');
      expect(recipe).toBeDefined();
      if (!recipe) {
        return;
      }
      const unreadyReadiness = {
        isReady: false,
        primaryMatch: null,
        lightMatch: null,
        reasoningMatch: null,
      };

      const setBaseModel = vi.fn();
      const success = applyOrchestrationRecipe(recipe, unreadyReadiness, {
        setBaseModel,
        setLiteModel: vi.fn(),
        setRoutingEnabled: vi.fn(),
        setRoutingLightModel: vi.fn(),
        setRoutingReasoningModel: vi.fn(),
        setAutoMoaReasoning: vi.fn(),
      });

      expect(success).toBe(false);
      expect(setBaseModel).not.toHaveBeenCalled();
    });
  });
});
