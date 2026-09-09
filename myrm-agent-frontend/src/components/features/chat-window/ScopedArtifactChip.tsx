'use client';

import React from 'react';
import { X, FileCode, FileSpreadsheet, FileText, Layers } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useScopedArtifactStore } from '@/store/useScopedArtifactStore';

const PREVIEW_MAX_LEN = 100;

function getKindIcon(kind?: string) {
  switch (kind) {
    case 'code':
      return <FileCode className="h-3.5 w-3.5 text-blue-500" />;
    case 'spreadsheet':
      return <FileSpreadsheet className="h-3.5 w-3.5 text-emerald-500" />;
    case 'document':
      return <FileText className="h-3.5 w-3.5 text-amber-500" />;
    default:
      return <Layers className="h-3.5 w-3.5 text-primary/70" />;
  }
}

export function ScopedArtifactChip() {
  const target = useScopedArtifactStore((s) => s.target);
  const clearTarget = useScopedArtifactStore((s) => s.clearTarget);

  return (
    <AnimatePresence>
      {target && (
        <motion.div
          initial={{ opacity: 0, height: 0, y: -4 }}
          animate={{ opacity: 1, height: 'auto', y: 0 }}
          exit={{ opacity: 0, height: 0, y: -4 }}
          transition={{ duration: 0.15, ease: 'easeOut' }}
          className="overflow-hidden"
          data-testid="scoped-artifact-chip"
        >
          <div className="flex items-center gap-2 mb-2 px-2.5 py-1.5 rounded-full bg-primary/10 border border-primary/20 text-xs">
            <div className="flex items-center gap-1.5 flex-shrink-0">
              {getKindIcon(target.kind)}
              <span className="font-medium text-foreground max-w-[120px] truncate" title={target.artifactName}>
                {target.artifactName}
              </span>
              <span className="px-1.5 py-0.2 rounded bg-primary/15 text-primary text-[10px] font-mono font-semibold">
                {target.scopeLabel}
              </span>
            </div>

            {target.selectedSnippet && (
              <span className="text-muted-foreground truncate flex-1 opacity-80" title={target.selectedSnippet}>
                {target.selectedSnippet.length > PREVIEW_MAX_LEN
                  ? `${target.selectedSnippet.slice(0, PREVIEW_MAX_LEN)}…`
                  : target.selectedSnippet}
              </span>
            )}

            <button
              type="button"
              onClick={clearTarget}
              aria-label="Remove scoped target"
              className="flex-shrink-0 p-0.5 rounded-full hover:bg-muted text-muted-foreground hover:text-foreground transition-colors ml-auto"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default ScopedArtifactChip;
