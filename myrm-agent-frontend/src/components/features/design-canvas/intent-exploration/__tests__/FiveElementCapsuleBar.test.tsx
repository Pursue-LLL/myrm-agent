import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FiveElementCapsuleBar } from '../FiveElementCapsuleBar';
import { useDesignIntentStore } from '../useDesignIntentStore';

describe('FiveElementCapsuleBar', () => {
  beforeEach(() => {
    useDesignIntentStore.getState().reset();
  });

  it('renders all five element labels and completeness score', () => {
    render(<FiveElementCapsuleBar />);

    expect(screen.getByText('意图五要素:')).toBeInTheDocument();
    expect(screen.getByText('做什么:')).toBeInTheDocument();
    expect(screen.getByText('给谁看:')).toBeInTheDocument();
    expect(screen.getByText('什么风格:')).toBeInTheDocument();
    expect(screen.getByText('内容清单:')).toBeInTheDocument();
    expect(screen.getByText('尺寸用途:')).toBeInTheDocument();

    expect(screen.getByText(/完整度/)).toBeInTheDocument();
  });

  it('opens quick options menu on capsule click and selects an option', () => {
    render(<FiveElementCapsuleBar />);

    // 点击"给谁看"胶囊
    const audienceBtn = screen.getByTitle(/给谁看/);
    fireEvent.click(audienceBtn);

    // 应该弹出选项"年轻都市白领"
    const option = screen.getByText('年轻都市白领');
    expect(option).toBeInTheDocument();

    // 点击选择该选项
    fireEvent.click(option);

    expect(useDesignIntentStore.getState().currentSpec.audience.value).toBe('年轻都市白领');
    expect(useDesignIntentStore.getState().activeCapsuleKey).toBeNull();
  });

  it('triggers prompt refinement on refine button click', () => {
    render(<FiveElementCapsuleBar />);

    const refineBtn = screen.getByText('升华提示词');
    fireEvent.click(refineBtn);

    expect(useDesignIntentStore.getState().draftPrompt).toContain('请设计制作一份专业的');
  });

  it('triggers 3-direction divergence modal on click', () => {
    render(<FiveElementCapsuleBar />);

    const generateBtn = screen.getByText('铺开 3 个方向初稿');
    fireEvent.click(generateBtn);

    expect(useDesignIntentStore.getState().isExplorationOpen).toBe(true);
    expect(useDesignIntentStore.getState().variants.length).toBe(3);
  });
});
