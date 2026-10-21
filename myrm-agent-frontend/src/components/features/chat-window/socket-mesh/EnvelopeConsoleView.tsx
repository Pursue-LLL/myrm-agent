import React from 'react';
import { PeerInfo } from './types';

export interface EnvelopeConsoleViewProps {
  peers: PeerInfo[];
  sender: string;
  onChangeSender: (val: string) => void;
  target: string;
  onChangeTarget: (val: string) => void;
  promptInput: string;
  onChangePromptInput: (val: string) => void;
  lastResponse: string;
  isProcessing: boolean;
  onSendAndAwait: () => void;
}

export const EnvelopeConsoleView: React.FC<EnvelopeConsoleViewProps> = ({
  peers,
  sender,
  onChangeSender,
  target,
  onChangeTarget,
  promptInput,
  onChangePromptInput,
  lastResponse,
  isProcessing,
  onSendAndAwait,
}) => {
  return (
    <div className="space-y-3">
      <div className="p-3 rounded-lg border border-border bg-background space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label htmlFor="envelope-sender-select" className="block text-[11px] font-medium text-muted-foreground mb-1">
              Sender Agent:
            </label>
            <select
              id="envelope-sender-select"
              value={sender}
              onChange={(e) => onChangeSender(e.target.value)}
              className="w-full text-xs px-2 py-1.5 rounded border border-border bg-background"
            >
              {peers.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name} ({p.purpose})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="envelope-target-select" className="block text-[11px] font-medium text-muted-foreground mb-1">
              Target Destination:
            </label>
            <select
              id="envelope-target-select"
              value={target}
              onChange={(e) => onChangeTarget(e.target.value)}
              className="w-full text-xs px-2 py-1.5 rounded border border-border bg-background"
            >
              {peers.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name} ({p.purpose})
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label htmlFor="envelope-prompt-input" className="block text-[11px] font-medium text-muted-foreground mb-1">
            Prompt Payload (Envelope Content):
          </label>
          <textarea
            id="envelope-prompt-input"
            rows={3}
            value={promptInput}
            onChange={(e) => onChangePromptInput(e.target.value)}
            placeholder="e.g., Audit AST import syntax tree for cyclic references and report findings..."
            className="w-full text-xs p-2 rounded border border-border bg-background focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-border/40">
          <div className="text-[11px] text-muted-foreground flex items-center gap-2">
            <span className="font-mono text-xs bg-muted px-2 py-0.5 rounded">Hops Limit: 5</span>
            <span className="text-[10px] text-emerald-600 font-medium">✓ Anti-Loop Active</span>
          </div>

          <button
            type="button"
            disabled={isProcessing || !promptInput.trim() || sender === target}
            onClick={onSendAndAwait}
            className="px-4 py-1.5 text-xs font-medium text-white bg-primary rounded hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {isProcessing ? 'Awaiting P2P Reply...' : 'Dispatch Prompt & Await (Zero-Broker)'}
          </button>
        </div>
      </div>

      {lastResponse && (
        <div className="p-3 rounded-lg border border-indigo-500/30 bg-indigo-500/5 text-xs space-y-1">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-indigo-600 dark:text-indigo-400">Response Envelope Received:</span>
            <span className="text-[10px] text-muted-foreground font-mono">Status: Delivered</span>
          </div>
          <p className="font-mono text-[11px] text-foreground bg-background/80 p-2 rounded border border-border/50 whitespace-pre-wrap">
            {lastResponse}
          </p>
        </div>
      )}
    </div>
  );
};
