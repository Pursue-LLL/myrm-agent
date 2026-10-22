/**
 * [INPUT]
 * - None (pure TypeScript type definitions)
 *
 * [OUTPUT]
 * - WidgetNetworkPolicy, PinnedWidget, PosterTheme, PosterExportOptions, PinnedDashboardDrawerProps, WidgetPosterExportModalProps
 *
 * [POS]
 * Domain types for Interactive Widget Dashboard Pinning and Snapshot Export (Item 48 P0).
 * Strictly under 80 lines. Zero `any`.
 */

export type WidgetNetworkPolicy = 'none' | 'restricted' | 'full';

export type PosterTheme =
  | 'minimal_slate'
  | 'cyber_purple'
  | 'emerald_pro'
  | 'amber_sunset';

export interface PinnedWidget {
  id: string;
  artifactId: string;
  title: string;
  type: string;
  content: string;
  pinnedAt: number;
  chatId?: string;
  networkPolicy: WidgetNetworkPolicy;
}

export interface PosterExportOptions {
  theme: PosterTheme;
  title: string;
  author?: string;
  showTimestamp?: boolean;
  watermark?: string;
}

export interface PinnedDashboardDrawerProps {
  chatId?: string;
  isOpen: boolean;
  onClose: () => void;
  className?: string;
  onExportPoster?: (widget: PinnedWidget) => void;
}

export interface WidgetPosterExportModalProps {
  widget: PinnedWidget | null;
  isOpen: boolean;
  onClose: () => void;
  className?: string;
  onDownloadSuccess?: () => void;
}
