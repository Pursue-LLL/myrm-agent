'use client';

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { RefreshCw, AlertCircle, FileX, ServerCrash, WifiOff, ShieldOff } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { ArtifactError, ArtifactErrorType } from '@/store/useArtifactPortalStore';

interface PortalErrorDisplayProps {
  error: ArtifactError;
  onRetry: () => void;
  labels: {
    message: string;
    httpStatus: string;
    retry: string;
    hint: string;
  };
}

/** 获取错误图标 */
function getErrorIcon(type: ArtifactErrorType) {
  switch (type) {
    case ArtifactErrorType.NotFound:
      return FileX;
    case ArtifactErrorType.ServerError:
      return ServerCrash;
    case ArtifactErrorType.NetworkError:
      return WifiOff;
    case ArtifactErrorType.PermissionDenied:
      return ShieldOff;
    default:
      return AlertCircle;
  }
}

/** 获取错误背景色 */
function getErrorBgClass(type: ArtifactErrorType): string {
  switch (type) {
    case ArtifactErrorType.NotFound:
      return 'bg-yellow-100 dark:bg-yellow-900/30';
    case ArtifactErrorType.ServerError:
      return 'bg-red-100 dark:bg-red-900/30';
    case ArtifactErrorType.NetworkError:
      return 'bg-orange-100 dark:bg-orange-900/30';
    case ArtifactErrorType.PermissionDenied:
      return 'bg-purple-100 dark:bg-purple-900/30';
    default:
      return 'bg-gray-100 dark:bg-gray-800';
  }
}

/** 获取错误图标色 */
function getErrorIconClass(type: ArtifactErrorType): string {
  switch (type) {
    case ArtifactErrorType.NotFound:
      return 'text-yellow-600 dark:text-yellow-400';
    case ArtifactErrorType.ServerError:
      return 'text-red-600 dark:text-red-400';
    case ArtifactErrorType.NetworkError:
      return 'text-orange-600 dark:text-orange-400';
    case ArtifactErrorType.PermissionDenied:
      return 'text-purple-600 dark:text-purple-400';
    default:
      return 'text-gray-600 dark:text-gray-400';
  }
}

/** Portal 错误显示 */
const PortalErrorDisplay: React.FC<PortalErrorDisplayProps> = ({ error, onRetry, labels }) => {
  const ErrorIcon = getErrorIcon(error.type);

  return (
    <div className="flex flex-col items-center justify-center h-full p-6 text-center">
      <div className={cn('w-16 h-16 rounded-full flex items-center justify-center mb-4', getErrorBgClass(error.type))}>
        <ErrorIcon className={cn('w-8 h-8', getErrorIconClass(error.type))} />
      </div>

      <h3 className="text-lg font-semibold text-foreground mb-2">{labels.message}</h3>

      {error.statusCode && (
        <p className="text-sm text-muted-foreground mb-2">
          {labels.httpStatus}: {error.statusCode}
        </p>
      )}

      {error.details && (
        <p className="text-xs text-muted-foreground mb-4 max-w-md break-all">
          {error.details.length > 200 ? `${error.details.slice(0, 200)}...` : error.details}
        </p>
      )}

      {error.retryable && (
        <Button variant="outline" size="sm" onClick={onRetry} className="gap-2">
          <RefreshCw className="w-4 h-4" />
          {labels.retry}
        </Button>
      )}

      <p className="text-xs text-muted-foreground mt-4">{labels.hint}</p>
    </div>
  );
};

export default PortalErrorDisplay;
