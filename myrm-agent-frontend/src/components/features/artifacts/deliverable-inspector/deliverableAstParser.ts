/**
 * [INPUT] Raw deliverable content, DeliverableType, patch requests, node arrays
 * [OUTPUT] Parsed DeliverableNode array, selective partial patch applier, and snapshot diff engine
 * [POS] artifacts/deliverable-inspector/deliverableAstParser.ts
 */

import type {
  DeliverableType,
  DeliverableNode,
  SnapshotDiffItem,
} from './deliverableInspectorTypes';

function extractTitle(content: string, fallback: string): string {
  const lines = content.split('\n');
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('#')) {
      return trimmed.replace(/^#+\s*/, '').trim();
    }
  }
  return fallback;
}

function extractSummary(content: string): string {
  const lines = content.split('\n');
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed && !trimmed.startsWith('#') && !trimmed.startsWith('---')) {
      if (trimmed.length > 70) {
        return trimmed.slice(0, 66) + '...';
      }
      return trimmed;
    }
  }
  return '无正文摘要';
}

export function parseDeliverableNodes(
  rawContent: string,
  type: DeliverableType,
): DeliverableNode[] {
  if (!rawContent || !rawContent.trim()) {
    return [];
  }

  const nodes: DeliverableNode[] = [];

  if (type === 'slides') {
    // Split by markdown horizontal rules or explicit slide markers
    const rawChunks = rawContent.split(/\n---\n|\n---$|^---\n/);
    let slideIndex = 1;

    for (const chunk of rawChunks) {
      const trimmed = chunk.trim();
      if (!trimmed) {
        continue;
      }

      const title = extractTitle(trimmed, `Slide ${slideIndex}`);
      const summary = extractSummary(trimmed);

      nodes.push({
        id: `slide-${slideIndex}`,
        index: slideIndex,
        title,
        summary,
        nodeType: 'slide',
        content: trimmed,
        metadata: {
          hasChart: /```mermaid|chart|table/i.test(trimmed),
          lineCount: trimmed.split('\n').length,
        },
      });
      slideIndex += 1;
    }

    if (nodes.length === 0) {
      nodes.push({
        id: 'slide-1',
        index: 1,
        title: 'Slide 1',
        summary: extractSummary(rawContent),
        nodeType: 'slide',
        content: rawContent.trim(),
      });
    }

    return nodes;
  }

  if (type === 'document' || type === 'markdown') {
    // Split by level 2 or level 1 headings
    const sectionRegex = /(?=^##\s+|^#\s+)/m;
    const rawSections = rawContent.split(sectionRegex);
    let sectionIndex = 1;

    for (const section of rawSections) {
      const trimmed = section.trim();
      if (!trimmed) {
        continue;
      }

      const title = extractTitle(trimmed, `Section ${sectionIndex}`);
      const summary = extractSummary(trimmed);

      nodes.push({
        id: `section-${sectionIndex}`,
        index: sectionIndex,
        title,
        summary,
        nodeType: 'section',
        content: trimmed,
        metadata: {
          paragraphCount: trimmed.split('\n\n').length,
        },
      });
      sectionIndex += 1;
    }

    if (nodes.length === 0) {
      nodes.push({
        id: 'section-1',
        index: 1,
        title: 'Document Content',
        summary: extractSummary(rawContent),
        nodeType: 'section',
        content: rawContent.trim(),
      });
    }

    return nodes;
  }

  // Spreadsheet type: split by sheet tags or sections
  const sheetRegex = /(?=^###\s+Sheet:|^Sheet:\s*|\n---Sheet:\s*)/im;
  const rawSheets = rawContent.split(sheetRegex);
  let sheetIndex = 1;

  for (const sheetChunk of rawSheets) {
    const trimmed = sheetChunk.trim();
    if (!trimmed) {
      continue;
    }

    const title = extractTitle(trimmed, `Sheet ${sheetIndex}`);
    const summary = extractSummary(trimmed);

    nodes.push({
      id: `sheet-${sheetIndex}`,
      index: sheetIndex,
      title,
      summary,
      nodeType: 'sheet',
      content: trimmed,
      metadata: {
        rowCount: trimmed.split('\n').filter((l) => l.includes('|')).length,
      },
    });
    sheetIndex += 1;
  }

  if (nodes.length === 0) {
    nodes.push({
      id: 'sheet-1',
      index: 1,
      title: 'Sheet 1',
      summary: extractSummary(rawContent),
      nodeType: 'sheet',
      content: rawContent.trim(),
    });
  }

  return nodes;
}

export function applySelectiveNodePatch(
  nodes: DeliverableNode[],
  patchNodeId: string,
  patchedContent: string,
  updatedTitle?: string,
): DeliverableNode[] {
  return nodes.map((node) => {
    if (node.id !== patchNodeId) {
      // Keep untouched nodes completely preserved
      return node;
    }

    const newTitle = updatedTitle || extractTitle(patchedContent, node.title);
    const newSummary = extractSummary(patchedContent);

    return {
      ...node,
      title: newTitle,
      summary: newSummary,
      content: patchedContent,
      metadata: {
        ...node.metadata,
        lastPatchedAt: Date.now(),
      },
    };
  });
}

export function computeSnapshotDiff(
  beforeNodes: DeliverableNode[],
  afterNodes: DeliverableNode[],
): SnapshotDiffItem[] {
  const diffs: SnapshotDiffItem[] = [];
  const beforeMap = new Map<string, DeliverableNode>();

  for (const n of beforeNodes) {
    beforeMap.set(n.id, n);
  }

  for (const afterNode of afterNodes) {
    const beforeNode = beforeMap.get(afterNode.id);
    if (!beforeNode) {
      diffs.push({
        nodeId: afterNode.id,
        nodeTitle: afterNode.title,
        status: 'added',
        afterContent: afterNode.content,
      });
    } else if (beforeNode.content !== afterNode.content) {
      diffs.push({
        nodeId: afterNode.id,
        nodeTitle: afterNode.title,
        status: 'modified',
        beforeContent: beforeNode.content,
        afterContent: afterNode.content,
      });
    } else {
      diffs.push({
        nodeId: afterNode.id,
        nodeTitle: afterNode.title,
        status: 'unchanged',
      });
    }
    beforeMap.delete(afterNode.id);
  }

  // Any remaining nodes in beforeMap were removed
  for (const [id, removedNode] of beforeMap.entries()) {
    diffs.push({
      nodeId: id,
      nodeTitle: removedNode.title,
      status: 'removed',
      beforeContent: removedNode.content,
    });
  }

  return diffs;
}
