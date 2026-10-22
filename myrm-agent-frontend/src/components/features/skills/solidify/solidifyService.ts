/**
 * Service for skill solidification.
 * Handles heuristic parameter minimization and communication with backend.
 */

import {
  ParameterExtractionRule,
  SolidifySkillRequestPayload,
  SolidifySkillResponseData,
} from './solidifyTypes';

export class SolidifyService {
  /**
   * Fast client-side parameter extraction heuristic adhering to parameter minimization.
   */
  public static extractParameters(content: string, type = 'html'): ParameterExtractionRule[] {
    const extracted: ParameterExtractionRule[] = [];
    const seen = new Set<string>();

    // 1. Check explicit {{variable}} slots
    const explicitRegex = /\{\{([a-zA-Z0-9_\u4e00-\u9fa5]+)\}\}/g;
    let match: RegExpExecArray | null = explicitRegex.exec(content);
    while (match !== null) {
      const key = match[1].trim();
      if (key && !seen.has(key)) {
        seen.add(key);
        extracted.push({
          name: key,
          description: `可变插值槽位: ${key}`,
          defaultValue: '',
          placeholderPattern: `{{${key}}}`,
          required: true,
        });
      }
      match = explicitRegex.exec(content);
    }

    if (extracted.length > 0) {
      return extracted;
    }

    // 2. Heuristic extraction for HTML
    if (type.toLowerCase() === 'html') {
      const titleMatch = /<title>(.*?)<\/title>/i.exec(content);
      if (titleMatch && titleMatch[1].trim()) {
        const titleVal = titleMatch[1].trim();
        seen.add('topic');
        extracted.push({
          name: 'topic',
          description: '课件/页面核心主题',
          defaultValue: titleVal,
          placeholderPattern: '{{topic}}',
          required: true,
        });
      }

      const h1Match = /<h1[^>]*>(.*?)<\/h1>/i.exec(content);
      if (h1Match && h1Match[1].trim() && !seen.has('headline')) {
        const h1Val = h1Match[1].replace(/<[^>]+>/g, '').trim();
        if (h1Val && !seen.has('topic')) {
          seen.add('headline');
          extracted.push({
            name: 'headline',
            description: '主讲标题/核心知识点',
            defaultValue: h1Val,
            placeholderPattern: '{{headline}}',
            required: true,
          });
        }
      }
    }

    // 3. Fallback slot if none found
    if (extracted.length === 0) {
      extracted.push({
        name: 'topic',
        description: '任务主体与核心议题',
        defaultValue: '通用主题',
        placeholderPattern: '{{topic}}',
        required: true,
      });
    }

    return extracted;
  }

  /**
   * Request backend to solidify artifact into 4-in-1 standard skill bundle.
   */
  public static async solidifySkill(
    payload: SolidifySkillRequestPayload
  ): Promise<SolidifySkillResponseData> {
    const res = await fetch('/api/v1/skills/solidify', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        name: payload.name,
        display_title: payload.displayTitle,
        description: payload.description,
        category: payload.category,
        source_artifact_content: payload.sourceArtifactContent,
        source_artifact_type: payload.sourceArtifactType || 'html',
        custom_parameters: payload.customParameters?.map((p) => ({
          name: p.name,
          description: p.description,
          default_value: p.defaultValue,
          placeholder_pattern: p.placeholderPattern,
          required: p.required,
        })),
        include_plan_before_execute_hint: payload.includePlanBeforeExecuteHint ?? true,
      }),
    });

    if (!res.ok) {
      throw new Error(`Failed to solidify skill: ${res.statusText}`);
    }

    const data = await res.json();
    return {
      skillId: data.skill_id,
      name: data.name,
      displayTitle: data.display_title,
      description: data.description,
      parameters: (data.parameters || []).map((p: {
        name: string;
        description: string;
        default_value?: string;
        placeholder_pattern: string;
        required: boolean;
      }) => ({
        name: p.name,
        description: p.description,
        defaultValue: p.default_value,
        placeholderPattern: p.placeholder_pattern,
        required: p.required,
      })),
      bundleFiles: data.bundle_files || [],
      previewUrl: data.preview_url,
      createdAt: data.created_at,
    };
  }
}
