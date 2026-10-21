import { describe, it, expect } from 'vitest';
import {
  buildThreeJsSandboxHtml,
  buildWebGLSelfHealingDossier,
  resolveCameraModeAction,
} from '../threeJsSandboxEngine';
import { WebGLLogEntry, WebGLPerformanceMetrics } from '../threeJsTypes';

describe('threeJsSandboxEngine 核心函数单测', () => {
  it('buildThreeJsSandboxHtml 应包含 Three.js CDN、错误拦截桥接与用户场景脚本', () => {
    const userCode = 'const scene = new THREE.Scene(); const cube = new THREE.Mesh();';
    const html = buildThreeJsSandboxHtml(userCode, '林渊：最后一夜');

    expect(html).toContain('<!DOCTYPE html>');
    expect(html).toContain('<title>林渊：最后一夜</title>');
    expect(html).toContain('three.min.js');
    expect(html).toContain('OrbitControls.js');
    expect(html).toContain('window.parent.postMessage');
    expect(html).toContain('compileShader');
    expect(html).toContain(userCode);
  });

  it('buildWebGLSelfHealingDossier 应格式化生成结构化 Agent 修复指令包', () => {
    const errorEntry: WebGLLogEntry = {
      id: 'log-err-1',
      level: 'error',
      source: 'shader',
      message: 'ERROR: 0:18: Use of undeclared identifier vUv',
      timestamp: '14:30:00',
      shaderInfo: {
        type: 'fragment',
        infoLog: 'Shader compile error at line 18',
      },
    };

    const metrics: WebGLPerformanceMetrics = {
      fps: 15,
      drawCalls: 120,
      triangles: 45000,
      geometries: 10,
      textures: 4,
    };

    const dossier = buildWebGLSelfHealingDossier('scene-forest-zombie', errorEntry, metrics);

    expect(dossier.sceneId).toBe('scene-forest-zombie');
    expect(dossier.source).toBe('shader');
    expect(dossier.repairInstructionPrompt).toContain('【WebGL 3D 场景运行时错误自愈请求】');
    expect(dossier.repairInstructionPrompt).toContain('ERROR: 0:18: Use of undeclared identifier vUv');
    expect(dossier.repairInstructionPrompt).toContain('Shader 诊断详情');
    expect(dossier.repairInstructionPrompt).toContain('fragment');
    expect(dossier.repairInstructionPrompt).toContain('FPS: 15');
  });

  it('resolveCameraModeAction 应正确映射操纵与观察模式的操作说明', () => {
    const playAction = resolveCameraModeAction('pointer_lock');
    expect(playAction.label).toBe('试玩操纵模式');
    expect(playAction.instruction).toContain('鼠标指针锁定');

    const orbitAction = resolveCameraModeAction('orbit');
    expect(orbitAction.label).toBe('轨道观察模式');
    expect(orbitAction.instruction).toContain('按住鼠标左键旋转视角');
  });
});
