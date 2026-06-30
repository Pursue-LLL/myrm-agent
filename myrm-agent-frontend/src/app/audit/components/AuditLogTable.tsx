'use client';

import { useState, useEffect } from 'react';
import { useLocale } from 'next-intl';
import { format } from 'date-fns';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/primitives/table';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import { Loader2, Download, Search, RefreshCw } from 'lucide-react';
import { localizeReactNode } from '@/lib/utils/localeText';

interface BashAuditLog {
  sequence: number;
  timestamp: number;
  command: string;
  exit_code: number;
  stdout: string;
  stderr: string;
  duration_ms: number;
  success: boolean;
  command_type: string;
  risk_level: string;
  error_message?: string;
}

const AuditLogTable = () => {
  const locale = useLocale();
  const [logs, setLogs] = useState<BashAuditLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [commandTypeFilter, setCommandTypeFilter] = useState<string>('all');
  const [riskLevelFilter, setRiskLevelFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedLog, setSelectedLog] = useState<BashAuditLog | null>(null);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (commandTypeFilter !== 'all') params.append('command_type', commandTypeFilter);
      if (riskLevelFilter !== 'all') params.append('risk_level', riskLevelFilter);
      params.append('limit', '100');

      const response = await fetch(`/api/v1/audit/bash/logs?${params.toString()}`);
      if (!response.ok) throw new Error('Failed to fetch audit logs');

      const data = await response.json();
      setLogs(data);
    } catch (error) {
      console.error('Error fetching audit logs:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [commandTypeFilter, riskLevelFilter]);

  const exportLogs = async (format: 'json' | 'csv') => {
    try {
      const response = await fetch(`/api/v1/audit/bash/export?format=${format}`);
      if (!response.ok) throw new Error('Failed to export logs');

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `bash-audit-logs-${Date.now()}.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Error exporting logs:', error);
    }
  };

  const filteredLogs = logs.filter((log) => log.command.toLowerCase().includes(searchQuery.toLowerCase()));

  const getRiskBadgeVariant = (risk: string): 'default' | 'destructive' | 'secondary' => {
    switch (risk) {
      case 'HIGH':
        return 'destructive';
      case 'MEDIUM':
        return 'default';
      default:
        return 'secondary';
    }
  };

  const viewDetails = async (log: BashAuditLog) => {
    // 如果输出已经很短（<500字符），直接显示
    const totalLen = log.stdout.length + log.stderr.length;
    if (totalLen < 500) {
      setSelectedLog(log);
      setDetailDialogOpen(true);
      return;
    }

    // 否则，请求完整输出
    try {
      const params = new URLSearchParams();
      params.append('truncate', 'false');
      params.append('limit', '1');
      params.append('start_sequence', log.sequence.toString());

      const response = await fetch(`/api/v1/audit/bash/logs?${params.toString()}`);
      if (!response.ok) throw new Error('Failed to fetch full log');

      const data = await response.json();
      if (data.length > 0) {
        setSelectedLog(data[0]);
      } else {
        setSelectedLog(log);
      }
      setDetailDialogOpen(true);
    } catch (error) {
      console.error('Error fetching full log:', error);
      setSelectedLog(log);
      setDetailDialogOpen(true);
    }
  };

  return localizeReactNode(
    <Card>
      <CardHeader>
        <CardTitle>Bash Audit Logs / Bash审计日志</CardTitle>
        <CardDescription>View and filter bash command execution history / 查看和筛选bash命令执行历史</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="mb-4 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:gap-2">
            <div className="relative flex-1 md:w-64">
              <Search className="absolute left-2 top-2.5 size-4 text-muted-foreground" />
              <Input
                placeholder="Search commands / 搜索命令..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8"
              />
            </div>
            <Select value={commandTypeFilter} onValueChange={setCommandTypeFilter}>
              <SelectTrigger className="w-full md:w-40">
                <SelectValue placeholder="Command Type / 类型" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Types / 全部</SelectItem>
                <SelectItem value="READ">READ / 读取</SelectItem>
                <SelectItem value="WRITE">WRITE / 写入</SelectItem>
                <SelectItem value="SEARCH">SEARCH / 搜索</SelectItem>
                <SelectItem value="NETWORK">NETWORK / 网络</SelectItem>
                <SelectItem value="GIT">GIT</SelectItem>
                <SelectItem value="PYTHON">PYTHON</SelectItem>
                <SelectItem value="DANGEROUS">DANGEROUS / 危险</SelectItem>
              </SelectContent>
            </Select>
            <Select value={riskLevelFilter} onValueChange={setRiskLevelFilter}>
              <SelectTrigger className="w-full md:w-40">
                <SelectValue placeholder="Risk Level / 风险" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Levels / 全部</SelectItem>
                <SelectItem value="LOW">LOW / 低</SelectItem>
                <SelectItem value="MEDIUM">MEDIUM / 中</SelectItem>
                <SelectItem value="HIGH">HIGH / 高</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={fetchLogs} disabled={loading}>
              <RefreshCw className={`mr-2 size-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh / 刷新
            </Button>
            <Button variant="outline" size="sm" onClick={() => exportLogs('json')}>
              <Download className="mr-2 size-4" />
              JSON
            </Button>
            <Button variant="outline" size="sm" onClick={() => exportLogs('csv')}>
              <Download className="mr-2 size-4" />
              CSV
            </Button>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="size-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Time / 时间</TableHead>
                  <TableHead>Command / 命令</TableHead>
                  <TableHead>Type / 类型</TableHead>
                  <TableHead>Risk / 风险</TableHead>
                  <TableHead>Status / 状态</TableHead>
                  <TableHead className="text-right">Duration / 耗时</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredLogs.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center text-muted-foreground">
                      No audit logs found / 未找到审计日志
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredLogs.map((log) => (
                    <TableRow
                      key={log.sequence}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => viewDetails(log)}
                    >
                      <TableCell className="whitespace-nowrap">
                        {format(new Date(log.timestamp * 1000), 'yyyy-MM-dd HH:mm:ss')}
                      </TableCell>
                      <TableCell className="max-w-md truncate font-mono text-sm">{log.command}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{log.command_type}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={getRiskBadgeVariant(log.risk_level)}>{log.risk_level}</Badge>
                      </TableCell>
                      <TableCell>
                        {log.success ? (
                          <Badge variant="secondary" className="bg-green-100 text-green-800">
                            Success / 成功
                          </Badge>
                        ) : (
                          <Badge variant="destructive">Failed / 失败</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right font-mono text-sm">{log.duration_ms}ms</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        )}

        {/* 详情对话框 */}
        <Dialog open={detailDialogOpen} onOpenChange={setDetailDialogOpen}>
          <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Command Execution Details / 命令执行详情</DialogTitle>
              <DialogDescription>
                Sequence: {selectedLog?.sequence} | Time:{' '}
                {selectedLog && format(new Date(selectedLog.timestamp * 1000), 'yyyy-MM-dd HH:mm:ss')}
              </DialogDescription>
            </DialogHeader>
            {selectedLog && (
              <div className="space-y-4">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-sm font-semibold">Command / 命令:</span>
                    <Badge variant="outline">{selectedLog.command_type}</Badge>
                    <Badge variant={getRiskBadgeVariant(selectedLog.risk_level)}>{selectedLog.risk_level}</Badge>
                  </div>
                  <pre className="bg-muted p-3 rounded-md font-mono text-sm overflow-x-auto">
                    {selectedLog.command}
                  </pre>
                </div>

                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-sm font-semibold">Status / 状态:</span>
                    {selectedLog.success ? (
                      <Badge variant="secondary" className="bg-green-100 text-green-800">
                        Success / 成功
                      </Badge>
                    ) : (
                      <Badge variant="destructive">Failed / 失败</Badge>
                    )}
                  </div>
                  <div className="text-sm text-muted-foreground">
                    Exit Code: {selectedLog.exit_code} | Duration: {selectedLog.duration_ms}ms
                  </div>
                </div>

                {selectedLog.stdout && (
                  <div>
                    <span className="text-sm font-semibold">Standard Output:</span>
                    <pre className="mt-2 bg-muted p-3 rounded-md font-mono text-xs overflow-x-auto max-h-60">
                      {selectedLog.stdout}
                    </pre>
                  </div>
                )}

                {selectedLog.stderr && (
                  <div>
                    <span className="text-sm font-semibold text-destructive">Standard Error:</span>
                    <pre className="mt-2 bg-destructive/10 p-3 rounded-md font-mono text-xs overflow-x-auto max-h-60">
                      {selectedLog.stderr}
                    </pre>
                  </div>
                )}

                {selectedLog.error_message && (
                  <div>
                    <span className="text-sm font-semibold text-destructive">Error Message:</span>
                    <pre className="mt-2 bg-destructive/10 p-3 rounded-md font-mono text-xs overflow-x-auto">
                      {selectedLog.error_message}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </DialogContent>
        </Dialog>
      </CardContent>
    </Card>,
    locale,
  );
};

export default AuditLogTable;
