import { z } from 'zod';

/**
 * [POS] Universal Intent Protocol (UIP) Schema Definition.
 * Defines the strict whitelist and validation rules for all supported deep links.
 */

// Base intent type
export const BaseIntentSchema = z.object({
  scheme: z.enum(['myrmagent', 'https', 'http']),
  action: z.string(),
});

// 1. Chat Navigation Intent: myrmagent://chat/{id}
export const ChatIntentSchema = BaseIntentSchema.extend({
  action: z.literal('chat'),
  id: z.string().min(1, 'Chat ID is required'),
});

// 2. Agent Navigation Intent: myrmagent://agent/{id}
export const AgentIntentSchema = BaseIntentSchema.extend({
  action: z.literal('agent'),
  id: z.string().min(1, 'Agent ID is required'),
});

// 3. Quick Ask Intent: myrmagent://ask?text={query}
export const QuickAskIntentSchema = BaseIntentSchema.extend({
  action: z.literal('ask'),
  text: z.string().min(1, 'Query text is required'),
});

// 4. OAuth Callback Intent: myrmagent://oauth/callback?token={token}
export const OAuthIntentSchema = BaseIntentSchema.extend({
  action: z.literal('oauth'),
  path: z.literal('callback'),
  token: z.string().min(1, 'Token is required'),
});

// 5. Install Skill Intent: myrmagent://install-skill?url={url}
export const InstallSkillIntentSchema = BaseIntentSchema.extend({
  action: z.literal('install-skill'),
  url: z.string().url('Valid URL is required'),
});

// Union of all supported intents
export const UIPIntentSchema = z.discriminatedUnion('action', [
  ChatIntentSchema,
  AgentIntentSchema,
  QuickAskIntentSchema,
  OAuthIntentSchema,
  InstallSkillIntentSchema,
]);

export type UIPIntent = z.infer<typeof UIPIntentSchema>;

/**
 * Parses a raw URL string into a strongly-typed UIP Intent.
 * Throws an error if the URL is invalid or the intent is not whitelisted.
 */
export function parseIntentUrl(rawUrl: string): UIPIntent {
  try {
    const url = new URL(rawUrl);

    // For myrmagent://chat/123, url.hostname is 'chat', url.pathname is '/123'
    // For myrmagent://ask?text=hi, url.hostname is 'ask', url.pathname is ''
    // For https://app.myrmagent.com/intent/chat/123, we need to extract from pathname

    let scheme = url.protocol.replace(':', '');
    let action = '';
    let id = '';
    let path = '';

    if (scheme === 'myrmagent') {
      action = url.hostname;
      // Remove leading slash if present
      const pathParts = url.pathname.split('/').filter(Boolean);
      if (pathParts.length > 0) {
        if (action === 'oauth') {
          path = pathParts[0];
        } else {
          id = pathParts[0];
        }
      }
    } else if (scheme === 'http' || scheme === 'https') {
      // Handle Web/SaaS deep links: /intent/<action>/<id>
      const pathParts = url.pathname.split('/').filter(Boolean);
      if (pathParts[0] === 'intent' && pathParts.length >= 2) {
        action = pathParts[1];
        if (pathParts.length > 2) {
          if (action === 'oauth') {
            path = pathParts[2];
          } else {
            id = pathParts[2];
          }
        }
      } else {
        throw new Error('Not a valid intent URL path');
      }
    } else {
      throw new Error(`Unsupported scheme: ${scheme}`);
    }

    const basePayload = { scheme, action };

    switch (action) {
      case 'chat':
        return ChatIntentSchema.parse({ ...basePayload, id });
      case 'agent':
        return AgentIntentSchema.parse({ ...basePayload, id });
      case 'ask':
        return QuickAskIntentSchema.parse({
          ...basePayload,
          text: url.searchParams.get('text') || '',
        });
      case 'oauth':
        return OAuthIntentSchema.parse({
          ...basePayload,
          path,
          token: url.searchParams.get('token') || '',
        });
      case 'install-skill':
        return InstallSkillIntentSchema.parse({
          ...basePayload,
          url: url.searchParams.get('url') || '',
        });
      default:
        throw new Error(`Unsupported action: ${action}`);
    }
  } catch (error) {
    console.error('[UIP] Failed to parse intent URL:', rawUrl, error);
    throw error;
  }
}
