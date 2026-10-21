import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { KeyboardSensor, TouchSensor, type TouchSensorOptions } from '@dnd-kit/core';
import { useKanbanDnD } from '../useKanbanDnD';
import { ISOLATE_FROM_CARD } from '../kanban-card-gestures';

// 真实 dnd-kit 传感器（不 mock）：隔离属性与传感器激活事件的对应关系只能靠真实配置核对。
function boardSensors() {
  const { result } = renderHook(() =>
    useKanbanDnD({ tasks: [], selectedTaskIds: [], onMoveTask: vi.fn(), onMoveBlocked: vi.fn() }),
  );
  return result.current.sensors;
}

describe('card gesture isolation vs board sensors', () => {
  it('stops the activation event of every pointer-like sensor', () => {
    // 键盘传感器只在卡片自身被聚焦时激活，卡片内控件的按键不会触发，所以不在隔离范围内。
    const activationEvents = boardSensors()
      .filter(({ sensor }) => sensor !== KeyboardSensor)
      .flatMap(({ sensor }) => sensor.activators.map(({ eventName }) => eventName));

    expect(activationEvents.length).toBeGreaterThan(0);
    for (const eventName of activationEvents) {
      expect(ISOLATE_FROM_CARD).toHaveProperty(eventName);
    }
  });

  it('starts a touch drag only after a long press so a swipe on a card scrolls the board', () => {
    const sensors = boardSensors();
    // useSensors 抹掉了各传感器的选项类型，这里按 TouchSensor 的选项读回长按约束。
    const touchOptions = sensors.find(({ sensor }) => sensor === TouchSensor)?.options as
      TouchSensorOptions | undefined;
    const activationEvents = sensors.flatMap(({ sensor }) => sensor.activators.map(({ eventName }) => eventName));

    expect(touchOptions?.activationConstraint).toMatchObject({ delay: expect.any(Number) });
    // 监听 onPointerDown 的传感器（PointerSensor）同样接管触屏指针，位移到阈值就起拖拽，长按约束形同虚设。
    expect(activationEvents).not.toContain('onPointerDown');
  });
});
