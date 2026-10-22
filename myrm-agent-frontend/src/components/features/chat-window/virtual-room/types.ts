export type ParticipantRole = 'human' | 'local_agent' | 'borrowed_agent';
export type LockScopeType = 'file_full' | 'line_range';

export interface RoomParticipant {
  id: string;
  name: string;
  role: ParticipantRole;
  avatar?: string;
  status: 'online' | 'busy' | 'idle';
  activeFile?: string;
  borrowedFrom?: string;
  grantId?: string;
}

export interface VfsLockItem {
  lockId: string;
  filePath: string;
  scope: LockScopeType;
  lineStart?: number;
  lineEnd?: number;
  holderId: string;
  holderName: string;
  holderRole: ParticipantRole;
  acquiredAt: string;
  ttlSecondsRemaining: number;
}

export interface BorrowingGrantItem {
  grantId: string;
  ownerId: string;
  ownerName: string;
  borrowerId: string;
  borrowerName: string;
  targetAgentName: string;
  allocatedTokens: number;
  usedTokens: number;
  maxExecutions: number;
  currentExecutions: number;
  status: 'active' | 'exhausted' | 'revoked';
}

export interface PortRelayItem {
  relayId: string;
  port: number;
  serviceName: string;
  protocol: 'http' | 'ws';
  publicUrl: string;
  latencyMs: number;
  activeConnections: number;
  isHealthy: boolean;
}

export interface VirtualRoomCoDevCockpitCardProps {
  chatId?: string;
  roomId?: string;
  roomName?: string;
  onDismiss?: () => void;
  onLockAcquired?: (lock: VfsLockItem) => void;
}

export const INITIAL_PARTICIPANTS: RoomParticipant[] = [
  {
    id: 'user-lead',
    name: 'Alice (Architect)',
    role: 'human',
    status: 'online',
    activeFile: 'src/core/vfs.rs',
  },
  {
    id: 'agent-local-1',
    name: 'CodeCraft (Local)',
    role: 'local_agent',
    status: 'busy',
    activeFile: 'src/services/payment.ts',
  },
  {
    id: 'agent-borrowed-1',
    name: 'DeepSeek-V3 Auditor',
    role: 'borrowed_agent',
    status: 'online',
    activeFile: 'src/auth/jwt.ts',
    borrowedFrom: 'Bob (Peer Human)',
    grantId: 'grant-sec-8801',
  },
];

export const INITIAL_LOCKS: VfsLockItem[] = [
  {
    lockId: 'lock-vfs-01',
    filePath: 'src/services/payment.ts',
    scope: 'line_range',
    lineStart: 45,
    lineEnd: 92,
    holderId: 'agent-local-1',
    holderName: 'CodeCraft (Local)',
    holderRole: 'local_agent',
    acquiredAt: '14:22:10',
    ttlSecondsRemaining: 240,
  },
  {
    lockId: 'lock-vfs-02',
    filePath: 'src/auth/jwt.ts',
    scope: 'file_full',
    holderId: 'agent-borrowed-1',
    holderName: 'DeepSeek-V3 Auditor',
    holderRole: 'borrowed_agent',
    acquiredAt: '14:24:05',
    ttlSecondsRemaining: 180,
  },
];

export const INITIAL_GRANTS: BorrowingGrantItem[] = [
  {
    grantId: 'grant-sec-8801',
    ownerId: 'user-bob',
    ownerName: 'Bob (Peer Human)',
    borrowerId: 'user-lead',
    borrowerName: 'Alice (Architect)',
    targetAgentName: 'DeepSeek-V3 Auditor',
    allocatedTokens: 50000,
    usedTokens: 14200,
    maxExecutions: 20,
    currentExecutions: 6,
    status: 'active',
  },
];

export const INITIAL_RELAYS: PortRelayItem[] = [
  {
    relayId: 'relay-web-3000',
    port: 3000,
    serviceName: 'Next.js App Preview',
    protocol: 'http',
    publicUrl: 'https://vr-3000.tunnel.internal',
    latencyMs: 18,
    activeConnections: 3,
    isHealthy: true,
  },
  {
    relayId: 'relay-api-8000',
    port: 8000,
    serviceName: 'FastAPI Microservice',
    protocol: 'http',
    publicUrl: 'https://vr-8000.tunnel.internal',
    latencyMs: 25,
    activeConnections: 5,
    isHealthy: true,
  },
];
