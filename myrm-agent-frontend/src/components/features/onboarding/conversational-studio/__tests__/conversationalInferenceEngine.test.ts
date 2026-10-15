import { describe, it, expect } from 'vitest';
import {
  getRecipeByPreset,
  inferRecipeFromUserInput,
} from '../conversationalInferenceEngine';

describe('conversationalInferenceEngine', () => {
  it('returns valid preset recipe with mapped skills and model tier', () => {
    const swRecipe = getRecipeByPreset('software_eng');
    expect(swRecipe.suggestedName).toBe('全栈架构工程师');
    expect(swRecipe.recommendedModelTier).toBe('pro');
    expect(swRecipe.recommendedSkills.length).toBeGreaterThanOrEqual(3);
    expect(swRecipe.estimatedTokenSavingPct).toBe(45);

    const mktRecipe = getRecipeByPreset('marketing');
    expect(mktRecipe.suggestedName).toBe('增长与营销洞察官');
    expect(mktRecipe.recommendedModelTier).toBe('turbo');
    expect(mktRecipe.recommendedSkills.some((s) => s.id === 'skill_web_scraper')).toBe(true);

    const fallbackRecipe = getRecipeByPreset('custom');
    expect(fallbackRecipe.suggestedName).toBe('全能办公协同搭子');
  });

  it('infers software engineering recipe from natural language input', () => {
    const recipe1 = inferRecipeFromUserInput('帮我审查 Python 和 React 代码中的 bug');
    expect(recipe1.presetKey).toBe('software_eng');

    const recipe2 = inferRecipeFromUserInput('搭建全栈微服务架构并配置 git 流');
    expect(recipe2.presetKey).toBe('software_eng');
  });

  it('infers marketing recipe from natural language input', () => {
    const recipe = inferRecipeFromUserInput('监控社媒舆情，抓取竞品价格并分析转化率');
    expect(recipe.presetKey).toBe('marketing');
  });

  it('infers finance audit recipe from natural language input', () => {
    const recipe = inferRecipeFromUserInput('对账单进行发票报销验真和多表借贷核对');
    expect(recipe.presetKey).toBe('finance_audit');
  });

  it('infers administrative writing recipe from natural language input', () => {
    const recipe = inferRecipeFromUserInput('整理昨天的项目例会录音，输出格式化纪要与周报');
    expect(recipe.presetKey).toBe('admin_writing');
  });

  it('falls back to custom recipe for unrecognized intent', () => {
    const recipe = inferRecipeFromUserInput('今天天气怎么样？今天做点什么好呢？');
    expect(recipe.presetKey).toBe('custom');
  });
});
