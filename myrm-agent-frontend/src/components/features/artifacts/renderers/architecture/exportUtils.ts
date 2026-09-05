/**
 * [INPUT]
 * - html2canvas::html2canvas
 * - architecture/types::ArchitectureIR
 *
 * [OUTPUT]
 * - exportDiagramToSvg: 导出独立矢量 SVG 文件
 * - exportDiagramToPng: 2x 高清栅格化 PNG 导出
 * - copyDiagramJson: 复制拓扑 JSON IR 至剪贴板
 *
 * [POS]
 * Architecture Artifact Export Suite — 架构拓扑图的矢量/位图导出与数据剪贴板交换工具集。
 */
import html2canvas from 'html2canvas';
import type { ArchitectureIR } from './types';

/**
 * Exports current React Flow viewport as a standalone vector SVG file.
 */
export function exportDiagramToSvg(container: HTMLElement, title?: string): boolean {
  try {
    const viewportEl = container.querySelector('.react-flow__viewport') as HTMLElement | null;
    if (!viewportEl) {
      return false;
    }

    const clone = viewportEl.cloneNode(true) as HTMLElement;
    const styles = Array.from(document.querySelectorAll('style, link[rel="stylesheet"]'))
      .map((s) => s.outerHTML)
      .join('\n');

    const svgData = `<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1000" viewBox="0 0 1600 1000">
      <foreignObject width="100%" height="100%">
        <div xmlns="http://www.w3.org/1999/xhtml">
          ${styles}
          <div class="${document.documentElement.className}">
            ${clone.innerHTML}
          </div>
        </div>
      </foreignObject>
    </svg>`;

    const blob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.download = `${title || 'architecture-diagram'}.svg`;
    link.href = url;
    link.click();
    URL.revokeObjectURL(url);
    return true;
  } catch {
    return false;
  }
}

/**
 * Captures React Flow viewport and exports as a 2x high-resolution PNG image.
 */
export async function exportDiagramToPng(container: HTMLElement, title?: string): Promise<boolean> {
  try {
    const isDark = document.documentElement.classList.contains('dark');
    const viewportEl = container.querySelector('.react-flow__viewport') as HTMLElement | null;
    const targetEl = viewportEl || container;

    const canvas = await html2canvas(targetEl, {
      backgroundColor: isDark ? '#020617' : '#ffffff',
      scale: 2,
      useCORS: true,
      logging: false,
    });

    const url = canvas.toDataURL('image/png');
    const link = document.createElement('a');
    link.download = `${title || 'architecture-diagram'}.png`;
    link.href = url;
    link.click();
    return true;
  } catch {
    return false;
  }
}

/**
 * Copies sanitized ArchitectureIR snapshot into user's clipboard.
 */
export async function copyDiagramJson(ir: ArchitectureIR): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(JSON.stringify(ir, null, 2));
    return true;
  } catch {
    return false;
  }
}
