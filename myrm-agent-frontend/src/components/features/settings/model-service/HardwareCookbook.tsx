'use client';

import { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Cpu, HardDrive, Monitor, CheckCircle2, AlertTriangle, XCircle, Download, Loader2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Progress } from '@/components/primitives/progress';
import { Alert, AlertDescription, AlertTitle } from '@/components/primitives/alert';
import { getDeployMode } from '@/lib/deploy-mode';

interface HardwareRecommendation {
  model_id: string;
  name: string;
  description: string;
  req_vram_gb: number;
  fit_score: number;
  fit_level: 'perfect' | 'good' | 'fair' | 'poor';
}

interface HardwareProfile {
  hardware_detected: boolean;
  os_type?: string;
  cpu_arch?: string;
  total_ram_gb?: number;
  has_gpu?: boolean;
  gpu_name?: string;
  gpu_vram_gb?: number;
  is_unified_memory?: boolean;
  recommendations: HardwareRecommendation[];
}

interface HardwareCookbookProps {
  onApplyModel: (modelId: string) => void;
}

export default function HardwareCookbook({ onApplyModel }: HardwareCookbookProps) {
  const t = useTranslations('settings.modelService.cookbook');
  const [profile, setProfile] = useState<HardwareProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // SaaS 模式下直接隐藏
  const isSaaS = getDeployMode() === 'sandbox';

  useEffect(() => {
    if (isSaaS) {
      setLoading(false);
      return;
    }

    const fetchHardwareProfile = async () => {
      try {
        const res = await fetch('/api/v1/integrations/llms/hardware/recommendations');
        if (!res.ok) throw new Error('Failed to fetch hardware recommendations');
        const data = await res.json();
        if (data.code === 0 && data.data) {
          setProfile(data.data);
        } else {
          throw new Error(data.message || 'Unknown error');
        }
      } catch (err) {
        console.error('Hardware detection failed:', err);
        setError(err instanceof Error ? err.message : 'Failed to detect hardware');
      } finally {
        setLoading(false);
      }
    };

    fetchHardwareProfile();
  }, [isSaaS]);

  if (isSaaS || (!loading && !error && profile && !profile.hardware_detected)) {
    return null; // 优雅降级：SaaS 模式或硬件检测失败时隐藏面板
  }

  if (loading) {
    return (
      <Card className="border-primary/20 bg-primary/5">
        <CardContent className="p-6 flex items-center justify-center space-x-2 text-muted-foreground">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span>{t('detecting')}</span>
        </CardContent>
      </Card>
    );
  }

  if (error || !profile) {
    return null; // 发生错误时也静默隐藏，不干扰主流程
  }

  const getFitLevelColor = (level: string) => {
    switch (level) {
      case 'perfect': return 'text-green-500 bg-green-500/10 border-green-500/20';
      case 'good': return 'text-blue-500 bg-blue-500/10 border-blue-500/20';
      case 'fair': return 'text-yellow-500 bg-yellow-500/10 border-yellow-500/20';
      case 'poor': return 'text-red-500 bg-red-500/10 border-red-500/20';
      default: return 'text-muted-foreground bg-muted border-border';
    }
  };

  const getFitLevelIcon = (level: string) => {
    switch (level) {
      case 'perfect': return <CheckCircle2 className="w-4 h-4" />;
      case 'good': return <CheckCircle2 className="w-4 h-4" />;
      case 'fair': return <AlertTriangle className="w-4 h-4" />;
      case 'poor': return <XCircle className="w-4 h-4" />;
      default: return null;
    }
  };

  return (
    <Card className="border-primary/30 shadow-sm overflow-hidden">
      <div className="bg-primary/5 border-b border-primary/10 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg font-semibold flex items-center gap-2">
              <Monitor className="w-5 h-5 text-primary" />
              {t('title')}
            </CardTitle>
            <CardDescription className="mt-1">{t('description')}</CardDescription>
          </div>
          <Badge variant="outline" className="bg-background/50 backdrop-blur">
            {t('localModeOnly')}
          </Badge>
        </div>
      </div>

      <CardContent className="p-0">
        {/* 硬件信息展示 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-6 bg-muted/30 border-b border-border/50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-background rounded-md border shadow-sm">
              <Cpu className="w-4 h-4 text-muted-foreground" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">{t('cpuArch')}</div>
              <div className="font-medium text-sm">{profile.cpu_arch || 'Unknown'} ({profile.os_type})</div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-background rounded-md border shadow-sm">
              <HardDrive className="w-4 h-4 text-muted-foreground" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">{t('memory')}</div>
              <div className="font-medium text-sm">{profile.total_ram_gb} GB {profile.is_unified_memory ? t('unified') : 'RAM'}</div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-background rounded-md border shadow-sm">
              <Monitor className="w-4 h-4 text-muted-foreground" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">{t('gpu')}</div>
              <div className="font-medium text-sm truncate max-w-[150px]" title={profile.gpu_name || t('noGpu')}>
                {profile.gpu_name || t('noGpu')}
              </div>
              {profile.gpu_vram_gb && !profile.is_unified_memory && (
                <div className="text-xs text-muted-foreground">{profile.gpu_vram_gb} GB VRAM</div>
              )}
            </div>
          </div>
        </div>

        {/* 推荐列表 */}
        <div className="p-6 space-y-4">
          <h4 className="text-sm font-medium text-muted-foreground mb-3">{t('recommendedModels')}</h4>
          
          <div className="grid gap-3">
            {profile.recommendations.map((rec, idx) => (
              <div 
                key={rec.model_id} 
                className={`flex flex-col sm:flex-row items-start sm:items-center justify-between p-4 rounded-lg border transition-all ${
                  idx === 0 ? 'bg-primary/5 border-primary/30 shadow-sm' : 'bg-background hover:bg-muted/50'
                }`}
              >
                <div className="space-y-1.5 flex-1 pr-4">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{rec.name}</span>
                    {idx === 0 && (
                      <Badge className="bg-primary text-primary-foreground text-[10px] px-1.5 py-0 h-5">
                        {t('bestFit')}
                      </Badge>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground line-clamp-1">{rec.description}</p>
                  <div className="flex items-center gap-4 text-xs">
                    <span className="flex items-center gap-1 text-muted-foreground">
                      <HardDrive className="w-3 h-3" />
                      {t('reqVram')}: {rec.req_vram_gb} GB
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-4 mt-4 sm:mt-0 w-full sm:w-auto">
                  <div className="flex flex-col items-end gap-1 min-w-[100px]">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-medium">Fit Score:</span>
                      <span className={`text-sm font-bold ${getFitLevelColor(rec.fit_level).split(' ')[0]}`}>
                        {rec.fit_score}%
                      </span>
                    </div>
                    <Progress 
                      value={rec.fit_score} 
                      className="h-1.5 w-24" 
                      indicatorClassName={
                        rec.fit_level === 'perfect' || rec.fit_level === 'good' ? 'bg-green-500' :
                        rec.fit_level === 'fair' ? 'bg-yellow-500' : 'bg-red-500'
                      }
                    />
                  </div>
                  
                  <Button 
                    size="sm" 
                    variant={idx === 0 ? "default" : "outline"}
                    className="shrink-0"
                    disabled={rec.fit_level === 'poor'}
                    onClick={() => onApplyModel(rec.model_id)}
                  >
                    <Download className="w-3.5 h-3.5 mr-1.5" />
                    {t('apply')}
                  </Button>
                </div>
              </div>
            ))}
          </div>
          
          {profile.recommendations.some(r => r.fit_level === 'poor') && (
            <Alert variant="destructive" className="mt-4 bg-red-500/5 border-red-500/20 text-red-600 dark:text-red-400">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>{t('warningTitle')}</AlertTitle>
              <AlertDescription className="text-xs mt-1">
                {t('warningDesc')}
              </AlertDescription>
            </Alert>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
