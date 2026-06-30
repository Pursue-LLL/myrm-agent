import type { DrawOperation, Point } from './types';

const BLUR_BLOCK_SIZE = 10;

export function renderOperation(ctx: CanvasRenderingContext2D, op: DrawOperation): void {
  ctx.strokeStyle = op.color;
  ctx.fillStyle = op.color;
  ctx.lineWidth = op.lineWidth;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  switch (op.tool) {
    case 'rect':
      renderRect(ctx, op.points);
      break;
    case 'ellipse':
      renderEllipse(ctx, op.points);
      break;
    case 'arrow':
      renderArrow(ctx, op.points);
      break;
    case 'freehand':
      renderFreehand(ctx, op.points);
      break;
    case 'text':
      renderText(ctx, op);
      break;
    case 'blur':
      renderBlur(ctx, op.points);
      break;
  }
}

function renderRect(ctx: CanvasRenderingContext2D, points: Point[]): void {
  if (points.length < 2) return;
  const [start, end] = [points[0], points[points.length - 1]];
  ctx.strokeRect(start.x, start.y, end.x - start.x, end.y - start.y);
}

function renderEllipse(ctx: CanvasRenderingContext2D, points: Point[]): void {
  if (points.length < 2) return;
  const [start, end] = [points[0], points[points.length - 1]];
  const cx = (start.x + end.x) / 2;
  const cy = (start.y + end.y) / 2;
  const rx = Math.abs(end.x - start.x) / 2;
  const ry = Math.abs(end.y - start.y) / 2;
  ctx.beginPath();
  ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
  ctx.stroke();
}

function renderArrow(ctx: CanvasRenderingContext2D, points: Point[]): void {
  if (points.length < 2) return;
  const [start, end] = [points[0], points[points.length - 1]];
  const angle = Math.atan2(end.y - start.y, end.x - start.x);
  const headLength = Math.max(12, ctx.lineWidth * 4);

  ctx.beginPath();
  ctx.moveTo(start.x, start.y);
  ctx.lineTo(end.x, end.y);
  ctx.stroke();

  ctx.beginPath();
  ctx.moveTo(end.x, end.y);
  ctx.lineTo(
    end.x - headLength * Math.cos(angle - Math.PI / 6),
    end.y - headLength * Math.sin(angle - Math.PI / 6),
  );
  ctx.moveTo(end.x, end.y);
  ctx.lineTo(
    end.x - headLength * Math.cos(angle + Math.PI / 6),
    end.y - headLength * Math.sin(angle + Math.PI / 6),
  );
  ctx.stroke();
}

function renderFreehand(ctx: CanvasRenderingContext2D, points: Point[]): void {
  if (points.length < 2) return;
  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  for (let i = 1; i < points.length; i++) {
    ctx.lineTo(points[i].x, points[i].y);
  }
  ctx.stroke();
}

function renderText(ctx: CanvasRenderingContext2D, op: DrawOperation): void {
  if (!op.text || op.points.length === 0) return;
  const size = op.fontSize ?? 16;
  ctx.font = `bold ${size}px sans-serif`;
  ctx.fillText(op.text, op.points[0].x, op.points[0].y);
}

function renderBlur(ctx: CanvasRenderingContext2D, points: Point[]): void {
  if (points.length < 2) return;
  const [start, end] = [points[0], points[points.length - 1]];
  const x = Math.min(start.x, end.x);
  const y = Math.min(start.y, end.y);
  const w = Math.abs(end.x - start.x);
  const h = Math.abs(end.y - start.y);
  if (w < 2 || h < 2) return;

  const imageData = ctx.getImageData(x, y, w, h);
  pixelate(imageData, BLUR_BLOCK_SIZE);
  ctx.putImageData(imageData, x, y);
}

function pixelate(imageData: ImageData, blockSize: number): void {
  const { data, width, height } = imageData;
  for (let by = 0; by < height; by += blockSize) {
    for (let bx = 0; bx < width; bx += blockSize) {
      let r = 0, g = 0, b = 0, count = 0;
      const bw = Math.min(blockSize, width - bx);
      const bh = Math.min(blockSize, height - by);

      for (let dy = 0; dy < bh; dy++) {
        for (let dx = 0; dx < bw; dx++) {
          const idx = ((by + dy) * width + (bx + dx)) * 4;
          r += data[idx];
          g += data[idx + 1];
          b += data[idx + 2];
          count++;
        }
      }

      r = Math.round(r / count);
      g = Math.round(g / count);
      b = Math.round(b / count);

      for (let dy = 0; dy < bh; dy++) {
        for (let dx = 0; dx < bw; dx++) {
          const idx = ((by + dy) * width + (bx + dx)) * 4;
          data[idx] = r;
          data[idx + 1] = g;
          data[idx + 2] = b;
        }
      }
    }
  }
}

export function renderAllOperations(
  ctx: CanvasRenderingContext2D,
  baseImage: HTMLImageElement,
  operations: DrawOperation[],
): void {
  ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  ctx.drawImage(baseImage, 0, 0, ctx.canvas.width, ctx.canvas.height);
  for (const op of operations) {
    renderOperation(ctx, op);
  }
}
