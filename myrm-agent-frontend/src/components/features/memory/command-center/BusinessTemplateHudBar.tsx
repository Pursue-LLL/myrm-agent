/**
 * [INPUT]
 * None
 *
 * [OUTPUT]
 * BusinessTemplateHudBar: 4-metric HUD status bar for Item 107 Business Scenario Experience Templates.
 *
 * [POS]
 * Command center status header visualizing template counts, analysis methods, retail stages, and escalation gate status.
 * Single file < 150 lines. Strict typing, zero any.
 */

import React from 'react';
import { Layers, FileSpreadsheet, ShoppingBag, ShieldAlert, RefreshCw } from 'lucide-react';

interface BusinessTemplateHudBarProps {
  totalTemplates: number;
  analysisStepsCount: number;
  retailStepsCount: number;
  activeEscalationTriggers: number;
  onRefresh: () => void;
  isRefreshing: boolean;
}

export const BusinessTemplateHudBar: React.FC<BusinessTemplateHudBarProps> = ({
  totalTemplates,
  analysisStepsCount,
  retailStepsCount,
  activeEscalationTriggers,
  onRefresh,
  isRefreshing,
}) => {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-3 bg-muted/30 rounded-lg border border-border/50">
      {/* 1. Total Templates */}
      <div className="flex items-center gap-2.5 p-2 bg-background/60 rounded border border-border/40">
        <div className="p-1.5 rounded bg-purple-500/10 text-purple-500">
          <Layers className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
            Cold-Start Templates
          </div>
          <div className="text-sm font-semibold flex items-center gap-1.5">
            <span className="inline-block w-2 h-2 rounded-full bg-purple-500" />
            {totalTemplates} Active Schemas
          </div>
        </div>
      </div>

      {/* 2. Business Review Methods */}
      <div className="flex items-center gap-2.5 p-2 bg-background/60 rounded border border-border/40">
        <div className="p-1.5 rounded bg-blue-500/10 text-blue-500">
          <FileSpreadsheet className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
            Review Methods
          </div>
          <div className="text-sm font-semibold">
            {analysisStepsCount} Reusable Rules
          </div>
        </div>
      </div>

      {/* 3. Retail Stages */}
      <div className="flex items-center gap-2.5 p-2 bg-background/60 rounded border border-border/40">
        <div className="p-1.5 rounded bg-emerald-500/10 text-emerald-500">
          <ShoppingBag className="w-4 h-4" />
        </div>
        <div>
          <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
            Retail Workflow
          </div>
          <div className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">
            {retailStepsCount}-Stage Protocol
          </div>
        </div>
      </div>

      {/* 4. Escalation Gate Guard */}
      <div className="flex items-center justify-between p-2 bg-background/60 rounded border border-border/40">
        <div className="flex items-center gap-2.5">
          <div className={`p-1.5 rounded ${activeEscalationTriggers > 0 ? 'bg-amber-500/10 text-amber-500' : 'bg-primary/10 text-primary'}`}>
            <ShieldAlert className="w-4 h-4" />
          </div>
          <div>
            <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
              Escalation Gate
            </div>
            <div className="text-sm font-semibold">
              {activeEscalationTriggers > 0 ? `${activeEscalationTriggers} Triggers Configured` : 'Armed & Safe'}
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={isRefreshing}
          aria-label="Refresh templates"
          className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
        </button>
      </div>
    </div>
  );
};
