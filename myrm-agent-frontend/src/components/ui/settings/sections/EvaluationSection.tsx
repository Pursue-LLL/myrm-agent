import React, { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconPlay,
  IconFileText,
  IconCheckCircle,
  IconXCircle,
  IconAlertCircle,
  IconClock,
} from '@/components/ui/icons/PremiumIcons';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { evalService, type EvalSummary } from '@/services/eval';
import { toast } from 'sonner';

import { Textarea } from '@/components/ui/textarea';

export function EvaluationSection() {
  const t = useTranslations('settings');
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState<{ total: number; completed: number } | null>(null);
  const [summary, setSummary] = useState<EvalSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [casesContent, setCasesContent] = useState('');
  const [isSavingCases, setIsSavingCases] = useState(false);

  useEffect(() => {
    fetchLatestReport();
    fetchCases();
    checkStatus();
  }, []);

  const fetchCases = async () => {
    try {
      const data = await evalService.getEvalCases();
      setCasesContent(data.content);
    } catch (error) {
      console.error('Failed to fetch eval cases:', error);
    }
  };

  const handleSaveCases = async () => {
    try {
      setIsSavingCases(true);
      await evalService.saveEvalCases(casesContent);
      toast.success(t('evaluation.casesSaved'));
    } catch (error) {
      console.error('Failed to save eval cases:', error);
      toast.error(t('evaluation.casesSaveError'));
    } finally {
      setIsSavingCases(false);
    }
  };

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isRunning) {
      interval = setInterval(checkStatus, 2000);
    }
    return () => clearInterval(interval);
  }, [isRunning]);

  const checkStatus = async () => {
    try {
      const status = await evalService.getEvalStatus();
      setIsRunning(status.is_running);

      if (status.is_running) {
        setProgress({ total: status.total, completed: status.completed });
      } else if (progress !== null) {
        // Just finished
        setProgress(null);
        fetchLatestReport();
        if (status.error) {
          toast.error(status.error);
        } else {
          toast.success(t('evaluation.success'));
        }
      }
    } catch (error) {
      console.error('Failed to fetch eval status:', error);
    }
  };

  const fetchLatestReport = async () => {
    try {
      setIsLoading(true);
      const data = await evalService.getLatestReport();
      if (data.summary) {
        setSummary(data.summary);
      }
    } catch (error) {
      console.error('Failed to fetch latest report:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRunEvaluation = async () => {
    try {
      await evalService.runEvaluation();
      setIsRunning(true);
      setProgress({ total: 0, completed: 0 });
      toast.info(t('evaluation.running'));
    } catch (error) {
      console.error('Failed to start evaluation:', error);
      toast.error(t('evaluation.error'));
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-medium">{t('evaluation.title')}</h3>
        <p className="text-sm text-muted-foreground">{t('evaluation.description')}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IconFileText className="w-5 h-5" />
            {t('evaluation.testCases')}
          </CardTitle>
          <CardDescription>{t('evaluation.testCasesDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            value={casesContent}
            onChange={(e) => setCasesContent(e.target.value)}
            className="font-mono text-sm h-48"
            placeholder={'{"message": "Hello"}\n{"message": "Test", "expected_tools": ["web_search"]}'}
          />
          <Button onClick={handleSaveCases} disabled={isSavingCases || isRunning} variant="outline">
            {isSavingCases ? t('evaluation.saving') : t('evaluation.save')}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IconPlay className="w-5 h-5" />
            {t('evaluation.runTest')}
          </CardTitle>
          <CardDescription>{t('evaluation.runDescription')}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
            <Button onClick={handleRunEvaluation} disabled={isRunning} className="w-full sm:w-auto">
              {isRunning ? (
                <>
                  <span className="animate-spin mr-2">⏳</span>
                  {t('evaluation.runningLabel')}
                </>
              ) : (
                <>
                  <IconPlay className="w-4 h-4 mr-2" />
                  {t('evaluation.startTest')}
                </>
              )}
            </Button>
            {isRunning && progress && progress.total > 0 && (
              <div className="flex-1 w-full flex items-center gap-3 text-sm">
                <Progress value={(progress.completed / progress.total) * 100} className="h-2 flex-1" />
                <span className="text-muted-foreground whitespace-nowrap">
                  {progress.completed} / {progress.total}
                </span>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {!isLoading && summary && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <IconFileText className="w-5 h-5" />
              {t('evaluation.latestReport')}
            </CardTitle>
            <CardDescription>{t('evaluation.reportDescription')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="font-medium">{t('evaluation.passRate')}</span>
                <span className="font-medium">{(summary.pass_rate * 100).toFixed(1)}%</span>
              </div>
              <Progress value={summary.pass_rate * 100} className="h-2" />
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="flex flex-col items-center justify-center p-4 bg-muted/50 rounded-lg">
                <span className="text-2xl font-bold">{summary.total_cases}</span>
                <span className="text-xs text-muted-foreground uppercase tracking-wider">{t('evaluation.total')}</span>
              </div>
              <div className="flex flex-col items-center justify-center p-4 bg-green-500/10 text-green-600 rounded-lg">
                <IconCheckCircle className="w-6 h-6 mb-1" />
                <span className="text-xl font-bold">{summary.pass_count}</span>
                <span className="text-xs uppercase tracking-wider">{t('evaluation.passed')}</span>
              </div>
              <div className="flex flex-col items-center justify-center p-4 bg-red-500/10 text-red-600 rounded-lg">
                <IconXCircle className="w-6 h-6 mb-1" />
                <span className="text-xl font-bold">{summary.fail_count}</span>
                <span className="text-xs uppercase tracking-wider">{t('evaluation.failed')}</span>
              </div>
              <div className="flex flex-col items-center justify-center p-4 bg-yellow-500/10 text-yellow-600 rounded-lg">
                <IconAlertCircle className="w-6 h-6 mb-1" />
                <span className="text-xl font-bold">{summary.error_count}</span>
                <span className="text-xs uppercase tracking-wider">{t('evaluation.errors')}</span>
              </div>
            </div>

            <div className="flex items-center gap-2 text-sm text-muted-foreground pt-4 border-t">
              <IconClock className="w-4 h-4" />
              <span>
                {t('evaluation.executionTime')}: {(summary.total_ms / 1000).toFixed(2)}s
              </span>
              {summary.report_path && (
                <span className="ml-auto truncate max-w-[200px] sm:max-w-xs" title={summary.report_path}>
                  {summary.report_path}
                </span>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
