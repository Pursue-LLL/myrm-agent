/**
 * [INPUT]
 * @/services/api::apiClient (POS: centralized frontend API client adapter)
 *
 * [OUTPUT]
 * - DevPortInfo: Active listening port detail
 * - DevPortRegisterRequest: Request payload to register listening port
 * - DevPortTunnelResponse: Response payload for public preview tunnel
 * - DevPortSniffRequest: Request payload for sniffing listening ports from raw text
 * - listDevPorts: Async function to fetch all listening dev ports
 * - registerDevPort: Async function to register a new dev port
 * - closeDevPort: Async function to terminate a dev port process
 * - createDevPortTunnel: Async function to generate public preview tunnel
 * - sniffAndRegisterDevPorts: Async function to auto-detect and register dev ports from logs
 *
 * [POS]
 * Client service layer for DevPortsListeningBarAndServicePreviewHub.
 * Single file < 100 lines. Zero `any` types.
 */

import { apiClient } from './api';

export interface DevPortInfo {
  port: number;
  process_name: string;
  pid?: number | null;
  protocol: string;
  url: string;
  tunnel_url?: string | null;
  status: 'listening' | 'starting' | 'stopped';
  created_at: string;
}

export interface DevPortRegisterRequest {
  port: number;
  process_name: string;
  pid?: number | null;
  protocol?: string;
}

export interface DevPortTunnelResponse {
  port: number;
  tunnel_url: string;
  expires_in_seconds: number;
}

export interface DevPortSniffRequest {
  log_text: string;
}

const DEV_PORTS_BASE = '/api/v1/dev-ports';

export async function listDevPorts(): Promise<DevPortInfo[]> {
  return apiClient.get<DevPortInfo[]>(DEV_PORTS_BASE);
}

export async function registerDevPort(
  payload: DevPortRegisterRequest,
): Promise<DevPortInfo> {
  return apiClient.post<DevPortInfo>(DEV_PORTS_BASE, payload);
}

export async function closeDevPort(port: number): Promise<{ success: boolean }> {
  return apiClient.delete<{ success: boolean }>(`${DEV_PORTS_BASE}/${port}`);
}

export async function createDevPortTunnel(
  port: number,
): Promise<DevPortTunnelResponse> {
  return apiClient.post<DevPortTunnelResponse>(`${DEV_PORTS_BASE}/${port}/tunnel`);
}

export async function sniffAndRegisterDevPorts(
  logText: string,
): Promise<DevPortInfo[]> {
  return apiClient.post<DevPortInfo[]>(`${DEV_PORTS_BASE}/sniff`, { log_text: logText });
}
