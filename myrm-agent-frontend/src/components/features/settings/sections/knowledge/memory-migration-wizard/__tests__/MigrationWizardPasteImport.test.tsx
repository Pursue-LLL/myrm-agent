/** @vitest-environment jsdom */
/**
 * [INPUT]
 * ../ScanStep (POS: 迁移向导扫描步骤)
 * ./wizardTestKit (POS: 迁移向导测试共用夹具)
 *
 * [OUTPUT]
 * 粘贴导入通道回归测试。
 *
 * [POS]
 * 迁移向导粘贴通道测试。断言粘贴文本转发给父组件并可请求预览、无内容时预览按钮禁用、
 * 体积提示可见、模型整理开关默认关闭且切换会上报、导出提示词为真实文案。
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ScanStep } from '../ScanStep';
import { t } from './wizardTestKit';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));

const renderScan = (overrides: Partial<Parameters<typeof ScanStep>[0]> = {}) => {
  const props: Parameters<typeof ScanStep>[0] = {
    discovery: null,
    scanning: false,
    uploading: false,
    previewing: false,
    previewingSource: null,
    includeEpisodic: true,
    onIncludeEpisodicChange: vi.fn(),
    agents: [],
    targetAgentId: null,
    onTargetAgentIdChange: vi.fn(),
    onScan: vi.fn(),
    onUpload: vi.fn(),
    onPreview: vi.fn(),
    pasteText: '',
    pasting: false,
    pasteModelExtraction: false,
    onPasteTextChange: vi.fn(),
    onPasteModelExtractionChange: vi.fn(),
    onPastePreview: vi.fn(),
    t,
    ...overrides,
  };
  render(<ScanStep {...props} />);
  return props;
};

describe('migration wizard paste lane', () => {
  afterEach(cleanup);

  it('forwards pasted text and requests a preview', () => {
    const props = renderScan({ pasteText: '## FACTS\n- Uses Postgres' });

    fireEvent.change(screen.getByTestId('migration-paste-textarea'), { target: { value: '## RULES\n- Answer short' } });
    expect(props.onPasteTextChange).toHaveBeenCalledWith('## RULES\n- Answer short');

    const previewButton = screen.getByRole('button', { name: /Parse and preview/ });
    expect(previewButton).toBeEnabled();
    fireEvent.click(previewButton);
    expect(props.onPastePreview).toHaveBeenCalledTimes(1);
  });

  it('keeps model-assisted extraction opt-in and reports the choice', () => {
    const props = renderScan();
    const toggle = screen.getByTestId('migration-paste-model-toggle');

    expect(toggle).not.toBeChecked();
    expect(
      screen.getByText(
        'The text goes to the model configured for this agent; the result still needs your review before anything is saved.',
      ),
    ).toBeInTheDocument();

    fireEvent.click(toggle);
    expect(props.onPasteModelExtractionChange).toHaveBeenCalledWith(true);
  });

  it('states the paste size budget next to the textarea', () => {
    renderScan();

    expect(
      screen.getByText('Up to 4 MB per paste. Longer exports can be split into several pastes.'),
    ).toBeInTheDocument();
  });

  it('keeps the preview action disabled while nothing is pasted', () => {
    renderScan();

    expect(screen.getByRole('button', { name: /Parse and preview/ })).toBeDisabled();
  });

  it('copies the real export prompt for assistants without an export package', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    renderScan();

    fireEvent.click(screen.getByRole('button', { name: /Copy export prompt/ }));

    expect(writeText).toHaveBeenCalledTimes(1);
    expect(writeText.mock.calls[0][0]).toContain('## RULES');
    expect(writeText.mock.calls[0][0]).toContain('## PREFERENCES');
  });
});
