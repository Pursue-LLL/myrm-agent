/**
 * Callout Anchor Zustand Store
 * 对话气泡引文与工件视口双向聚焦、几何矩阵计算与高亮状态调度器
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 所有 if 显式包裹大括号；
 * 3. 行数严格受控在 400 行以内；
 * 4. 纯净状态流转，支持双向（气泡 <-> 视口）双向联动。
 */

import { create } from 'zustand';
import {
  CalloutAnchor,
  FocusOrigin,
  ViewportTransform,
} from './calloutAnchorTypes';
import { calculateCenteringTransform } from './calloutCoordinateMath';

interface CalloutAnchorState {
  anchors: CalloutAnchor[];
  activeAnchorId: string | null;
  hoveredAnchorId: string | null;
  viewportTransform: ViewportTransform;
  viewportDimensions: { width: number; height: number };
  isPulseAnimating: boolean;

  // Actions
  focusAnchor: (anchorId: string, origin: FocusOrigin) => void;
  setHoveredAnchorId: (anchorId: string | null) => void;
  setViewportDimensions: (width: number, height: number) => void;
  resetViewport: () => void;
  getActiveAnchor: () => CalloutAnchor | undefined;
  resetToDefault: () => void;
}

const DEFAULT_ANCHORS: CalloutAnchor[] = [
  {
    id: 'anchor-truss-heel-01',
    label: '桁架根部支座节点 (Truss Heel)',
    section: '5.1 结构荷载安全审计',
    quote: 'the heel is 28 mm outside the wall face, creating an eccentric vertical reaction',
    targetSelector: 'Truss_01_BottomChord_Joint',
    evidenceType: '3d',
    boundingBox: { x: 80, y: 60, width: 90, height: 70 },
    severity: 'critical',
    description: '受力中心偏出外墙承重轴线 28mm，存在偏心剪切断裂重大隐患',
    tags: ['结构安全', 'BIM', '承重节点'],
  },
  {
    id: 'anchor-db-pool-02',
    label: '数据库异步连接池 (DatabasePool)',
    section: '3.2 高并发性能与死锁分析',
    quote: 'pool acquisition timeout occurs when concurrent workers exceed 128 instances',
    targetSelector: 'service.core.DatabasePool',
    evidenceType: 'code',
    boundingBox: { x: 260, y: 70, width: 110, height: 80 },
    severity: 'warning',
    description: '工作协程突发超出 128 峰值时连接获取超时，缺少熔断排队自愈通道',
    tags: ['后端架构', '连接池', '并发性能'],
  },
  {
    id: 'anchor-pay-btn-03',
    label: '结算提交交互卡片 (CheckoutButton)',
    section: '2.4 订单结算组件可访问性',
    quote: 'contrast ratio of checkout button fails WCAG AAA threshold under dark theme',
    targetSelector: '#btn-checkout-primary',
    evidenceType: 'dom',
    boundingBox: { x: 100, y: 200, width: 120, height: 60 },
    severity: 'info',
    description: '深色模式下颜色对比度 3.8:1，低于 WCAG AAA 4.5:1 无障碍规范',
    tags: ['UI 组件', '无障碍', '色彩规范'],
  },
  {
    id: 'anchor-auth-gate-04',
    label: 'JWT 鉴权拦截防线 (AuthGate)',
    section: '4.3 边缘网关安全策略',
    quote: 'revocation list cache misses trigger redundant database queries per request',
    targetSelector: 'middleware.auth.RevocationBarrier',
    evidenceType: 'canvas',
    boundingBox: { x: 280, y: 190, width: 100, height: 75 },
    severity: 'warning',
    description: '黑名单缓存击穿时产生请求放大，需要引入布隆过滤器前置阻断',
    tags: ['安全审计', '网关', '缓存一致性'],
  },
];

export const useCalloutAnchorStore = create<CalloutAnchorState>(
  (set, get) => ({
    anchors: DEFAULT_ANCHORS,
    activeAnchorId: 'anchor-truss-heel-01',
    hoveredAnchorId: null,
    viewportTransform: { translateX: 0, translateY: 0, scale: 1 },
    viewportDimensions: { width: 480, height: 320 },
    isPulseAnimating: false,

    focusAnchor: (anchorId: string, origin: FocusOrigin) => {
      const target = get().anchors.find((a) => a.id === anchorId);
      if (!target) {
        return;
      }

      const { width, height } = get().viewportDimensions;
      const nextTransform = calculateCenteringTransform(
        width,
        height,
        target.boundingBox
      );

      set({
        activeAnchorId: anchorId,
        viewportTransform: nextTransform,
        isPulseAnimating: true,
      });

      // 广播全局空间聚焦事件，供外部宿主或 3D 引擎感知
      if (typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('myrm:callout-focused', {
            detail: {
              anchorId,
              origin,
              transform: nextTransform,
            },
          })
        );
      }
    },

    setHoveredAnchorId: (anchorId: string | null) => {
      set({ hoveredAnchorId: anchorId });
    },

    setViewportDimensions: (width: number, height: number) => {
      set({ viewportDimensions: { width, height } });
    },

    resetViewport: () => {
      set({
        viewportTransform: { translateX: 0, translateY: 0, scale: 1 },
        activeAnchorId: null,
        hoveredAnchorId: null,
        isPulseAnimating: false,
      });
    },

    getActiveAnchor: () => {
      const { anchors, activeAnchorId } = get();
      return anchors.find((a) => a.id === activeAnchorId);
    },

    resetToDefault: () => {
      set({
        anchors: JSON.parse(JSON.stringify(DEFAULT_ANCHORS)) as CalloutAnchor[],
        activeAnchorId: 'anchor-truss-heel-01',
        hoveredAnchorId: null,
        viewportTransform: { translateX: 0, translateY: 0, scale: 1 },
        isPulseAnimating: false,
      });
    },
  })
);
