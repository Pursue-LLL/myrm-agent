/**
 * Client-side Service for Agent Avatar Generation & Lock Persistence.
 *
 * [INPUT] avatarTypes, avatarGenerator
 * [OUTPUT] avatarService: Unified API service with offline deterministic fallbacks.
 * [POS] src/components/features/agent-avatar/avatarService.ts
 */

import type {
  AvatarMetadata,
  AvatarStyle,
  GenerateAiAvatarRequest,
  GenerateSvgRequest,
} from './avatarTypes';
import { generateDeterministicSvg } from './avatarGenerator';

class AvatarService {
  private readonly baseUrl = '/api/v1/agents/avatar';

  async generateSvg(req: GenerateSvgRequest): Promise<string> {
    const style: AvatarStyle = req.style ?? 'beam';
    const bg = req.backgroundColor ?? '#6366f1';

    try {
      const res = await fetch(`${this.baseUrl}/generate-svg`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          seed: req.seed,
          style,
          background_color: bg,
        }),
      });
      if (res.ok) {
        const data = (await res.json()) as { svg_data: string };
        return data.svg_data;
      }
    } catch {
      // Offline fallback
    }

    return generateDeterministicSvg(req.seed, style, bg);
  }

  async generateAiAvatar(req: GenerateAiAvatarRequest): Promise<string> {
    try {
      const res = await fetch(`${this.baseUrl}/generate-ai`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: req.prompt,
          style: req.style ?? 'photorealistic',
        }),
      });
      if (res.ok) {
        const data = (await res.json()) as { image_url: string };
        return data.image_url;
      }
    } catch {
      // Offline fallback
    }

    const safeHash = Math.abs(req.prompt.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0));
    return `https://api.dicebear.com/7.x/bottts/svg?seed=${safeHash}`;
  }

  async setAgentAvatar(
    agentId: string,
    metadata: AvatarMetadata,
  ): Promise<AvatarMetadata> {
    try {
      const res = await fetch(`${this.baseUrl}/${agentId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          seed: metadata.seed,
          style: metadata.style,
          background_color: metadata.backgroundColor,
          is_locked: metadata.isLocked,
          svg_data: metadata.svgData,
          image_url: metadata.imageUrl ?? null,
        }),
      });
      if (res.ok) {
        const data = (await res.json()) as {
          seed: string;
          style: AvatarStyle;
          background_color: string;
          is_locked: boolean;
          svg_data: string;
          image_url?: string | null;
        };
        return {
          seed: data.seed,
          style: data.style,
          backgroundColor: data.background_color,
          isLocked: data.is_locked,
          svgData: data.svg_data,
          imageUrl: data.image_url,
        };
      }
    } catch {
      // Return metadata as-is if network request fails
    }

    return metadata;
  }

  async getAgentAvatar(agentId: string): Promise<AvatarMetadata> {
    try {
      const res = await fetch(`${this.baseUrl}/${agentId}`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      });
      if (res.ok) {
        const data = (await res.json()) as {
          seed: string;
          style: AvatarStyle;
          background_color: string;
          is_locked: boolean;
          svg_data: string;
          image_url?: string | null;
        };
        return {
          seed: data.seed,
          style: data.style,
          backgroundColor: data.background_color,
          isLocked: data.is_locked,
          svgData: data.svg_data,
          imageUrl: data.image_url,
        };
      }
    } catch {
      // Offline fallback
    }

    const defaultSvg = generateDeterministicSvg(agentId, 'beam', '#6366f1');
    return {
      seed: agentId,
      style: 'beam',
      backgroundColor: '#6366f1',
      isLocked: false,
      svgData: defaultSvg,
    };
  }
}

export const avatarService = new AvatarService();
