'use client';

import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { toast } from '@/hooks/useToast';

interface ABTestStatus {
  skill_id: string;
  version: number;
  status: 'running' | 'completed' | 'failed';
  baseline_score: number;
  candidate_score: number;
  progress_percent: number;
  winner: 'baseline' | 'candidate' | null;
  started_at: string;
  completed_at?: string;
}

interface SkillABTestDashboardProps {
  apiBaseUrl?: string;
}

/**
 * A/B测试Dashboard
 *
 * P0-2: 管理Skill A/B测试：
 * - 运行中测试列表（实时状态）
 * - 启动新测试表单
 * - 进度可视化
 * - Activate Winner按钮
 */
export function SkillABTestDashboard({ apiBaseUrl = '/api/v1' }: SkillABTestDashboardProps) {
  const [runningTests, setRunningTests] = useState<ABTestStatus[]>([]);
  const [isLoading] = useState(false);
  const [showStartDialog, setShowStartDialog] = useState(false);

  // 启动测试表单状态
  const [skillId, setSkillId] = useState('');
  const [baselineVersion, setBaselineVersion] = useState<number>(1);
  const [candidateContent, setCandidateContent] = useState('');
  const [isStarting, setIsStarting] = useState(false);

  useEffect(() => {
    fetchRunningTests();
    let timeoutId: NodeJS.Timeout;
    const handleSseEvent = () => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => fetchRunningTests(), 1000);
    };
    window.addEventListener('skill_ab_test_updated', handleSseEvent);
    window.addEventListener('app_resync_required', handleSseEvent);
    return () => {
      window.removeEventListener('skill_ab_test_updated', handleSseEvent);
      window.removeEventListener('app_resync_required', handleSseEvent);
      clearTimeout(timeoutId);
    };
  }, []);

  const fetchRunningTests = async () => {
    try {
      // 注意：这需要后端提供一个"list running tests"的API
      // 暂时使用mock数据，实际应该是 fetch(`${apiBaseUrl}/skill-optimization/ab-tests`)
      // 这里简化为空数组，实际项目需要实现完整API
      setRunningTests([]);
    } catch (err) {
      console.error('Failed to fetch running tests:', err);
    }
  };

  const handleStartTest = async () => {
    if (!skillId || !candidateContent) {
      toast.warning('Please fill all required fields');
      return;
    }

    setIsStarting(true);

    try {
      const response = await fetch(`${apiBaseUrl}/skill-optimization/ab-tests/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          skill_id: skillId,
          baseline_version: baselineVersion,
          candidate_content: candidateContent,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      toast.success('A/B test started successfully!');
      setShowStartDialog(false);
      setSkillId('');
      setCandidateContent('');
      fetchRunningTests();
    } catch (err) {
      toast.error(`Failed to start test: ${err}`);
    } finally {
      setIsStarting(false);
    }
  };

  const handleStopTest = async (skillId: string, version: number) => {
    if (!confirm(`Are you sure you want to stop A/B test for ${skillId} v${version}?`)) {
      return;
    }

    try {
      const response = await fetch(`${apiBaseUrl}/skill-optimization/ab-tests/${skillId}/stop?version=${version}`, {
        method: 'POST',
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      toast.success('A/B test stopped and winner activated!');
      fetchRunningTests();
    } catch (err) {
      toast.error(`Failed to stop test: ${err}`);
    }
  };

  return (
    <div className="space-y-4">
      {/* 头部控制 */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-foreground">A/B Testing Dashboard</h3>
          <p className="text-sm text-muted-foreground">Scientific validation for skill optimizations</p>
        </div>

        <Dialog open={showStartDialog} onOpenChange={setShowStartDialog}>
          <DialogTrigger asChild>
            <Button>Start New A/B Test</Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-[600px]">
            <DialogHeader>
              <DialogTitle>Start A/B Test</DialogTitle>
              <DialogDescription>
                Compare a new candidate version against the current baseline. The system will collect quality metrics
                and determine the winner.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="skill-id">Skill ID</Label>
                <Input
                  id="skill-id"
                  placeholder="e.g., search_skill"
                  value={skillId}
                  onChange={(e) => setSkillId(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="baseline-version">Baseline Version</Label>
                <Input
                  id="baseline-version"
                  type="number"
                  min="1"
                  value={baselineVersion}
                  onChange={(e) => setBaselineVersion(Number(e.target.value))}
                />
                <p className="text-xs text-muted-foreground">The current active version to compare against</p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="candidate-content">Candidate Content</Label>
                <Textarea
                  id="candidate-content"
                  placeholder="Paste the new skill content here..."
                  rows={10}
                  value={candidateContent}
                  onChange={(e) => setCandidateContent(e.target.value)}
                  className="font-mono text-xs"
                />
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setShowStartDialog(false)} disabled={isStarting}>
                Cancel
              </Button>
              <Button onClick={handleStartTest} disabled={isStarting}>
                {isStarting ? 'Starting...' : 'Start A/B Test'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* 运行中的测试 */}
      {isLoading ? (
        <Card className="p-6">
          <p className="text-sm text-muted-foreground text-center">Loading tests...</p>
        </Card>
      ) : runningTests.length === 0 ? (
        <Card className="p-12">
          <div className="text-center">
            <p className="text-sm text-muted-foreground mb-2">No active A/B tests</p>
            <Button variant="outline" onClick={() => setShowStartDialog(true)}>
              Start Your First Test
            </Button>
          </div>
        </Card>
      ) : (
        <div className="space-y-3">
          {runningTests.map((test) => (
            <Card key={`${test.skill_id}-${test.version}`} className="p-4">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h4 className="text-sm font-semibold text-foreground">
                    {test.skill_id} v{test.version}
                  </h4>
                  <p className="text-xs text-muted-foreground">Started: {new Date(test.started_at).toLocaleString()}</p>
                </div>

                <div className="flex items-center gap-2">
                  {test.status === 'running' && (
                    <span className="px-2 py-1 rounded text-xs font-medium bg-primary/10 text-primary">Running</span>
                  )}
                  {test.status === 'completed' && (
                    <span className="px-2 py-1 rounded text-xs font-medium bg-green-500/10 text-green-600">
                      Completed
                    </span>
                  )}
                  {test.status === 'failed' && (
                    <span className="px-2 py-1 rounded text-xs font-medium bg-destructive/10 text-destructive">
                      Failed
                    </span>
                  )}
                </div>
              </div>

              {/* 进度条 */}
              <div className="mb-4">
                <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                  <span>Progress</span>
                  <span>{test.progress_percent}%</span>
                </div>
                <div className="h-2 bg-muted rounded-full overflow-hidden">
                  <div className="h-full bg-primary transition-all" style={{ width: `${test.progress_percent}%` }} />
                </div>
              </div>

              {/* 对比结果 */}
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div className="p-3 rounded-lg bg-muted/50">
                  <p className="text-xs text-muted-foreground mb-1">Baseline</p>
                  <p className="text-2xl font-bold text-foreground">{test.baseline_score.toFixed(2)}</p>
                </div>
                <div className="p-3 rounded-lg bg-muted/50">
                  <p className="text-xs text-muted-foreground mb-1">Candidate</p>
                  <p className="text-2xl font-bold text-foreground">{test.candidate_score.toFixed(2)}</p>
                  {test.candidate_score > test.baseline_score && (
                    <p className="text-xs text-green-600 font-medium mt-1">
                      +{(((test.candidate_score - test.baseline_score) / test.baseline_score) * 100).toFixed(1)}%
                    </p>
                  )}
                </div>
              </div>

              {/* Winner提示 */}
              {test.winner && (
                <div className="p-3 rounded-lg bg-green-500/10 border border-green-500/20 mb-4">
                  <p className="text-sm font-medium text-green-600">
                    Winner: {test.winner === 'baseline' ? 'Baseline' : 'Candidate'}
                  </p>
                </div>
              )}

              {/* 操作按钮 */}
              <div className="flex items-center gap-2">
                {test.status === 'completed' && test.winner === 'candidate' && (
                  <Button size="sm" onClick={() => handleStopTest(test.skill_id, test.version)}>
                    Activate Winner
                  </Button>
                )}
                {test.status === 'running' && (
                  <Button size="sm" variant="outline" onClick={() => handleStopTest(test.skill_id, test.version)}>
                    Stop Test
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
