/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 * ./service::buildWikiApiPath, WikiMaintainResponse (POS: Wiki API 路径构造 / 维护结果 DTO)
 *
 * [OUTPUT]
 * startWikiMaintain / getWikiMaintainStatus / cancelWikiMaintain: 后台维护运行的启动、状态查询与取消。
 * WikiMaintainMode / WikiMaintainPhase / WikiMaintainProgress / WikiMaintainStatus: 运行状态 DTO。
 *
 * [POS]
 * Wiki 维护运行客户端。`POST /wiki/maintain`（202，启动或加入进行中的运行）、`GET /wiki/maintain/status` 与
 * `POST /wiki/maintain/cancel`（幂等）REST 契约；全量维护要数分钟，所以启动请求立即返回，调用方轮询状态直到结束。
 */

import { apiRequest } from '@/lib/api';
import { buildWikiApiPath, type WikiMaintainResponse } from './service';

export type WikiMaintainMode = 'structural' | 'full';

export type WikiMaintainPhase = 'drift_review' | 'link_discovery';

/** Pages of one model phase that are done, as reported while a full maintenance run is in flight. */
export interface WikiMaintainProgress {
  phase: WikiMaintainPhase;
  done: number;
  total: number;
}

export interface WikiMaintainStatus {
  state: 'idle' | 'running' | 'succeeded' | 'cancelled' | 'failed';
  mode: WikiMaintainMode | null;
  phase: WikiMaintainPhase | null;
  done: number;
  total: number;
  /** The user asked to stop and the run is still winding down. */
  cancel_requested: boolean;
  /** Present once the run has ended, partial when it was cancelled. */
  result: WikiMaintainResponse | null;
  /** Present once the run has failed; never carries the technical cause. */
  error_code: 'maintain_failed' | 'maintain_timeout' | 'compile_in_progress' | null;
}

/** Starts a run in the background, or joins the run already in flight; follow it with getWikiMaintainStatus. */
export async function startWikiMaintain(mode: WikiMaintainMode, agentId?: string | null): Promise<WikiMaintainStatus> {
  const params = new URLSearchParams({ mode });
  return apiRequest<WikiMaintainStatus>(buildWikiApiPath(`/wiki/maintain?${params.toString()}`, agentId), {
    method: 'POST',
  });
}

export async function getWikiMaintainStatus(agentId?: string | null): Promise<WikiMaintainStatus> {
  return apiRequest<WikiMaintainStatus>(buildWikiApiPath('/wiki/maintain/status', agentId));
}

/** Asks the run in flight to stop between model calls; what it already wrote stays. Repeating it changes nothing. */
export async function cancelWikiMaintain(agentId?: string | null): Promise<WikiMaintainStatus> {
  return apiRequest<WikiMaintainStatus>(buildWikiApiPath('/wiki/maintain/cancel', agentId), { method: 'POST' });
}
