export type DisclosureTier = 'minimal' | 'standard' | 'expert';

export type ServiceCategory =
  | 'model_gateway'
  | 'sandbox'
  | 'skill_mesh'
  | 'mcp_bridge'
  | 'vector_memory';

export interface SilentServiceItem {
  id: string;
  name: string;
  category: ServiceCategory;
  isReady: boolean;
  latencyMs: number;
  description: string;
}

export interface SilencedNotice {
  id: string;
  title: string;
  source: string;
  severity: 'info' | 'warning';
  timestamp: string;
  details?: string;
  actionLabel?: string;
}

export interface ProgressiveBootState {
  tier: DisclosureTier;
  isDrawerOpen: boolean;
  services: SilentServiceItem[];
  silencedNotices: SilencedNotice[];
  bootCompletedAt: string;

  setDisclosureTier: (tier: DisclosureTier) => void;
  toggleDrawer: (open?: boolean) => void;
  suppressBlockingModal: (notice: Omit<SilencedNotice, 'id' | 'timestamp'>) => string;
  dismissNotice: (id: string) => void;
  updateServiceStatus: (serviceId: string, isReady: boolean, latencyMs: number) => void;
  resetBootState: () => void;
}
