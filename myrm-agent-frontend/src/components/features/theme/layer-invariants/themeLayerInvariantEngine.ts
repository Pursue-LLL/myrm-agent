import {
  LayerDirectionEvaluation,
  PrebakedThemeBaseline,
  ThemeInvariantSuiteReport,
  ThemeMode,
} from './themeLayerInvariantTypes';

/**
 * 将十六进制颜色解析为 RGB 三元组 [r, g, b] (0 - 255)
 */
export function parseHexToRgb(hexColor: string): [number, number, number] {
  const cleanHex = hexColor.trim().replace(/^#/, '');

  if (cleanHex.length === 3) {
    const r = parseInt(cleanHex[0] + cleanHex[0], 16);
    const g = parseInt(cleanHex[1] + cleanHex[1], 16);
    const b = parseInt(cleanHex[2] + cleanHex[2], 16);
    return [r, g, b];
  }

  if (cleanHex.length === 6) {
    const r = parseInt(cleanHex.slice(0, 2), 16);
    const g = parseInt(cleanHex.slice(2, 4), 16);
    const b = parseInt(cleanHex.slice(4, 6), 16);
    return [r, g, b];
  }

  // 默认兜底为黑色
  return [0, 0, 0];
}

/**
 * 根据标准 WCAG / ITU-R BT.709 相对亮度公式计算归一化明度百分比 (0 - 100)
 */
export function calculateHexLightness(hexColor: string): number {
  const [r, g, b] = parseHexToRgb(hexColor);
  // Y = 0.2126R + 0.7152G + 0.0722B (归一化到 0 - 100)
  const luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 2.55;
  return Math.round(luminance * 10) / 10;
}

/**
 * 单主题层级方向不变量评估
 * 浅色下: L_card >= L_canvas (卡面明度 >= 画布底色，靠描边+阴影抬升，严禁调暗产生凹陷感)
 * 深色下: L_card > L_canvas (卡面明度 > 画布底色，阴影在深色不可见，靠更亮的卡面抬升)
 */
export function evaluateLayerDirection(
  mode: ThemeMode,
  canvasHex: string,
  cardHex: string
): LayerDirectionEvaluation {
  const canvasLightness = calculateHexLightness(canvasHex);
  const cardLightness = calculateHexLightness(cardHex);
  const deltaLightness = Math.round((cardLightness - canvasLightness) * 10) / 10;

  if (mode === 'light') {
    // 浅色下: cardLightness 必须 >= canvasLightness
    const isSatisfied = cardLightness >= canvasLightness;
    return {
      mode: 'light',
      canvasHex,
      cardHex,
      canvasLightness,
      cardLightness,
      deltaLightness,
      isInvariantSatisfied: isSatisfied,
      violationReason: isSatisfied
        ? undefined
        : `浅色主题违规：卡面明度 (${cardLightness}) 低于页面画布 (${canvasLightness}) ${Math.abs(deltaLightness)} 级，卡片被错误调暗导致凹陷/禁用感！`,
    };
  }

  // 深色下: cardLightness 必须 > canvasLightness
  const isSatisfied = cardLightness > canvasLightness;
  return {
    mode: 'dark',
    canvasHex,
    cardHex,
    canvasLightness,
    cardLightness,
    deltaLightness,
    isInvariantSatisfied: isSatisfied,
    violationReason: isSatisfied
      ? undefined
      : `深色主题违规：卡面明度 (${cardLightness}) 未高于页面底色 (${canvasLightness})，深色阴影失效导致无法形成视觉抬升分层！`,
  };
}

/**
 * 双主题同帧套件评估
 */
export function evaluateThemeInvariantSuite(
  lightCanvasHex: string,
  lightCardHex: string,
  darkCanvasHex: string,
  darkCardHex: string
): ThemeInvariantSuiteReport {
  const lightEvaluation = evaluateLayerDirection(
    'light',
    lightCanvasHex,
    lightCardHex
  );
  const darkEvaluation = evaluateLayerDirection(
    'dark',
    darkCanvasHex,
    darkCardHex
  );

  return {
    timestamp: Date.now(),
    lightEvaluation,
    darkEvaluation,
    allPassed:
      lightEvaluation.isInvariantSatisfied && darkEvaluation.isInvariantSatisfied,
  };
}

/**
 * 与旧版预烘基线比对回归
 */
export function compareWithPrebakedBaseline(
  report: ThemeInvariantSuiteReport,
  baseline: PrebakedThemeBaseline
): { hasRegression: boolean; details: string[] } {
  const details: string[] = [];
  let hasRegression = false;

  // 浅色比对
  if (
    baseline.lightMode.isCorrect &&
    !report.lightEvaluation.isInvariantSatisfied
  ) {
    hasRegression = true;
    details.push(
      `浅色主题发生反直觉回归：在基线版本 ${baseline.baselineVersion} 中浅色合规，但当前版本卡面变暗出现发灰凹陷！`
    );
  }

  // 深色比对
  if (baseline.darkMode.isCorrect && !report.darkEvaluation.isInvariantSatisfied) {
    hasRegression = true;
    details.push(
      `深色主题发生抬升失守回归：在基线版本 ${baseline.baselineVersion} 中深色合规，但当前版本卡面明度未高于底色！`
    );
  }

  return {
    hasRegression,
    details,
  };
}
