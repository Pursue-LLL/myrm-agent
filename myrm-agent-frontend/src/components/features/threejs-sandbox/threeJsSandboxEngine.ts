import {
  WebGLPerformanceMetrics,
  WebGLLogEntry,
  WebGLSelfHealingDossier,
  SandboxCameraMode,
} from './threeJsTypes';

/**
 * 组装安全的 WebGL / Three.js 独立沙箱 HTML 页面
 */
export function buildThreeJsSandboxHtml(userCode: string, title = '3D Scene Sandbox'): string {
  // 注入轻量级的宿主桥接脚本，用于错误捕获与性能采样
  const bridgeScript = `
    <script>
      (function() {
        const sendParent = function(type, payload) {
          try {
            window.parent.postMessage({ source: 'threejs-sandbox', type: type, payload: payload }, '*');
          } catch (e) {}
        };

        // 1. 全局 JavaScript 异常拦截
        window.addEventListener('error', function(e) {
          sendParent('log', {
            level: 'error',
            source: 'runtime',
            message: e.message || 'Unknown WebGL Runtime Error',
            timestamp: new Date().toLocaleTimeString()
          });
        });

        // 2. WebGL 上下文丢失拦截
        window.addEventListener('webglcontextlost', function(e) {
          e.preventDefault();
          sendParent('log', {
            level: 'error',
            source: 'system',
            message: 'WebGL 上下文丢失 (Context Lost)',
            timestamp: new Date().toLocaleTimeString()
          });
        });

        // 3. 拦截 Shader 编译错误
        if (window.WebGLRenderingContext) {
          const origCompileShader = WebGLRenderingContext.prototype.compileShader;
          WebGLRenderingContext.prototype.compileShader = function(shader) {
            origCompileShader.apply(this, arguments);
            const status = this.getShaderParameter(shader, this.COMPILE_STATUS);
            if (!status) {
              const infoLog = this.getShaderInfoLog(shader) || 'Shader compilation failed';
              const isFrag = this.getShaderParameter(shader, this.SHADER_TYPE) === this.FRAGMENT_SHADER;
              sendParent('log', {
                level: 'error',
                source: 'shader',
                message: '着色器编译失败: ' + infoLog,
                timestamp: new Date().toLocaleTimeString(),
                shaderInfo: {
                  type: isFrag ? 'fragment' : 'vertex',
                  infoLog: infoLog
                }
              });
            }
          };
        }

        // 4. 帧率测量心跳广播
        let frameCount = 0;
        let lastTime = performance.now();
        function loop() {
          frameCount++;
          const now = performance.now();
          if (now - lastTime >= 1000) {
            const fps = Math.round((frameCount * 1000) / (now - lastTime));
            frameCount = 0;
            lastTime = now;
            sendParent('metrics', {
              fps: fps,
              drawCalls: window.__threeStats ? window.__threeStats.drawCalls : 1,
              triangles: window.__threeStats ? window.__threeStats.triangles : 0,
              geometries: window.__threeStats ? window.__threeStats.geometries : 0,
              textures: window.__threeStats ? window.__threeStats.textures : 0
            });
          }
          requestAnimationFrame(loop);
        }
        requestAnimationFrame(loop);
      })();
    </script>
  `;

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${title}</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { width: 100%; height: 100%; overflow: hidden; background: #0b0f19; }
    canvas { display: block; width: 100vw; height: 100vh; }
  </style>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
  ${bridgeScript}
</head>
<body>
  <div id="canvas-container"></div>
  <script>
    try {
      ${userCode}
    } catch (err) {
      console.error(err);
      window.parent.postMessage({
        source: 'threejs-sandbox',
        type: 'log',
        payload: {
          level: 'error',
          source: 'runtime',
          message: err.message || String(err),
          timestamp: new Date().toLocaleTimeString()
        }
      }, '*');
    }
  </script>
</body>
</html>`;
}

/**
 * 将运行时错误构造成供 Agent 自愈修复的结构化 Prompt 诊断包
 */
export function buildWebGLSelfHealingDossier(
  sceneId: string,
  errorEntry: WebGLLogEntry,
  currentMetrics?: WebGLPerformanceMetrics
): WebGLSelfHealingDossier {
  let prompt = `【WebGL 3D 场景运行时错误自愈请求】\n场景 ID: ${sceneId}\n报错级别: ${errorEntry.level}\n错误来源: ${errorEntry.source || '未知'}\n错误信息: ${errorEntry.message}\n时间戳: ${errorEntry.timestamp}\n`;

  if (errorEntry.shaderInfo) {
    prompt += `\nShader 诊断详情:\n- 着色器类型: ${errorEntry.shaderInfo.type}\n- 编译日志: ${errorEntry.shaderInfo.infoLog}\n`;
  }

  if (currentMetrics) {
    prompt += `\n崩溃发生时渲染指标: FPS: ${currentMetrics.fps}, DrawCalls: ${currentMetrics.drawCalls}, Triangles: ${currentMetrics.triangles}\n`;
  }

  prompt += '\n请分析上述报错原因，重点核查顶点/片元着色器语法、缺少的光源或摄像机参数、贴图资源路径、Three.js API 兼容性，并输出修复后的完整纯 JavaScript 场景代码。';

  return {
    sceneId,
    errorMessage: errorEntry.message,
    source: errorEntry.source || 'runtime',
    timestamp: errorEntry.timestamp,
    metricsAtFailure: currentMetrics,
    repairInstructionPrompt: prompt,
  };
}

/**
 * 校验相机模式切换动作指令
 */
export function resolveCameraModeAction(mode: SandboxCameraMode): {
  label: string;
  instruction: string;
} {
  if (mode === 'pointer_lock') {
    return {
      label: '试玩操纵模式',
      instruction: '已启用鼠标指针锁定与 WASD 键盘穿透，按 ESC 退出锁定',
    };
  }

  return {
    label: '轨道观察模式',
    instruction: '按住鼠标左键旋转视角，滚轮缩放，右键平移场景',
  };
}
