import React, { useEffect, useState } from 'react';
import { FileText, Activity, ShieldAlert, CheckCircle2 } from 'lucide-react';
import { fetchRecentTaskAdaptiveContexts } from '@/services/task-adaptive';
import { IconLock } from '@/components/ui/icons/PremiumIcons';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';

interface FileHotspot {
  file_path: string;
  read_count: number;
  write_count: number;
  last_accessed: number;
}

interface AntiPattern {
  error_signature: string;
  failed_tool: string;
  failed_args: Record<string, unknown>;
  user_correction: string | null;
  timestamp: number;
}

interface TraceRunDigest {
  session_id: string;
  task_intent: string | null;
  hotspots: FileHotspot[];
  anti_patterns: AntiPattern[];
  success_rate: number;
  duration_ms: number;
}

interface TaskAdaptivePreviewProps {
  onApplyContext?: (digest: TraceRunDigest) => void;
  className?: string;
}

export function TaskAdaptivePreview({ onApplyContext, className = '' }: TaskAdaptivePreviewProps) {
  const [digests, setDigests] = useState<TraceRunDigest[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDigestId, setSelectedDigestId] = useState<string | null>(null);
  const [isApplied, setIsApplied] = useState(false);

  useEffect(() => {
    const loadDigests = async () => {
      try {
        const response = await fetchRecentTaskAdaptiveContexts(5);
        if (response && response.data && response.data.digests) {
          setDigests(response.data.digests);
          if (response.data.digests.length > 0) {
            setSelectedDigestId(response.data.digests[0].session_id);
          }
        }
      } catch (error) {
        console.error('Failed to load task adaptive contexts', error);
      } finally {
        setLoading(false);
      }
    };
    loadDigests();
  }, []);

  if (loading) {
    return (
      <Card className={`w-full ${className}`}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            JIT Context Assembler
          </CardTitle>
          <CardDescription>Loading historical execution traces...</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (digests.length === 0) {
    return null; // Don't show if no historical context is available
  }

  const selectedDigest = digests.find((d) => d.session_id === selectedDigestId) || digests[0];

  if (isApplied) {
    return (
      <Card className={`w-full border-green-200 bg-green-50 ${className}`}>
        <div className="flex items-center justify-between p-3">
          <div className="flex items-center gap-2 text-green-800 font-medium text-sm">
            <CheckCircle2 className="h-4 w-4" />
            <IconLock className="inline-block h-4 w-4" /> Kanban Context Loaded:{' '}
            {selectedDigest.task_intent ? selectedDigest.task_intent.substring(0, 30) + '...' : 'Historical Context'}
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="h-8 text-green-700 hover:bg-green-100 hover:text-green-900"
            onClick={() => setIsApplied(false)}
          >
            Review
          </Button>
        </div>
      </Card>
    );
  }

  return (
    <Card className={`w-full border-blue-200 ${className}`}>
      <CardHeader className="bg-blue-50/50 pb-4">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-blue-800">
              <Activity className="h-5 w-5 text-blue-600" />
              Kanban JIT Context
            </CardTitle>
            <CardDescription className="mt-1">
              Assemble execution boundaries based on past evidence before starting.
            </CardDescription>
          </div>
          {onApplyContext && (
            <Button
              size="sm"
              onClick={() => {
                setIsApplied(true);
                onApplyContext(selectedDigest);
              }}
              className="bg-blue-600 hover:bg-blue-700"
            >
              Apply to Session
            </Button>
          )}
        </div>

        {digests.length > 1 && (
          <div className="flex gap-2 mt-4 overflow-x-auto pb-2">
            {digests.map((digest) => (
              <Badge
                key={digest.session_id}
                variant={selectedDigestId === digest.session_id ? 'default' : 'outline'}
                className={`cursor-pointer whitespace-nowrap ${selectedDigestId === digest.session_id ? 'bg-blue-600' : ''}`}
                onClick={() => setSelectedDigestId(digest.session_id)}
              >
                {digest.task_intent ? digest.task_intent.substring(0, 20) + '...' : 'Unknown Task'}
                <span className="ml-2 text-xs opacity-70">{(digest.success_rate * 100).toFixed(0)}%</span>
              </Badge>
            ))}
          </div>
        )}
      </CardHeader>

      <CardContent className="p-0">
        <ScrollArea className="h-64">
          <div className="p-4 space-y-6">
            {/* Hotspots Section */}
            {selectedDigest.hotspots.length > 0 && (
              <div>
                <h4 className="flex items-center gap-2 text-sm font-semibold text-slate-700 mb-3">
                  <FileText className="h-4 w-4" />
                  Historical Hotspots
                </h4>
                <div className="space-y-2">
                  {selectedDigest.hotspots.slice(0, 5).map((hotspot, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between text-sm bg-slate-50 p-2 rounded-full border border-slate-100"
                    >
                      <span className="font-mono text-xs truncate max-w-[70%]">{hotspot.file_path}</span>
                      <div className="flex gap-2 text-xs text-slate-500">
                        <span title="Reads">R: {hotspot.read_count}</span>
                        <span title="Writes">W: {hotspot.write_count}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Anti-Patterns Section */}
            {selectedDigest.anti_patterns.length > 0 ? (
              <div>
                <h4 className="flex items-center gap-2 text-sm font-semibold text-red-700 mb-3">
                  <ShieldAlert className="h-4 w-4" />
                  Anti-Patterns & Pitfalls
                </h4>
                <div className="space-y-3">
                  {selectedDigest.anti_patterns.slice(0, 3).map((ap, idx) => (
                    <div key={idx} className="text-sm bg-red-50 p-3 rounded-full border border-red-100">
                      <div className="font-medium text-red-800 mb-1 flex justify-between">
                        <span>Tool: {ap.failed_tool}</span>
                      </div>
                      <div className="text-xs text-red-600 font-mono mb-2 line-clamp-2">{ap.error_signature}</div>
                      {ap.user_correction && (
                        <div className="mt-2 text-xs bg-white p-2 rounded border border-red-100">
                          <span className="font-semibold text-green-700 flex items-center gap-1 mb-1">
                            <CheckCircle2 className="h-3 w-3" /> User Correction:
                          </span>
                          {ap.user_correction}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="text-sm text-slate-500 flex items-center gap-2 bg-green-50 p-3 rounded-full">
                <CheckCircle2 className="h-4 w-4 text-green-600" />
                No critical anti-patterns detected for this context.
              </div>
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
