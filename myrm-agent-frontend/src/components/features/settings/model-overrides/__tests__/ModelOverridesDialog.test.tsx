/** @vitest-environment jsdom */
import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { ModelOverridesDialog } from '../ModelOverridesDialog';
import { ModelOverridesService } from '../modelOverridesService';

const stableT = (key: string) => {
  const table: Record<string, string> = {
    title: '模型 Context 与价格自定义管理',
    hermesParity: '对标 Hermes v0.21.0 model_overrides · 实时热生效',
    cloneTemplate: '2026 主流新模型 SKU 预置模板（点击一键克隆）:',
    modelIdLabel: '目标模型 ID / 别名',
    currencyLabel: '计费币种',
    contextWindowLabel: 'Context Window (tokens)',
    maxOutputLabel: 'Max Output Tokens (输出上限)',
    inputPriceLabel: '输入单价 (每 1M tokens)',
    outputPriceLabel: '输出单价 (每 1M tokens)',
    calcTitle: 'BYOK 实时用量与成本计算器',
    calcInputTokens: '预估输入 Tokens',
    calcOutputTokens: '预估输出 Tokens',
    calcComputeBtn: '计算单次费用',
    activeOverrides: '已保存的模型覆写列表:',
    loadToForm: '加载编辑',
    close: '关闭',
    saveAndApply: '保存并实时生效',
  };
  return table[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('ModelOverridesDialog', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = render(<ModelOverridesDialog isOpen={false} onClose={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders dialog elements, form controls, and calculator when open', async () => {
    vi.spyOn(ModelOverridesService, 'listOverrides').mockResolvedValueOnce([]);
    vi.spyOn(ModelOverridesService, 'getPreloadedSkus').mockResolvedValueOnce([
      {
        model_id: 'glm-5.3-flash',
        display_name: 'GLM-5.3 Flash',
        provider: 'Zhipu AI',
        default_context_window: 131072,
        default_max_output_tokens: 8192,
        suggested_input_cost_per_mtoken: 0.1,
        suggested_output_cost_per_mtoken: 0.1,
        currency: 'CNY',
        recommended_use_case: '高速工具编排',
      },
    ]);

    await act(async () => {
      render(<ModelOverridesDialog isOpen={true} onClose={vi.fn()} />);
    });

    expect(screen.getByTestId('model-overrides-dialog')).toBeInTheDocument();
    expect(screen.getByText('模型 Context 与价格自定义管理')).toBeInTheDocument();
    expect(screen.getByTestId('clone-sku-glm-5.3-flash')).toBeInTheDocument();
    expect(screen.getByTestId('input-model-id')).toBeInTheDocument();
    expect(screen.getByTestId('slider-context-window')).toBeInTheDocument();
    expect(screen.getByTestId('input-max-output')).toBeInTheDocument();
    expect(screen.getByTestId('input-price-input')).toBeInTheDocument();
    expect(screen.getByTestId('output-price-input')).toBeInTheDocument();
    expect(screen.getByTestId('save-override-btn')).toBeInTheDocument();
  });

  it('clones preloaded SKU parameters into form when template clicked', async () => {
    vi.spyOn(ModelOverridesService, 'listOverrides').mockResolvedValueOnce([]);
    vi.spyOn(ModelOverridesService, 'getPreloadedSkus').mockResolvedValueOnce([
      {
        model_id: 'qwen-3.8-max',
        display_name: 'Qwen 3.8 Max',
        provider: 'Alibaba Cloud',
        default_context_window: 131072,
        default_max_output_tokens: 16384,
        suggested_input_cost_per_mtoken: 0.4,
        suggested_output_cost_per_mtoken: 1.2,
        currency: 'CNY',
        recommended_use_case: '深度推理',
      },
    ]);

    await act(async () => {
      render(<ModelOverridesDialog isOpen={true} onClose={vi.fn()} />);
    });

    const cloneBtn = screen.getByTestId('clone-sku-qwen-3.8-max');
    await act(async () => {
      fireEvent.click(cloneBtn);
    });

    const modelInput = screen.getByTestId('input-model-id') as HTMLInputElement;
    expect(modelInput.value).toBe('qwen-3.8-max');
  });

  it('saves custom override configuration and triggers onSaved callback', async () => {
    const onSavedMock = vi.fn();
    vi.spyOn(ModelOverridesService, 'listOverrides').mockResolvedValueOnce([]);
    vi.spyOn(ModelOverridesService, 'getPreloadedSkus').mockResolvedValueOnce([]);
    vi.spyOn(ModelOverridesService, 'upsertOverride').mockResolvedValueOnce({
      model_id: 'custom-glm-5',
      custom_context_window: 1000000,
      custom_max_output_tokens: 8192,
      input_cost_per_mtoken: 0.1,
      output_cost_per_mtoken: 0.2,
      currency: 'USD',
      enabled: true,
      remarks: 'Saved remark',
    });

    await act(async () => {
      render(<ModelOverridesDialog isOpen={true} onClose={vi.fn()} onSaved={onSavedMock} />);
    });

    const modelInput = screen.getByTestId('input-model-id');
    await act(async () => {
      fireEvent.change(modelInput, { target: { value: 'custom-glm-5' } });
    });

    const saveBtn = screen.getByTestId('save-override-btn');
    await act(async () => {
      fireEvent.click(saveBtn);
    });

    expect(ModelOverridesService.upsertOverride).toHaveBeenCalledWith(
      'custom-glm-5',
      expect.objectContaining({
        custom_context_window: expect.any(Number),
        currency: 'USD',
      }),
    );
    expect(onSavedMock).toHaveBeenCalledTimes(1);
  });

  it('calculates BYOK real-time cost and displays summary', async () => {
    vi.spyOn(ModelOverridesService, 'listOverrides').mockResolvedValueOnce([]);
    vi.spyOn(ModelOverridesService, 'getPreloadedSkus').mockResolvedValueOnce([]);
    vi.spyOn(ModelOverridesService, 'estimateCost').mockResolvedValueOnce({
      model_id: 'glm-5.3-flash',
      input_tokens: 200000,
      output_tokens: 50000,
      input_cost: 0.02,
      output_cost: 0.01,
      total_cost: 0.03,
      currency: 'USD',
      is_overridden: true,
    });

    await act(async () => {
      render(<ModelOverridesDialog isOpen={true} onClose={vi.fn()} />);
    });

    const computeBtn = screen.getByTestId('calc-estimate-btn');
    await act(async () => {
      fireEvent.click(computeBtn);
    });

    expect(ModelOverridesService.estimateCost).toHaveBeenCalled();
    expect(screen.getByTestId('calc-result-panel')).toBeInTheDocument();
    expect(screen.getByText('$0.03')).toBeInTheDocument();
  });

  it('deletes existing override when trash button clicked', async () => {
    vi.spyOn(ModelOverridesService, 'listOverrides').mockResolvedValueOnce([
      {
        model_id: 'to-delete-model',
        custom_context_window: 500000,
        custom_max_output_tokens: 4096,
        input_cost_per_mtoken: 0.1,
        output_cost_per_mtoken: 0.2,
        currency: 'USD',
        enabled: true,
        remarks: null,
      },
    ]);
    vi.spyOn(ModelOverridesService, 'getPreloadedSkus').mockResolvedValueOnce([]);
    vi.spyOn(ModelOverridesService, 'deleteOverride').mockResolvedValueOnce(true);

    await act(async () => {
      render(<ModelOverridesDialog isOpen={true} onClose={vi.fn()} />);
    });

    const deleteBtn = screen.getByTestId('delete-override-to-delete-model');
    await act(async () => {
      fireEvent.click(deleteBtn);
    });

    expect(ModelOverridesService.deleteOverride).toHaveBeenCalledWith('to-delete-model');
  });

  it('triggers onClose when close button is clicked', async () => {
    const onCloseMock = vi.fn();
    await act(async () => {
      render(<ModelOverridesDialog isOpen={true} onClose={onCloseMock} />);
    });

    const closeBtn = screen.getByTestId('close-overrides-dialog');
    fireEvent.click(closeBtn);
    expect(onCloseMock).toHaveBeenCalledTimes(1);
  });
});
