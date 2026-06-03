'use client';

import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/primitives/card';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { useTranslations } from 'next-intl';
import { CheckCircle2, XCircle, Clock, ShieldAlert, GitMerge } from 'lucide-react';

interface ShadowTestResult {
  skill_id: string;
  baseline_version: number;
  candidate_version: number;
  is_match: boolean;
  baseline_duration: number;
  candidate_duration: number;
}

interface StrategyMergeResult {
  skill_id: string;
  global_strategy: string;
  local_code: string;
  merged_code: string;
  baseline_version: number;
}

export function SafeTestDashboard() {
  const t = useTranslations('SkillOptimization');

  // Mock data for demonstration
  const [shadowTests] = useState<ShadowTestResult[]>([
    {
      skill_id: 'web_search',
      baseline_version: 1,
      candidate_version: 2,
      is_match: true,
      baseline_duration: 1.2,
      candidate_duration: 0.8,
    },
    {
      skill_id: 'pdf_parser',
      baseline_version: 3,
      candidate_version: 4,
      is_match: false,
      baseline_duration: 2.5,
      candidate_duration: 3.1,
    },
  ]);

  const [mergeTasks] = useState<StrategyMergeResult[]>([
    {
      skill_id: 'web_search',
      global_strategy: 'Implement exponential backoff for rate-limited APIs and add a strict 10s timeout.',
      local_code: 'def execute(query):\n    # Local custom logic\n    return search_api(query)',
      merged_code:
        'def execute(query):\n    # Applied Global Strategy: Implement exponential backoff...\n    # Local custom logic\n    @retry(stop=stop_after_attempt(3))\n    return search_api(query, timeout=10)',
      baseline_version: 1,
    },
  ]);

  return (
    <div className="space-y-6">
      {/* Shadow Test Results */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-blue-500" />
            {t('shadowTest.title') || 'Zero-Risk Shadow Tests'}
          </CardTitle>
          <CardDescription>
            {t('shadowTest.description') ||
              'Results of candidate versions running in isolated mode alongside real traffic.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {shadowTests.map((test, idx) => (
              <div key={idx} className="flex items-center justify-between p-4 border rounded-lg bg-background">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{test.skill_id}</span>
                    <Badge variant="outline">
                      v{test.baseline_version} → v{test.candidate_version}
                    </Badge>
                    {test.is_match ? (
                      <Badge variant="default" className="bg-green-500">
                        <CheckCircle2 className="w-3 h-3 mr-1" /> Match
                      </Badge>
                    ) : (
                      <Badge variant="destructive">
                        <XCircle className="w-3 h-3 mr-1" /> Diverged
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-4 text-sm text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Clock className="w-4 h-4" />
                      Baseline: {test.baseline_duration.toFixed(2)}s
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock className="w-4 h-4" />
                      Candidate: {test.candidate_duration.toFixed(2)}s
                    </span>
                  </div>
                </div>
                <div>
                  <Button variant={test.is_match ? 'default' : 'outline'} size="sm">
                    {test.is_match ? 'Promote to Active' : 'View Diff'}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Strategy Merge Tasks */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <GitMerge className="w-5 h-5 text-purple-500" />
            {t('strategyMerge.title') || 'Strategy-Level Semantic Merges'}
          </CardTitle>
          <CardDescription>
            {t('strategyMerge.description') ||
              'Global optimization strategies intelligently applied to your local custom code.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {mergeTasks.map((task, idx) => (
              <div key={idx} className="p-4 border rounded-lg bg-background space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{task.skill_id}</span>
                    <Badge variant="secondary">Global Strategy Received</Badge>
                  </div>
                  <Button size="sm">Review & Accept Merge</Button>
                </div>

                <div className="p-3 bg-muted rounded-full text-sm">
                  <span className="font-semibold text-purple-600">Strategy: </span>
                  {task.global_strategy}
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <div className="text-sm font-medium">Local Code (v{task.baseline_version})</div>
                    <pre className="p-3 bg-slate-950 text-slate-50 rounded-full text-xs overflow-x-auto">
                      <code>{task.local_code}</code>
                    </pre>
                  </div>
                  <div className="space-y-2">
                    <div className="text-sm font-medium text-green-600">
                      Proposed Merge (v{task.baseline_version + 1})
                    </div>
                    <pre className="p-3 bg-slate-950 text-green-400 rounded-full text-xs overflow-x-auto border border-green-900">
                      <code>{task.merged_code}</code>
                    </pre>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
