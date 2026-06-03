'use client';

import { useEffect, useState } from 'react';
import { wikiService, Concept, QueueStatus, PendingEditsResponse } from '@/services/wikiService';
import { Button } from '@/components/primitives/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/primitives/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/primitives/card';
import { showApiError } from '@/lib/api';
import { toast } from '@/hooks/useToast';
import { Textarea } from '@/components/primitives/textarea';
import { Loader2, Check, X, RefreshCw, XCircle, BrainCircuit, FileText, Inbox, Activity, Search } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { Input } from '@/components/primitives/input';

export default function BrainConsolePage() {
  // State
  const [concepts, setConcepts] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [totalConcepts, setTotalConcepts] = useState(0);
  const [selectedConcept, setSelectedConcept] = useState<Concept | null>(null);
  const [editContent, setEditContent] = useState('');
  const [isEditing, setIsEditing] = useState(false);

  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const [pendingEdits, setPendingEdits] = useState<PendingEditsResponse | null>(null);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(searchQuery), 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Data fetching
  const fetchData = async () => {
    try {
      setLoading(true);
      const [c, q, p] = await Promise.all([
        wikiService.listConcepts(debouncedQuery, 100, 0),
        wikiService.getQueueStatus(),
        wikiService.getPendingEdits(),
      ]);
      setConcepts(c.concepts);
      setTotalConcepts(c.total);
      setQueueStatus(q);
      setPendingEdits(p);
    } catch (e) {
      showApiError(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // Auto-refresh queue and pending using debounced SSE or fallback to interval if not implemented via SSE yet
    let interval: NodeJS.Timeout | undefined;

    const handleSseEvent = () => {
      // Refresh with simple debounce to avoid storm
      if (interval) clearTimeout(interval);
      interval = setTimeout(() => {
        wikiService.getQueueStatus().then(setQueueStatus).catch(console.error);
        wikiService.getPendingEdits().then(setPendingEdits).catch(console.error);
      }, 1000);
    };

    // Listen to generic subagents_updated as a fallback trigger for backend activity
    window.addEventListener('subagents_updated', handleSseEvent);

    // Also keep a slower fallback interval just in case
    interval = setInterval(() => {
      wikiService.getQueueStatus().then(setQueueStatus).catch(console.error);
      wikiService.getPendingEdits().then(setPendingEdits).catch(console.error);
    }, 15000);

    return () => {
      window.removeEventListener('subagents_updated', handleSseEvent);
      if (interval) clearInterval(interval);
    };
  }, [debouncedQuery]);

  const loadConcept = async (name: string) => {
    try {
      const c = await wikiService.getConcept(name);
      setSelectedConcept(c);
      setEditContent(c.content);
      setIsEditing(false);
    } catch (e) {
      showApiError(e);
    }
  };

  const handleSaveConcept = async () => {
    if (!selectedConcept) return;
    try {
      setSaving(true);
      await wikiService.updateConcept(selectedConcept.name, editContent);
      toast({ title: 'Success', description: 'Concept saved successfully.' });
      setIsEditing(false);
      await loadConcept(selectedConcept.name);
    } catch (e) {
      showApiError(e);
    } finally {
      setSaving(false);
    }
  };

  // Queue actions
  const handleCancelQueue = async () => {
    try {
      await wikiService.cancelQueue();
      toast({ title: 'Success', description: 'Queue cancelled.' });
      const q = await wikiService.getQueueStatus();
      setQueueStatus(q);
    } catch (e) {
      showApiError(e);
    }
  };

  const handleRetryQueue = async () => {
    try {
      await wikiService.retryFailedQueue();
      toast({ title: 'Success', description: 'Failed jobs retried.' });
      const q = await wikiService.getQueueStatus();
      setQueueStatus(q);
    } catch (e) {
      showApiError(e);
    }
  };

  // HITL actions
  const handleApprove = async (id: number) => {
    try {
      await wikiService.approveEdit(id);
      toast({ title: 'Approved', description: 'Edit merged successfully.' });
      fetchData(); // Refresh all to reflect new concept content
      if (selectedConcept) loadConcept(selectedConcept.name);
    } catch (e) {
      showApiError(e);
    }
  };

  const handleReject = async (id: number) => {
    try {
      await wikiService.rejectEdit(id);
      toast({ title: 'Rejected', description: 'Edit discarded.' });
      fetchData();
    } catch (e) {
      showApiError(e);
    }
  };

  if (loading && !concepts.length) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <Loader2 className="animate-spin h-8 w-8 text-primary" />
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] w-full overflow-hidden bg-background">
      {/* Left Sidebar: Entity List */}
      <div className="w-64 border-r flex flex-col bg-card/30">
        <div className="p-4 border-b flex flex-col gap-3">
          <div className="flex items-center space-x-2">
            <BrainCircuit className="h-5 w-5 text-primary" />
            <h2 className="font-semibold flex-1">Entities</h2>
            <span className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">{totalConcepts}</span>
          </div>
          <div className="relative">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search concepts..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 h-9 text-xs"
            />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {concepts.length === 0 ? (
            <p className="text-sm text-muted-foreground p-2">No entities found.</p>
          ) : (
            <ul className="space-y-1">
              {concepts.map((c) => (
                <li key={c}>
                  <button
                    onClick={() => loadConcept(c)}
                    className={`w-full text-left px-3 py-2 text-sm rounded-full transition-colors hover:bg-accent ${selectedConcept?.name === c ? 'bg-accent font-medium' : ''}`}
                  >
                    {c}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Middle: Obsidian Editor */}
      <div className="flex-1 border-r flex flex-col">
        {selectedConcept ? (
          <>
            <div className="p-4 border-b flex justify-between items-center bg-card/30">
              <div className="flex items-center space-x-2">
                <FileText className="h-5 w-5 text-primary" />
                <h2 className="font-semibold text-lg">{selectedConcept.name}</h2>
              </div>
              <div className="space-x-2">
                {isEditing ? (
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setIsEditing(false);
                        setEditContent(selectedConcept.content);
                      }}
                    >
                      Cancel
                    </Button>
                    <Button size="sm" onClick={handleSaveConcept} disabled={saving}>
                      {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                      Save
                    </Button>
                  </>
                ) : (
                  <Button variant="outline" size="sm" onClick={() => setIsEditing(true)}>
                    Edit
                  </Button>
                )}
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-6 bg-background">
              {isEditing ? (
                <Textarea
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  className="min-h-[500px] font-mono text-sm resize-none"
                />
              ) : (
                <article className="prose prose-sm dark:prose-invert max-w-none">
                  <ReactMarkdown>{selectedConcept.content}</ReactMarkdown>
                </article>
              )}
            </div>
          </>
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground flex-col space-y-4">
            <BrainCircuit className="h-16 w-16 opacity-20" />
            <p>Select an entity to view or edit</p>
          </div>
        )}
      </div>

      {/* Right Sidebar: Activity & Review */}
      <div className="w-80 flex flex-col bg-card/30">
        <Tabs defaultValue="review" className="flex-1 flex flex-col">
          <div className="border-b px-4 pt-4">
            <TabsList className="w-full grid grid-cols-2 h-auto">
              <TabsTrigger value="review" className="min-w-0 gap-1.5">
                <Inbox className="h-4 w-4 shrink-0" />
                <span className="truncate">Review</span>
                {pendingEdits?.stats.pending ? (
                  <span className="shrink-0 bg-destructive text-destructive-foreground text-xs rounded-full px-1.5 py-0.5 min-w-[1.25rem] text-center">
                    {pendingEdits.stats.pending}
                  </span>
                ) : null}
              </TabsTrigger>
              <TabsTrigger value="queue" className="min-w-0 gap-1.5">
                <Activity className="h-4 w-4 shrink-0" />
                <span className="truncate">Queue</span>
              </TabsTrigger>
            </TabsList>
          </div>

          {/* Review Inbox */}
          <TabsContent
            value="review"
            className="flex-1 overflow-y-auto p-4 m-0 data-[state=active]:flex flex-col gap-4"
          >
            {pendingEdits?.pending_edits.length === 0 ? (
              <div className="text-center text-muted-foreground p-8 text-sm">
                <Inbox className="h-8 w-8 mx-auto mb-2 opacity-50" />
                No pending edits to review.
              </div>
            ) : (
              pendingEdits?.pending_edits.map((edit) => (
                <Card key={edit.id} className="text-sm border-muted">
                  <CardHeader className="p-3 pb-2">
                    <CardTitle className="text-base">{edit.concept_name}</CardTitle>
                    <CardDescription className="text-xs">
                      Proposed at {new Date(edit.created_at).toLocaleString()}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="p-3 pt-0">
                    <div className="bg-muted p-2 rounded max-h-40 overflow-y-auto font-mono text-xs whitespace-pre-wrap">
                      {edit.proposed_content.substring(0, 300)}...
                    </div>
                  </CardContent>
                  <CardFooter className="p-3 pt-0 flex justify-end space-x-2">
                    <Button variant="outline" size="sm" onClick={() => handleReject(edit.id)}>
                      <X className="h-4 w-4 mr-1" /> Reject
                    </Button>
                    <Button size="sm" onClick={() => handleApprove(edit.id)}>
                      <Check className="h-4 w-4 mr-1" /> Approve
                    </Button>
                  </CardFooter>
                </Card>
              ))
            )}
          </TabsContent>

          {/* Ingestion Queue */}
          <TabsContent value="queue" className="flex-1 overflow-y-auto p-4 m-0 data-[state=active]:flex flex-col gap-4">
            <Card className="border-muted">
              <CardHeader className="p-3 pb-2">
                <CardTitle className="text-base flex items-center justify-between">
                  Queue Stats
                  <div className="space-x-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6"
                      onClick={handleRetryQueue}
                      title="Retry Failed"
                    >
                      <RefreshCw className="h-3 w-3" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 text-destructive hover:text-destructive"
                      onClick={handleCancelQueue}
                      title="Cancel Pending"
                    >
                      <XCircle className="h-3 w-3" />
                    </Button>
                  </div>
                </CardTitle>
              </CardHeader>
              <CardContent className="p-3 pt-0">
                {queueStatus && (
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="bg-muted p-2 rounded">
                      <div className="text-muted-foreground">Pending</div>
                      <div className="font-semibold text-lg">{queueStatus.stats.pending || 0}</div>
                    </div>
                    <div className="bg-muted p-2 rounded">
                      <div className="text-muted-foreground">Processing</div>
                      <div className="font-semibold text-lg text-blue-500">{queueStatus.stats.processing || 0}</div>
                    </div>
                    <div className="bg-muted p-2 rounded">
                      <div className="text-muted-foreground">Completed</div>
                      <div className="font-semibold text-lg text-green-500">{queueStatus.stats.completed || 0}</div>
                    </div>
                    <div className="bg-muted p-2 rounded">
                      <div className="text-muted-foreground">Failed</div>
                      <div className="font-semibold text-lg text-destructive">{queueStatus.stats.failed || 0}</div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            <div className="space-y-2">
              <h3 className="font-medium text-sm">Active & Pending Items</h3>
              {queueStatus?.pending_items.length === 0 ? (
                <p className="text-xs text-muted-foreground">Queue is empty.</p>
              ) : (
                <ul className="space-y-2">
                  {queueStatus?.pending_items.map((item) => (
                    <li
                      key={item.id}
                      className="text-xs p-2 bg-background border rounded-full truncate"
                      title={item.source_path}
                    >
                      <div className="flex justify-between mb-1">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] ${item.status === 'processing' ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200' : 'bg-secondary text-secondary-foreground'}`}
                        >
                          {item.status}
                        </span>
                        <span className="text-muted-foreground">{item.file_type}</span>
                      </div>
                      <div className="text-foreground truncate">{item.source_path.split('/').pop()}</div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
