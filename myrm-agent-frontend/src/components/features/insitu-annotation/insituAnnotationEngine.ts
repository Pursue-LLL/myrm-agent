import {
  VisualCommentPin,
  ElementStylePatch,
  BatchAnnotationPayload,
} from './insituAnnotationTypes';

/**
 * 将多元素就地样式补丁编译为一段可注入 DOM 的 CSS 规则
 */
export function generateCssFromPatches(patches: ElementStylePatch[]): string {
  if (patches.length === 0) {
    return '';
  }

  const rules = patches.map((patch) => {
    const declarations: string[] = [];
    if (patch.color) {
      declarations.push(`color: ${patch.color} !important;`);
    }
    if (patch.backgroundColor) {
      declarations.push(`background-color: ${patch.backgroundColor} !important;`);
    }
    if (patch.fontSize) {
      declarations.push(`font-size: ${patch.fontSize} !important;`);
    }
    if (patch.padding) {
      declarations.push(`padding: ${patch.padding} !important;`);
    }

    if (declarations.length === 0) {
      return '';
    }

    return `${patch.selector} { ${declarations.join(' ')} }`;
  });

  return rules.filter(Boolean).join('\n');
}

/**
 * 将多点批注与就地补丁打包编译为结构化 Agent 修改协议 Prompt
 */
export function compileBatchAnnotationsPrompt(
  artifactId: string,
  comments: VisualCommentPin[],
  stylePatches: ElementStylePatch[]
): string {
  let prompt = `【工件画布多点精准修改需求包】\n工件 ID: ${artifactId}\n批注数量: ${comments.length} 处\n就地样式补丁: ${stylePatches.length} 处\n\n`;

  prompt += '--- 批注详细清单 ---\n';
  if (comments.length === 0) {
    prompt += '（无新悬浮批注）\n';
  } else {
    comments.forEach((c) => {
      prompt += `批注 [${c.index}] 目标元素: <${c.targetTag}> (Selector: "${c.selector}")\n`;
      if (c.targetPreviewSnippet) {
        prompt += `原元素片段: "${c.targetPreviewSnippet}"\n`;
      }
      prompt += `修改诉求: ${c.commentText}\n\n`;
    });
  }

  if (stylePatches.length > 0) {
    prompt += '--- 用户就地预览的样式补丁 (请直接固化至源代码) ---\n';
    stylePatches.forEach((p, idx) => {
      prompt += `补丁 [${idx + 1}] 目标: ${p.selector}\n`;
      if (p.textContent) {
        prompt += `- 文本内容改为: "${p.textContent}"\n`;
      }
      if (p.color) {
        prompt += `- 文字颜色: ${p.color}\n`;
      }
      if (p.backgroundColor) {
        prompt += `- 背景颜色: ${p.backgroundColor}\n`;
      }
      if (p.fontSize) {
        prompt += `- 字号: ${p.fontSize}\n`;
      }
      if (p.padding) {
        prompt += `- 内边距: ${p.padding}\n`;
      }
      prompt += '\n';
    });
  }

  prompt += '请严格根据上述批注和就地补丁，在保持其他未批注部分完全不变的前提下，一次性完成所有局部修改并输出最终完整工件代码。';

  return prompt;
}

/**
 * 组装批量批注分发 Payload
 */
export function buildBatchAnnotationPayload(
  artifactId: string,
  comments: VisualCommentPin[],
  stylePatches: ElementStylePatch[]
): BatchAnnotationPayload {
  return {
    artifactId,
    totalComments: comments.length,
    comments,
    appliedStylePatches: stylePatches,
    compiledPromptInstruction: compileBatchAnnotationsPrompt(
      artifactId,
      comments,
      stylePatches
    ),
    dispatchedAt: new Date().toISOString(),
  };
}
