/**
 * [INPUT]
 * - HTMLElement targets from pointer/click inspector events
 * - React Fiber internal references (__reactFiber$*)
 *
 * [OUTPUT]
 * - SourceLocation: Resolved component file path, line numbers, and confidence level
 * - DomInspectionFingerprint: Full inspection snapshot including hierarchy and candidates
 * - resolveDomSourceLocation: Function to extract source locations from a DOM element
 * - extractInspectionFingerprint: Function to build a complete fingerprint for self-evolution
 *
 * [POS]
 * DOM-to-Component AST & Fiber reverse locator for Designer's Eye Self-Evolution Pipeline.
 * Zero `any` types. File length < 320 lines. Production and development mode resilient.
 */

export type SourceConfidence = 'fiber_debug' | 'data_attribute' | 'hierarchy_match' | 'tag_fallback';

export interface SourceLocation {
  fileName: string;
  lineNumber?: number;
  columnNumber?: number;
  componentName?: string;
  confidence: SourceConfidence;
}

export interface DomInspectionFingerprint {
  tagName: string;
  id?: string;
  classes: string[];
  selector: string;
  componentHierarchy: string[];
  primarySource?: SourceLocation;
  candidates: SourceLocation[];
  textContentSnippet?: string;
}

interface ReactFiberDebugSource {
  fileName?: string;
  lineNumber?: number;
  columnNumber?: number;
}

interface ReactFiberNode {
  type?: {
    displayName?: string;
    name?: string;
  } | string | unknown;
  elementType?: {
    displayName?: string;
    name?: string;
  } | unknown;
  _debugSource?: ReactFiberDebugSource;
  _debugOwner?: ReactFiberNode;
  return?: ReactFiberNode;
}

/**
 * Normalizes an absolute or bundler file path into a clean repository-relative path.
 */
export function normalizeSourceFilePath(rawPath: string): string {
  let cleaned = rawPath.replace(/\\/g, '/');
  // Strip bundler webpack/vite query parameters
  const queryIndex = cleaned.indexOf('?');
  if (queryIndex !== -1) {
    cleaned = cleaned.slice(0, queryIndex);
  }

  // Look for src/ directory anchor
  const srcIndex = cleaned.lastIndexOf('/src/');
  if (srcIndex !== -1) {
    return cleaned.slice(srcIndex + 1);
  }
  if (cleaned.startsWith('src/')) {
    return cleaned;
  }

  // Fallback to basename or stripped path
  return cleaned.replace(/^.*\/myrm-agent-frontend\//, '');
}

/**
 * Inspects element properties to find React Fiber instance.
 */
function findReactFiber(el: Element): ReactFiberNode | null {
  const propertyKeys = Object.keys(el);
  const fiberKey = propertyKeys.find(
    (key) => key.startsWith('__reactFiber$') || key.startsWith('__reactInternalInstance$'),
  );
  if (!fiberKey) {
    return null;
  }
  const candidate = (el as unknown as Record<string, unknown>)[fiberKey];
  return (candidate && typeof candidate === 'object') ? (candidate as ReactFiberNode) : null;
}

/**
 * Extracts a readable component name from Fiber type definition.
 */
function getFiberComponentName(fiber: ReactFiberNode): string | undefined {
  if (typeof fiber.type === 'function') {
    const fn = fiber.type as { displayName?: string; name?: string };
    return fn.displayName || fn.name || undefined;
  }
  if (fiber.type && typeof fiber.type === 'object') {
    const typeObj = fiber.type as { displayName?: string; name?: string };
    if (typeObj.displayName) {
      return typeObj.displayName;
    }
    if (typeObj.name) {
      return typeObj.name;
    }
  }
  if (fiber.elementType && typeof fiber.elementType === 'object') {
    const elObj = fiber.elementType as { displayName?: string; name?: string };
    if (elObj.displayName) {
      return elObj.displayName;
    }
    if (elObj.name) {
      return elObj.name;
    }
  }
  return undefined;
}

/**
 * Resolves source location by walking up the React Fiber hierarchy.
 */
export function resolveFiberSource(el: Element): SourceLocation | null {
  let currentFiber = findReactFiber(el);
  let depth = 0;
  const maxDepth = 40;

  while (currentFiber && depth < maxDepth) {
    const compName = getFiberComponentName(currentFiber);
    const source = currentFiber._debugSource;

    if (source && source.fileName) {
      return {
        fileName: normalizeSourceFilePath(source.fileName),
        lineNumber: source.lineNumber,
        columnNumber: source.columnNumber,
        componentName: compName,
        confidence: 'fiber_debug',
      };
    }

    // Try debug owner if return path is absent
    currentFiber = currentFiber._debugOwner || currentFiber.return || null;
    depth += 1;
  }

  return null;
}

/**
 * Extracts full component hierarchy array from React Fiber tree.
 */
export function extractComponentHierarchy(el: Element): string[] {
  const names: string[] = [];
  let currentFiber = findReactFiber(el);
  let depth = 0;

  while (currentFiber && depth < 30) {
    const compName = getFiberComponentName(currentFiber);
    if (compName && !names.includes(compName) && compName !== 'Fragment') {
      names.push(compName);
    }
    currentFiber = currentFiber.return || null;
    depth += 1;
  }

  return names;
}

/**
 * Constructs a unique or representative CSS selector for the given element.
 */
export function buildConciseCssSelector(el: Element): string {
  const tagName = el.tagName.toLowerCase();
  if (el.id) {
    return `${tagName}#${el.id}`;
  }

  const classes = Array.from(el.classList).filter(
    (cls) => !cls.startsWith('hover:') && !cls.startsWith('focus:'),
  );

  if (classes.length > 0) {
    const leadingClasses = classes.slice(0, 3).join('.');
    return `${tagName}.${leadingClasses}`;
  }

  const parent = el.parentElement;
  if (!parent || parent === document.body) {
    return tagName;
  }

  const siblings = Array.from(parent.children).filter((c) => c.tagName === el.tagName);
  if (siblings.length <= 1) {
    return `${parent.tagName.toLowerCase()} > ${tagName}`;
  }

  const index = siblings.indexOf(el) + 1;
  return `${parent.tagName.toLowerCase()} > ${tagName}:nth-of-type(${index})`;
}

/**
 * Generates heuristic candidate file locations based on component hierarchy and tag clues.
 */
export function inferCandidateSourceFiles(
  componentHierarchy: string[],
  componentHint?: string,
): SourceLocation[] {
  const candidates: SourceLocation[] = [];
  const namesToInspect = [...(componentHint ? [componentHint] : []), ...componentHierarchy];

  const seenPaths = new Set<string>();

  for (const name of namesToInspect) {
    if (!name || name.length < 2) {
      continue;
    }

    // Common component location directories in myrm-agent-frontend
    const possiblePaths = [
      `src/components/features/${name.toLowerCase()}/${name}.tsx`,
      `src/components/features/chat-window/${name}.tsx`,
      `src/components/features/app-shell/${name}.tsx`,
      `src/components/common/${name}.tsx`,
      `src/components/primitives/${name.toLowerCase()}.tsx`,
      `src/components/${name}.tsx`,
    ];

    for (const p of possiblePaths) {
      if (!seenPaths.has(p)) {
        seenPaths.add(p);
        candidates.push({
          fileName: p,
          componentName: name,
          confidence: 'hierarchy_match',
        });
      }
    }
  }

  return candidates.slice(0, 5);
}

/**
 * Extracts a complete DOM inspection fingerprint for self-evolution task creation.
 */
export function extractInspectionFingerprint(el: HTMLElement): DomInspectionFingerprint {
  const tagName = el.tagName.toLowerCase();
  const classes = Array.from(el.classList);
  const selector = buildConciseCssSelector(el);
  const componentHierarchy = extractComponentHierarchy(el);

  const componentHint =
    el.getAttribute('data-component') ||
    el.closest('[data-component]')?.getAttribute('data-component') ||
    undefined;

  const fiberSource = resolveFiberSource(el);
  const heuristicCandidates = inferCandidateSourceFiles(componentHierarchy, componentHint);

  const candidates: SourceLocation[] = [];
  if (fiberSource) {
    candidates.push(fiberSource);
  }
  for (const cand of heuristicCandidates) {
    if (!candidates.some((c) => c.fileName === cand.fileName)) {
      candidates.push(cand);
    }
  }

  // Fallback candidate if none matched
  if (candidates.length === 0) {
    candidates.push({
      fileName: `src/components/${tagName.toUpperCase()}.tsx`,
      componentName: tagName,
      confidence: 'tag_fallback',
    });
  }

  // Safe text snippet
  const textRaw = el.innerText || el.textContent || '';
  const textContentSnippet = textRaw.replace(/\s+/g, ' ').trim().slice(0, 80) || undefined;

  return {
    tagName,
    id: el.id || undefined,
    classes,
    selector,
    componentHierarchy,
    primarySource: candidates[0],
    candidates,
    textContentSnippet,
  };
}
