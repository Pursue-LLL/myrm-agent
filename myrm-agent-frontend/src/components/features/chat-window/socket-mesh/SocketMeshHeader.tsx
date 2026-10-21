import React from 'react';

export interface SocketMeshHeaderProps {
  chatId: string;
  project: string;
  peersCount: number;
  onlineCount: number;
  activeTab: 'peers' | 'console' | 'audit';
  onSelectTab: (tab: 'peers' | 'console' | 'audit') => void;
}

export const SocketMeshHeader: React.FC<SocketMeshHeaderProps> = ({
  chatId,
  project,
  peersCount,
  onlineCount,
  activeTab,
  onSelectTab,
}) => {
  return (
    <div>
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3 mb-3">
        <div>
          <h3 className="text-base font-semibold tracking-tight text-foreground flex items-center gap-2">
            <span>⚡ Lightweight P2P Agent Socket Mesh Protocol</span>
            <span className="text-xs px-2 py-0.5 rounded-full font-mono bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
              Chat: {chatId}
            </span>
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Project: <span className="font-mono text-foreground font-medium">{project}</span> | Zero-Broker Decentralized Local IPC Socket Mesh
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs px-2 py-0.5 rounded-md font-mono bg-emerald-500/10 text-emerald-600">
            Online: {onlineCount}/{peersCount}
          </span>
          <span className="text-xs px-2 py-0.5 rounded-md font-mono bg-muted text-muted-foreground">
            Zero Broker (coms.ts)
          </span>
        </div>
      </header>

      {/* Navigation Tabs */}
      <nav className="flex space-x-1 border-b border-border mb-3" aria-label="Socket Mesh Tabs">
        {(['peers', 'console', 'audit'] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => onSelectTab(tab)}
            className={`px-3 py-1.5 text-xs font-medium rounded-t-md transition-colors ${
              activeTab === tab
                ? 'border-b-2 border-primary text-primary bg-muted/40 font-semibold'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted/20'
            }`}
          >
            {tab === 'peers' && `Active Peers (${peersCount})`}
            {tab === 'console' && 'Atomic Envelope Console'}
            {tab === 'audit' && 'Mesh Audit Trail'}
          </button>
        ))}
      </nav>
    </div>
  );
};
