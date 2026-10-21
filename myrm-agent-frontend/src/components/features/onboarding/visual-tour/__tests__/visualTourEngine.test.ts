import { describe, it, expect } from 'vitest';
import {
  calculateChecklistProgress,
  calculateSpotlightRect,
  buildSandboxExecutionPayload,
  getNextStepIndex,
  getPrevStepIndex,
  DEFAULT_TOUR_STEPS,
  DEFAULT_CHECKLIST_ITEMS,
  DEFAULT_PLAYGROUND_TEMPLATES,
} from '../visualTourEngine';
import type { ChecklistItem } from '../visualTourTypes';

describe('visualTourEngine', () => {
  it('应包含完备的默认引导步骤、新手核对项与场景模板', () => {
    expect(DEFAULT_TOUR_STEPS.length).toBeGreaterThanOrEqual(4);
    expect(DEFAULT_CHECKLIST_ITEMS.length).toBeGreaterThanOrEqual(3);
    expect(DEFAULT_PLAYGROUND_TEMPLATES.length).toBeGreaterThanOrEqual(3);

    const firstStep = DEFAULT_TOUR_STEPS[0];
    expect(firstStep).toBeDefined();
    if (firstStep) {
      expect(firstStep.id).toBe('agent-switcher');
      expect(firstStep.targetSelector).toBe('[data-tour="agent-switcher"]');
    }
  });

  describe('calculateSpotlightRect', () => {
    it('当传入 null 或空元素时应安全返回 null', () => {
      const rect = calculateSpotlightRect(null);
      expect(rect).toBeNull();
    });

    it('当传入正常 DOM 元素时应正确计算位置与尺寸', () => {
      const fakeElement = {
        getBoundingClientRect: () => {
          return {
            top: 120.4,
            left: 240.6,
            width: 300.2,
            height: 80.1,
            bottom: 200.5,
            right: 540.8,
            x: 240.6,
            y: 120.4,
            toJSON: () => {
              return {};
            },
          };
        },
      } as unknown as Element;

      const rect = calculateSpotlightRect(fakeElement);
      expect(rect).toBeDefined();
      if (rect) {
        expect(rect.top).toBe(120);
        expect(rect.left).toBe(241);
        expect(rect.width).toBe(300);
        expect(rect.height).toBe(80);
      }
    });
  });

  describe('calculateChecklistProgress', () => {
    it('空列表时应返回 100% 完成度', () => {
      const progress = calculateChecklistProgress([]);
      expect(progress.completedCount).toBe(0);
      expect(progress.totalCount).toBe(0);
      expect(progress.percentage).toBe(100);
      expect(progress.isAllCompleted).toBe(true);
    });

    it('部分完成与全部完成时应正确计算百分比', () => {
      const mockItems: ChecklistItem[] = [
        { id: '1', title: 'Task 1', description: 'Desc 1', completed: true, required: true },
        { id: '2', title: 'Task 2', description: 'Desc 2', completed: false, required: true },
        { id: '3', title: 'Task 3', description: 'Desc 3', completed: false, required: false },
      ];

      const partialProgress = calculateChecklistProgress(mockItems);
      expect(partialProgress.completedCount).toBe(1);
      expect(partialProgress.totalCount).toBe(3);
      expect(partialProgress.percentage).toBe(33);
      expect(partialProgress.isAllCompleted).toBe(false);

      const allCompletedItems: ChecklistItem[] = mockItems.map((item) => {
        return { ...item, completed: true };
      });
      const fullProgress = calculateChecklistProgress(allCompletedItems);
      expect(fullProgress.completedCount).toBe(3);
      expect(fullProgress.totalCount).toBe(3);
      expect(fullProgress.percentage).toBe(100);
      expect(fullProgress.isAllCompleted).toBe(true);
    });
  });

  describe('buildSandboxExecutionPayload', () => {
    it('应正确组装带有附加环境变量与上下文标签的沙盒指令载荷', () => {
      const template = DEFAULT_PLAYGROUND_TEMPLATES[0];
      expect(template).toBeDefined();
      if (template) {
        const payload = buildSandboxExecutionPayload(template, {
          targetIndustry: '企业级协同 SaaS',
        });

        expect(payload.templateId).toBe(template.id);
        expect(payload.tags).toEqual(template.tags);
        expect(payload.prompt).toContain(template.prompt);
        expect(payload.prompt).toContain('[附加上下文 targetIndustry]: 企业级协同 SaaS');
        expect(payload.initialParams.targetIndustry).toBe('企业级协同 SaaS');
      }
    });
  });

  describe('getNextStepIndex & getPrevStepIndex', () => {
    it('应安全进行边界受控的索引递增与递减', () => {
      expect(getNextStepIndex(0, 4)).toBe(1);
      expect(getNextStepIndex(3, 4)).toBe(3);
      expect(getNextStepIndex(0, 0)).toBe(0);

      expect(getPrevStepIndex(2)).toBe(1);
      expect(getPrevStepIndex(0)).toBe(0);
    });
  });
});
