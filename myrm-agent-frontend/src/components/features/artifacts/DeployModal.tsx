'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Label } from '@/components/primitives/label';
import { Loader2, Globe, CheckCircle2, XCircle, Copy, ExternalLink } from 'lucide-react';
import { Artifact } from '@/store/chat/types';
import { writeToClipboard } from '@/lib/utils/clipboardUtils';
import { getApiUrl } from '@/lib/api';

interface DeployModalProps {
  artifact: Artifact;
  open: boolean;
  onClose: () => void;
}

export const DeployModal: React.FC<DeployModalProps> = ({ artifact, open, onClose }) => {
  const [token, setToken] = useState('');
  const [status, setStatus] = useState<'IDLE' | 'DEPLOYING' | 'SUCCESS' | 'ERROR'>('IDLE');
  const [logs, setLogs] = useState<string[]>([]);
  const [deployUrl, setDeployUrl] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [copied, setCopied] = useState(false);
  const isIntentionalClose = useRef(false);

  // Load token from local storage on mount
  useEffect(() => {
    const savedToken = localStorage.getItem('vercel_token');
    if (savedToken) {
      setToken(savedToken);
    }
  }, []);

  const handleDeploy = async () => {
    if (!token) {
      setErrorMsg('Please enter your Vercel token');
      return;
    }

    // Save token
    localStorage.setItem('vercel_token', token);
    
    setStatus('DEPLOYING');
    setLogs(['Initiating deployment...']);
    setErrorMsg('');
    isIntentionalClose.current = false;

    try {
      // 1. Call POST /api/v1/artifacts/{id}/deploy
      const response = await fetch(getApiUrl(`/api/v1/artifacts/${artifact.id}/deploy`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ token, platform: 'vercel' }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Deployment failed');
      }

      const data = await response.json();
      const deploymentId = data.deployment_id;
      
      if (!deploymentId) {
        throw new Error('No deployment ID returned');
      }

      setLogs((prev) => [...prev, `Deployment created: ${deploymentId}`, 'Connecting to build logs...']);

      // 2. Connect to WebSocket for status updates
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsHost = getApiUrl('').replace(/^https?:\/\//, '');
      const wsUrl = `${wsProtocol}//${wsHost}/api/v1/artifacts/${artifact.id}/deploy/status/${deploymentId}`;
      
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        // Send auth payload as first message to avoid token in URL logs
        ws.send(JSON.stringify({ type: 'auth', token }));
      };

      ws.onmessage = (event) => {
        const statusData = JSON.parse(event.data);
        const currentStatus = statusData.status;
        
        setLogs((prev) => [...prev, `Status: ${currentStatus}`]);

        if (currentStatus === 'READY') {
          setStatus('SUCCESS');
          setDeployUrl(statusData.url);
          isIntentionalClose.current = true;
          ws.close();
        } else if (currentStatus === 'ERROR' || currentStatus === 'CANCELED') {
          setStatus('ERROR');
          setErrorMsg(`Deployment ${currentStatus.toLowerCase()}`);
          isIntentionalClose.current = true;
          ws.close();
        }
      };

      ws.onclose = (event) => {
        // If the connection closes unexpectedly while still deploying
        setStatus((currentStatus) => {
          if (currentStatus === 'DEPLOYING' && !isIntentionalClose.current) {
            setErrorMsg('Network connection lost. Please refresh to check deployment status.');
            return 'ERROR';
          }
          return currentStatus;
        });
      };

      ws.onerror = () => {
        setLogs((prev) => [...prev, 'WebSocket connection error']);
      };

    } catch (error: unknown) {
      setStatus('ERROR');
      const errorMessage = error instanceof Error ? error.message : 'An unexpected error occurred';
      setErrorMsg(errorMessage);
      setLogs((prev) => [...prev, `Error: ${errorMessage}`]);
    }
  };

  const handleCopy = async () => {
    if (!deployUrl) return;
    try {
      await writeToClipboard(deployUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy', err);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="sm:max-w-md bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 shadow-2xl overflow-hidden">
        {/* Decorative background gradient */}
        <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-transparent pointer-events-none" />
        
        <DialogHeader className="relative z-10">
          <DialogTitle className="flex items-center gap-2 text-xl font-semibold">
            <div className="p-2 bg-primary/10 rounded-lg text-primary">
              <Globe className="w-5 h-5" />
            </div>
            Deploy to Web
          </DialogTitle>
          <DialogDescription className="pt-2">
            Publish your artifact instantly to the global edge network using Vercel.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4 relative z-10">
          {status === 'IDLE' && (
            <div className="space-y-5 animate-in fade-in slide-in-from-bottom-4 duration-500">
              <div className="space-y-2">
                <Label htmlFor="token" className="text-sm font-medium">Vercel Personal Access Token</Label>
                <Input
                  id="token"
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="Enter your Vercel token"
                  className="w-full font-mono text-sm bg-gray-50 dark:bg-gray-950 border-gray-200 dark:border-gray-800 focus-visible:ring-primary"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Securely stored in your browser. Get one from your{' '}
                  <a href="https://vercel.com/account/tokens" target="_blank" rel="noreferrer" className="text-primary hover:underline">
                    Vercel Account Settings
                  </a>.
                </p>
              </div>
              {errorMsg && <p className="text-sm text-red-500 bg-red-50 dark:bg-red-950/50 p-2 rounded-md border border-red-100 dark:border-red-900">{errorMsg}</p>}
              <Button onClick={handleDeploy} className="w-full shadow-lg shadow-primary/20 transition-all hover:scale-[1.02]" disabled={!token}>
                Deploy Now
              </Button>
            </div>
          )}

          {status === 'DEPLOYING' && (
            <div className="space-y-5 animate-in fade-in zoom-in-95 duration-300">
              <div className="flex flex-col items-center justify-center py-6 gap-4">
                <div className="relative">
                  <div className="absolute inset-0 bg-primary/20 rounded-full blur-xl animate-pulse" />
                  <Loader2 className="w-10 h-10 animate-spin text-primary relative z-10" />
                </div>
                <p className="text-sm font-medium text-gray-600 dark:text-gray-300 animate-pulse">Building and deploying...</p>
              </div>
              <div className="bg-gray-950 text-gray-300 p-4 rounded-lg h-40 overflow-y-auto font-mono text-xs shadow-inner border border-gray-800 scrollbar-thin scrollbar-thumb-gray-700">
                {logs.map((log, i) => (
                  <div key={i} className="mb-1 opacity-80 hover:opacity-100 transition-opacity">
                    <span className="text-gray-500 mr-2">[{new Date().toLocaleTimeString()}]</span>
                    {log}
                  </div>
                ))}
              </div>
            </div>
          )}

          {status === 'SUCCESS' && (
            <div className="space-y-6 text-center animate-in fade-in zoom-in-95 duration-500">
              <div className="flex justify-center">
                <div className="relative">
                  <div className="absolute inset-0 bg-green-500/20 rounded-full blur-xl animate-pulse" />
                  <CheckCircle2 className="w-16 h-16 text-green-500 relative z-10" />
                </div>
              </div>
              <div>
                <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Deployment Successful!</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">Your app is now live on the global edge network.</p>
              </div>
              
              <div className="flex items-center gap-2 p-2 bg-gray-50 dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-xl shadow-sm">
                <Input 
                  value={deployUrl} 
                  readOnly 
                  className="bg-transparent border-none focus-visible:ring-0 font-mono text-sm text-primary" 
                />
                <div className="flex gap-1 pr-1">
                  <Button size="icon" variant="ghost" onClick={handleCopy} className="hover:bg-gray-200 dark:hover:bg-gray-800 rounded-lg">
                    {copied ? <CheckCircle2 className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4 text-gray-500" />}
                  </Button>
                  <Button size="icon" variant="ghost" onClick={() => window.open(deployUrl, '_blank')} className="hover:bg-gray-200 dark:hover:bg-gray-800 rounded-lg">
                    <ExternalLink className="w-4 h-4 text-gray-500" />
                  </Button>
                </div>
              </div>
              
              <Button onClick={onClose} variant="outline" className="w-full hover:bg-gray-50 dark:hover:bg-gray-800">
                Done
              </Button>
            </div>
          )}

          {status === 'ERROR' && (
            <div className="space-y-5 text-center animate-in fade-in slide-in-from-bottom-4 duration-300">
              <div className="flex justify-center">
                <div className="p-3 bg-red-100 dark:bg-red-900/30 rounded-full">
                  <XCircle className="w-10 h-10 text-red-500" />
                </div>
              </div>
              <div>
                <h3 className="text-lg font-semibold text-red-500">Deployment Failed</h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mt-2 bg-red-50 dark:bg-red-950/30 p-3 rounded-lg border border-red-100 dark:border-red-900/50">
                  {errorMsg}
                </p>
              </div>
              <Button onClick={() => setStatus('IDLE')} variant="outline" className="w-full hover:bg-red-50 dark:hover:bg-red-950/30 hover:text-red-600 dark:hover:text-red-400 hover:border-red-200 dark:hover:border-red-900">
                Try Again
              </Button>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};
