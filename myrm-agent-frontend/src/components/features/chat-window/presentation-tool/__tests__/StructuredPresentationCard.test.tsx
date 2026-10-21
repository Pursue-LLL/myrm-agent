import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PresentationPayload } from '../presentationToolTypes';
import { StructuredPresentationCard } from '../StructuredPresentationCard';
import { usePresentationToolStore } from '../usePresentationToolStore';

describe('StructuredPresentationCard', () => {
  beforeEach(() => {
    usePresentationToolStore.getState().reset();
  });

  const mockProductPresentation: PresentationPayload = {
    id: 'pres-product-test',
    toolName: 'present_products',
    title: '精选智能硬件比价',
    description: '基于您提出的续航与算力需求筛选得出',
    createdAt: Date.now(),
    items: [
      {
        id: 'prod-1',
        title: 'M4 Max 移动工作站',
        subtitle: '128GB 统一内存 · 2TB SSD',
        highlight: '极致本地推理速度',
        position: 1,
      },
      {
        id: 'prod-2',
        title: 'RTX 4090 深度学习主机',
        subtitle: '24GB 显存 · 水冷散热',
        highlight: '性价比高算力之选',
        position: 2,
      },
    ],
  };

  it('renders card title, description, and product items accurately', () => {
    render(<StructuredPresentationCard presentation={mockProductPresentation} />);

    expect(
      screen.getByTestId('structured-presentation-card-pres-product-test'),
    ).toBeDefined();
    expect(screen.getByText('精选智能硬件比价')).toBeDefined();
    expect(
      screen.getByText('基于您提出的续航与算力需求筛选得出'),
    ).toBeDefined();
    expect(screen.getByText('展示工具原生契约')).toBeDefined();
    expect(screen.getByText('2 项')).toBeDefined();

    expect(screen.getByText('M4 Max 移动工作站')).toBeDefined();
    expect(screen.getByText('128GB 统一内存 · 2TB SSD')).toBeDefined();
    expect(screen.getByText('极致本地推理速度')).toBeDefined();
    expect(screen.getByText('1')).toBeDefined();
    expect(screen.getByText('2')).toBeDefined();
  });

  it('handles item click and invokes onItemSelected callback', () => {
    const onSelect = vi.fn();
    render(
      <StructuredPresentationCard
        presentation={mockProductPresentation}
        onItemSelected={onSelect}
      />,
    );

    const firstItem = screen.getByText('M4 Max 移动工作站');
    fireEvent.click(firstItem);

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(mockProductPresentation.items[0]);
  });

  it('renders positional selection badge when store item matches', () => {
    const targetItem = mockProductPresentation.items[1];
    expect(targetItem).toBeDefined();
    if (targetItem) {
      usePresentationToolStore.setState({
        selectedPositionalItem: {
          presentationId: 'pres-product-test',
          item: targetItem,
        },
      });
    }

    render(<StructuredPresentationCard presentation={mockProductPresentation} />);

    expect(screen.getByText('已选中指代')).toBeDefined();
  });

  it('renders itinerary tool format correctly', () => {
    const mockItinerary: PresentationPayload = {
      id: 'pres-itinerary-test',
      toolName: 'present_itinerary',
      title: '工作区四区整理分步计划',
      createdAt: Date.now(),
      items: [
        {
          step: 1,
          title: '原件隔离只读保护',
          description: '将所有发票与合同归入 01 分区',
          position: 1,
        },
      ],
    };

    render(<StructuredPresentationCard presentation={mockItinerary} />);

    expect(screen.getByText('工作区四区整理分步计划')).toBeDefined();
    expect(screen.getByText('原件隔离只读保护')).toBeDefined();
    expect(
      screen.getByText('将所有发票与合同归入 01 分区'),
    ).toBeDefined();
  });
});
