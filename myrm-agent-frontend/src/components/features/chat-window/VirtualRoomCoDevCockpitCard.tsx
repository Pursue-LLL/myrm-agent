import React, { useState, useMemo } from 'react';
import {
  Users,
  Lock,
  Unlock,
  KeyRound,
  Network,
  ShieldCheck,
  Zap,
  Clock,
  Terminal,
  ExternalLink,
  X,
  PlusCircle,
  AlertTriangle,
  Radio,
} from 'lucide-react';
import {
  RoomParticipant,
  VfsLockItem,
  BorrowingGrantItem,
  PortRelayItem,
  VirtualRoomCoDevCockpitCardProps,
  INITIAL_PARTICIPANTS,
  INITIAL_LOCKS,
  INITIAL_GRANTS,
  INITIAL_RELAYS,
} from './virtual-room/types';

export * from './virtual-room/types';

export function VirtualRoomCoDevCockpitCard({
  roomId = 'room-alpha-9901',
  roomName = 'Core Co-Dev Workspace #1',
  onDismiss,
  onLockAcquired,
}: VirtualRoomCoDevCockpitCardProps): React.ReactElement {
  const [activeTab, setActiveTab] = useState<'roster' | 'locks' | 'borrowing' | 'preview'>('locks');
  const [participants] = useState<RoomParticipant[]>(INITIAL_PARTICIPANTS);
  const [locks, setLocks] = useState<VfsLockItem[]>(INITIAL_LOCKS);
  const [grants, setGrants] = useState<BorrowingGrantItem[]>(INITIAL_GRANTS);
  const [relays] = useState<PortRelayItem[]>(INITIAL_RELAYS);
  const [conflictWarning, setConflictWarning] = useState<string | null>(null);

  const activeLocksCount = useMemo(() => locks.length, [locks]);
  const activeGrantsCount = useMemo(() => grants.filter((g) => g.status === 'active').length, [grants]);

  const handleAcquireSampleLock = () => {
    setConflictWarning(null);
    const candidatePath = 'src/services/payment.ts';
    const candidateStart = 120;
    const candidateEnd = 160;

    const hasConflict = locks.some((l) => {
      if (l.filePath !== candidatePath) {
        return false;
      }
      if (l.scope === 'file_full') {
        return true;
      }
      if (l.lineStart !== undefined && l.lineEnd !== undefined) {
        return !(candidateEnd < l.lineStart || candidateStart > l.lineEnd);
      }
      return false;
    });

    if (hasConflict) {
      setConflictWarning(`Lock conflict on ${candidatePath} [${candidateStart}-${candidateEnd}]: overlaps with existing lock.`);
      return;
    }

    const newLock: VfsLockItem = {
      lockId: `lock-vfs-${Date.now().toString().slice(-4)}`,
      filePath: candidatePath,
      scope: 'line_range',
      lineStart: candidateStart,
      lineEnd: candidateEnd,
      holderId: 'user-lead',
      holderName: 'Alice (Architect)',
      holderRole: 'human',
      acquiredAt: 'Just now',
      ttlSecondsRemaining: 300,
    };
    setLocks((prev) => [...prev, newLock]);
    onLockAcquired?.(newLock);
  };

  const handleReleaseLock = (lockId: string) => {
    setLocks((prev) => prev.filter((l) => l.lockId !== lockId));
    setConflictWarning(null);
  };

  const handleRevokeGrant = (grantId: string) => {
    setGrants((prev) =>
      prev.map((g) => (g.grantId === grantId ? { ...g, status: 'revoked' as const } : g))
    );
  };

  return (
    <section
      aria-label="Virtual Room Co-Dev Cockpit"
      className="rounded-xl border border-border/80 bg-card/95 p-4 shadow-xl backdrop-blur-md transition-all text-card-foreground my-3"
    >

      <div className="flex items-center justify-between border-b border-border/60 pb-3">
        <div className="flex items-center space-x-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500 ring-1 ring-emerald-500/20">
            <Radio className="h-4 w-4 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-sm">{roomName}</span>
              <span className="inline-flex items-center rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-500 border border-emerald-500/20">
                LIVE ROOM
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground font-mono">ID: {roomId} · Multi-Human + Multi-Agent Sandbox</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          {onDismiss && (
            <button
              onClick={onDismiss}
              aria-label="Close Room Cockpit"
              className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      <div className="mt-3 flex space-x-1 border-b border-border/40 pb-2 text-xs">
        <button
          onClick={() => setActiveTab('locks')}
          className={`flex items-center gap-1.5 rounded-md px-3 py-1 font-medium transition-colors ${
            activeTab === 'locks'
              ? 'bg-primary text-primary-foreground shadow-sm'
              : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
          }`}
        >
          <Lock className="h-3.5 w-3.5" />
          <span>VFS Line Locks ({activeLocksCount})</span>
        </button>
        <button
          onClick={() => setActiveTab('roster')}
          className={`flex items-center gap-1.5 rounded-md px-3 py-1 font-medium transition-colors ${
            activeTab === 'roster'
              ? 'bg-primary text-primary-foreground shadow-sm'
              : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
          }`}
        >
          <Users className="h-3.5 w-3.5" />
          <span>Roster ({participants.length})</span>
        </button>
        <button
          onClick={() => setActiveTab('borrowing')}
          className={`flex items-center gap-1.5 rounded-md px-3 py-1 font-medium transition-colors ${
            activeTab === 'borrowing'
              ? 'bg-primary text-primary-foreground shadow-sm'
              : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
          }`}
        >
          <KeyRound className="h-3.5 w-3.5" />
          <span>Agent Borrowing ({activeGrantsCount})</span>
        </button>
        <button
          onClick={() => setActiveTab('preview')}
          className={`flex items-center gap-1.5 rounded-md px-3 py-1 font-medium transition-colors ${
            activeTab === 'preview'
              ? 'bg-primary text-primary-foreground shadow-sm'
              : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
          }`}
        >
          <Network className="h-3.5 w-3.5" />
          <span>Live Previews ({relays.length})</span>
        </button>
      </div>

      <div className="mt-3">
        {conflictWarning && (
          <div className="mb-3 flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-500">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span className="flex-1 font-medium">{conflictWarning}</span>
          </div>
        )}

        {activeTab === 'locks' && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Concurrent In-flight AST & Line-Range Write Locks</span>
              <button
                onClick={handleAcquireSampleLock}
                className="inline-flex items-center gap-1 rounded bg-secondary px-2 py-1 font-medium text-[11px] text-secondary-foreground hover:bg-secondary/80 transition-colors"
              >
                <PlusCircle className="h-3 w-3" />
                <span>Acquire Safe Range Lock</span>
              </button>
            </div>
            <div className="space-y-1.5">
              {locks.map((lock) => (
                <div
                  key={lock.lockId}
                  className="flex items-center justify-between rounded-lg border border-border/50 bg-background/50 px-3 py-2 text-xs"
                >
                  <div className="flex items-center gap-2">
                    <div className="rounded p-1 bg-amber-500/10 text-amber-500">
                      <Lock className="h-3.5 w-3.5" />
                    </div>
                    <div>
                      <div className="font-mono font-medium text-foreground">
                        {lock.filePath}{' '}
                        <span className="text-[11px] text-muted-foreground">
                          {lock.scope === 'line_range' ? `[Lines ${lock.lineStart}-${lock.lineEnd}]` : '[FULL FILE]'}
                        </span>
                      </div>
                      <div className="text-[11px] text-muted-foreground">
                        Holder: <span className="text-foreground">{lock.holderName}</span> · TTL: {lock.ttlSecondsRemaining}s
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => handleReleaseLock(lock.lockId)}
                    aria-label={`Release lock ${lock.lockId}`}
                    className="inline-flex items-center gap-1 rounded border border-border/60 px-2 py-0.5 text-[11px] hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30 transition-colors"
                  >
                    <Unlock className="h-3 w-3" />
                    <span>Release</span>
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'roster' && (
          <div className="space-y-1.5">
            {participants.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between rounded-lg border border-border/50 bg-background/50 px-3 py-2 text-xs"
              >
                <div className="flex items-center gap-2.5">
                  <div
                    className={`h-2 w-2 rounded-full ${
                      p.status === 'online' ? 'bg-emerald-500' : p.status === 'busy' ? 'bg-amber-500' : 'bg-muted-foreground'
                    }`}
                  />
                  <div>
                    <div className="flex items-center gap-1.5 font-medium">
                      <span>{p.name}</span>
                      <span className="rounded bg-muted px-1.5 py-0.2 text-[10px] text-muted-foreground uppercase">
                        {p.role}
                      </span>
                    </div>
                    {p.activeFile && (
                      <p className="text-[11px] font-mono text-muted-foreground">Editing: {p.activeFile}</p>
                    )}
                    {p.borrowedFrom && (
                      <p className="text-[10px] text-primary/80">Delegated via: {p.borrowedFrom}</p>
                    )}
                  </div>
                </div>
                <span className="text-[11px] text-muted-foreground capitalize">{p.status}</span>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'borrowing' && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <div className="flex items-center gap-1 text-emerald-500 font-medium text-[11px]">
                <ShieldCheck className="h-3.5 w-3.5" />
                <span>Zero-Credential Safe Delegation Gateway</span>
              </div>
            </div>
            <div className="space-y-1.5">
              {grants.map((grant) => (
                <div
                  key={grant.grantId}
                  className="rounded-lg border border-border/50 bg-background/50 p-2.5 text-xs space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-semibold text-foreground flex items-center gap-1.5">
                        <Zap className="h-3.5 w-3.5 text-primary" />
                        <span>{grant.targetAgentName}</span>
                      </div>
                      <p className="text-[11px] text-muted-foreground">
                        Owner: {grant.ownerName} → Borrower: {grant.borrowerName}
                      </p>
                    </div>
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${
                        grant.status === 'active'
                          ? 'bg-emerald-500/10 text-emerald-500'
                          : 'bg-muted text-muted-foreground'
                      }`}
                    >
                      {grant.status}
                    </span>
                  </div>
                  <div>
                    <div className="flex justify-between text-[11px] text-muted-foreground mb-1">
                      <span>Tokens: {grant.usedTokens.toLocaleString()} / {grant.allocatedTokens.toLocaleString()}</span>
                      <span>Executions: {grant.currentExecutions} / {grant.maxExecutions}</span>
                    </div>
                    <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full bg-primary rounded-full transition-all"
                        style={{ width: `${Math.min(100, (grant.usedTokens / grant.allocatedTokens) * 100)}%` }}
                      />
                    </div>
                  </div>
                  {grant.status === 'active' && (
                    <div className="flex justify-end pt-1">
                      <button
                        onClick={() => handleRevokeGrant(grant.grantId)}
                        className="rounded border border-destructive/30 px-2 py-0.5 text-[11px] text-destructive hover:bg-destructive/10 transition-colors"
                      >
                        Revoke Grant
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'preview' && (
          <div className="space-y-1.5">
            {relays.map((relay) => (
              <div
                key={relay.relayId}
                className="flex items-center justify-between rounded-lg border border-border/50 bg-background/50 px-3 py-2 text-xs"
              >
                <div className="flex items-center gap-2">
                  <div className="rounded p-1 bg-primary/10 text-primary">
                    <Terminal className="h-3.5 w-3.5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-1.5 font-medium text-foreground">
                      <span>{relay.serviceName}</span>
                      <span className="font-mono text-[11px] text-muted-foreground">:{relay.port}</span>
                    </div>
                    <a
                      href={relay.publicUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[11px] text-primary hover:underline font-mono"
                    >
                      <span>{relay.publicUrl}</span>
                      <ExternalLink className="h-2.5 w-2.5" />
                    </a>
                  </div>
                </div>
                <div className="text-right text-[11px] text-muted-foreground">
                  <div className="flex items-center justify-end gap-1 text-emerald-500">
                    <Clock className="h-3 w-3" />
                    <span>{relay.latencyMs}ms</span>
                  </div>
                  <span>{relay.activeConnections} peers</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}


export default VirtualRoomCoDevCockpitCard;
