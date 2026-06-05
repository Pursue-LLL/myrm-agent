import React, { useState, useEffect } from 'react';
import { fetchWithTimeout } from '@/lib/api';
import { Button } from '@/components/primitives/button';
import { Activity, AlertTriangle, CheckCircle2, XCircle, Clock } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/primitives/dialog';
import { Progress } from '@/components/primitives/progress';

interface ToolHealth {
  tool_name: string;
  total_calls: number;
  success_count: number;
  error_count: number;
  avg_duration: number;
  max_duration: number;
}

export const AgentToolDiagnostics = ({ agentId }: { agentId: string }) => {
  const [data, setData] = useState<ToolHealth[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open || !agentId) return;
    const fetchHealth = async () => {
      setLoading(true);
      try {
        const res = await fetchWithTimeout(`/statistics/agent/${agentId}/tool_health?days=7`);
        const json = await res.json();
        if (json.data) {
          setData(json.data);
        }
      } catch (e) {
        console.error('Failed to fetch tool health', e);
      } finally {
        setLoading(false);
      }
    };
    fetchHealth();
  }, [agentId, open]);

  const sortedData = [...data].sort((a, b) => {
    const errorRateA = a.total_calls > 0 ? a.error_count / a.total_calls : 0;
    const errorRateB = b.total_calls > 0 ? b.error_count / b.total_calls : 0;
    return errorRateB - errorRateA;
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground">
          <Activity className="w-3.5 h-3.5 mr-1" />
          Tool Health
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-primary" />
            Agent Tool Diagnostics
          </DialogTitle>
        </DialogHeader>
        
        <div className="flex flex-col gap-4 py-4 max-h-[60vh] overflow-y-auto pr-2">
          {loading ? (
            <div className="flex items-center justify-center p-8 text-muted-foreground">
              Loading diagnostics...
            </div>
          ) : sortedData.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-8 text-center bg-muted/30 rounded-lg border border-dashed">
              <CheckCircle2 className="w-8 h-8 text-muted-foreground/50 mb-2" />
              <p className="text-sm text-muted-foreground">No tool execution data for this agent yet.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {sortedData.map((tool) => {
                const errorRate = tool.total_calls > 0 ? tool.error_count / tool.total_calls : 0;
                const isWarning = errorRate > 0.3;
                const isCritical = errorRate > 0.6;
                
                return (
                  <div key={tool.tool_name} className={`p-3 rounded-lg border flex flex-col gap-2 ${isCritical ? 'border-red-200 bg-red-50/50 dark:border-red-900/50 dark:bg-red-950/20' : isWarning ? 'border-amber-200 bg-amber-50/50 dark:border-amber-900/50 dark:bg-amber-950/20' : 'border-border/60 bg-muted/20'}`}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 font-medium">
                        {isCritical ? <XCircle className="w-4 h-4 text-red-500" /> : isWarning ? <AlertTriangle className="w-4 h-4 text-amber-500" /> : <CheckCircle2 className="w-4 h-4 text-green-500" />}
                        <span className={isCritical ? 'text-red-700 dark:text-red-400' : isWarning ? 'text-amber-700 dark:text-amber-400' : ''}>{tool.tool_name}</span>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {tool.total_calls} calls
                      </div>
                    </div>
                    
                    <div className="flex flex-col gap-1.5 mt-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">Success Rate</span>
                        <span className={`font-medium ${isCritical ? 'text-red-600 dark:text-red-400' : ''}`}>{((1 - errorRate) * 100).toFixed(1)}%</span>
                      </div>
                      <Progress value={(1 - errorRate) * 100} className="h-1.5" indicatorClassName={isCritical ? 'bg-red-500' : isWarning ? 'bg-amber-500' : 'bg-green-500'} />
                    </div>
                    
                    <div className="grid grid-cols-2 gap-4 mt-2 pt-2 border-t border-border/50 text-xs">
                      <div className="flex flex-col gap-0.5">
                        <span className="text-muted-foreground">Errors</span>
                        <span className="font-medium text-foreground">{tool.error_count}</span>
                      </div>
                      <div className="flex flex-col gap-0.5">
                        <span className="text-muted-foreground flex items-center gap-1"><Clock className="w-3 h-3" /> Avg Time</span>
                        <span className="font-medium text-foreground">{tool.avg_duration.toFixed(2)}s</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};