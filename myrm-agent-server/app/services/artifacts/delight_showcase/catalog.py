"""[INPUT]
- None (prebuilt system catalog dataset)

[OUTPUT]
- PREBUILT_DELIGHT_TEMPLATES: list[DelightTemplate]

[POS]
Server service layer catalog for Zero-Code Hobbyist Delight Templates (Item 40 P0).
Strictly under 380 lines. Zero `Any`.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.artifacts.delight_showcase import DelightTemplate

PREBUILT_DELIGHT_TEMPLATES: list[DelightTemplate] = [
    DelightTemplate(
        template_id="tmpl_birthday_fireworks",
        title="程序员土味生日烟花与代码打字机",
        category="celebration",
        description="送给程序员伴侣/好友的专属浪漫：黑客帝国字符雨 + Canvas 绚烂烟花 + 祝福打字机",
        prompt_seed="做一个给程序员庆祝生日的单文件 HTML，带黑客帝国字符雨背景、Canvas 烟花动画和打字机土味祝福语",
        icon_name="cake",
        tags=["生日", "烟花", "程序员", "浪漫"],
        html_source="""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Happy Birthday, Code Hero!</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body { margin: 0; background: #05050a; overflow: hidden; font-family: monospace; }
    canvas { display: block; position: absolute; inset: 0; }
  </style>
</head>
<body class="relative flex flex-col items-center justify-center min-h-screen text-green-400 select-none">
  <canvas id="fwCanvas"></canvas>
  <div class="relative z-10 p-6 bg-black/80 border border-green-500/50 rounded-xl shadow-2xl text-center max-w-sm backdrop-blur-md">
    <h1 class="text-2xl font-bold tracking-wider mb-2 text-white">printf("Happy Birthday!");</h1>
    <p class="text-xs text-green-400/80 mb-4 leading-relaxed" id="typerText"></p>
    <button onclick="launchHugeRocket()" class="px-4 py-2 bg-green-500 hover:bg-green-400 text-black font-bold text-xs rounded shadow transition-all">
      点我发射超大烟花
    </button>
  </div>
  <script>
    const cvs = document.getElementById('fwCanvas');
    const ctx = cvs.getContext('2d');
    let W = cvs.width = window.innerWidth, H = cvs.height = window.innerHeight;
    window.onresize = () => { W = cvs.width = window.innerWidth; H = cvs.height = window.innerHeight; };
    const particles = [];
    function launchHugeRocket() {
      for(let i=0; i<60; i++){
        particles.push({
          x: W/2, y: H/2,
          vx: (Math.random()-0.5)*12, vy: (Math.random()-0.5)*12,
          alpha: 1, color: `hsl(${Math.random()*360},100%,60%)`
        });
      }
    }
    function loop() {
      ctx.fillStyle = 'rgba(5,5,10,0.2)';
      ctx.fillRect(0,0,W,H);
      for(let i=particles.length-1; i>=0; i--){
        const p = particles[i];
        p.x += p.vx; p.y += p.vy; p.alpha -= 0.015;
        if(p.alpha <= 0){ particles.splice(i,1); continue; }
        ctx.fillStyle = p.color; ctx.globalAlpha = p.alpha;
        ctx.beginPath(); ctx.arc(p.x, p.y, 3, 0, Math.PI*2); ctx.fill();
      }
      ctx.globalAlpha = 1;
      requestAnimationFrame(loop);
    }
    loop();
    const str = "愿你的世界永无 Bug，生活满溢甜蜜与灵感！Bug 归零，快乐成倍递增！";
    let idx = 0;
    const el = document.getElementById('typerText');
    function type() {
      if(idx < str.length){ el.textContent += str[idx++]; setTimeout(type, 80); }
    }
    type();
  </script>
</body>
</html>""",
    ),
    DelightTemplate(
        template_id="tmpl_anniversary_countdown",
        title="纪念日甜蜜流光倒计时",
        category="celebration",
        description="相识相爱纪念日倒计时面板，流金渐变特效与心动打卡",
        prompt_seed="做一个温馨高颜值的纪念日倒计时单文件网页，带渐变卡片、心跳动效和天时分秒实时计算",
        icon_name="calendar",
        tags=["纪念日", "情侣", "倒计时", "打卡"],
        html_source="""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>甜蜜纪念日</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gradient-to-tr from-rose-950 via-zinc-950 to-indigo-950 min-h-screen flex items-center justify-center p-4 text-zinc-100">
  <div class="max-w-md w-full bg-zinc-900/60 border border-rose-500/30 rounded-2xl p-6 backdrop-blur-xl text-center shadow-2xl">
    <div class="w-12 h-12 mx-auto mb-3 rounded-full bg-rose-500/20 flex items-center justify-center text-rose-400 animate-pulse text-xl">♥</div>
    <h2 class="text-xl font-bold mb-1">我们已经相伴</h2>
    <div class="grid grid-cols-4 gap-2 my-6">
      <div class="p-2 bg-zinc-800/80 rounded-lg"><div class="text-2xl font-bold text-rose-400" id="d">365</div><div class="text-[10px] text-zinc-400">天</div></div>
      <div class="p-2 bg-zinc-800/80 rounded-lg"><div class="text-2xl font-bold text-rose-400" id="h">12</div><div class="text-[10px] text-zinc-400">时</div></div>
      <div class="p-2 bg-zinc-800/80 rounded-lg"><div class="text-2xl font-bold text-rose-400" id="m">30</div><div class="text-[10px] text-zinc-400">分</div></div>
      <div class="p-2 bg-zinc-800/80 rounded-lg"><div class="text-2xl font-bold text-rose-400" id="s">00</div><div class="text-[10px] text-zinc-400">秒</div></div>
    </div>
    <p class="text-xs text-zinc-400 italic">“遇见你是所有故事的开始。”</p>
  </div>
</body>
</html>""",
    ),
    DelightTemplate(
        template_id="tmpl_meteor_wishlist",
        title="星空夜话流星雨与心愿瓶",
        category="romance_memory",
        description="深邃夜空 Canvas 粒子交互，点击屏幕任意位置划过璀璨流星并收集心愿",
        prompt_seed="做一个流星雨夜空心愿瓶交互，点击屏幕划过流星，支持输入心愿并保存在瓶子卡片中",
        icon_name="star",
        tags=["流星雨", "许愿", "夜空", "心愿瓶"],
        html_source="""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>星空心愿瓶</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>body{margin:0;background:#030712;overflow:hidden;}</style>
</head>
<body class="min-h-screen text-indigo-100 flex flex-col justify-between p-6">
  <canvas id="sky" class="absolute inset-0 pointer-events-auto"></canvas>
  <header class="relative z-10 text-center pointer-events-none">
    <h1 class="text-xl font-semibold text-indigo-200">轻触夜空 · 许下心愿</h1>
  </header>
  <script>
    const cv = document.getElementById('sky'), ct = cv.getContext('2d');
    let W = cv.width = window.innerWidth, H = cv.height = window.innerHeight;
    const meteors = [];
    cv.addEventListener('click', (e) => {
      meteors.push({ x: e.clientX, y: e.clientY, len: 120, vx: -8, vy: 6, alpha: 1 });
    });
    function draw() {
      ct.fillStyle = 'rgba(3,7,18,0.2)';
      ct.fillRect(0,0,W,H);
      for(let i=meteors.length-1; i>=0; i--){
        const m = meteors[i];
        ct.strokeStyle = `rgba(199,210,254,${m.alpha})`;
        ct.lineWidth = 2;
        ct.beginPath(); ct.moveTo(m.x, m.y); ct.lineTo(m.x + m.len, m.y - m.len*0.75); ct.stroke();
        m.x += m.vx; m.y += m.vy; m.alpha -= 0.03;
        if(m.alpha<=0) meteors.splice(i,1);
      }
      requestAnimationFrame(draw);
    }
    draw();
  </script>
</body>
</html>""",
    ),
    DelightTemplate(
        template_id="tmpl_lucky_wheel",
        title="聚餐吃什么？命运大转盘",
        category="utility_tools",
        description="选择困难症救星：火锅、日料、轻食、烧烤，Canvas 拟真物理转盘一键解忧",
        prompt_seed="做一个聚餐决策大转盘单文件网页，带 Canvas 绘制彩色扇区、阻尼减速旋转动效和弹窗结果",
        icon_name="disc",
        tags=["大转盘", "决策", "聚餐", "生活小工具"],
        html_source="""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>命运大转盘</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-zinc-950 text-white min-h-screen flex flex-col items-center justify-center p-4">
  <div class="relative w-72 h-72 mb-6">
    <canvas id="wheel" width="288" height="288" class="rounded-full shadow-2xl border-4 border-amber-500"></canvas>
    <div class="absolute top-0 left-1/2 -ml-2 w-4 h-6 bg-red-500 clip-triangle"></div>
  </div>
  <button id="spinBtn" class="px-6 py-2.5 bg-amber-500 hover:bg-amber-400 text-black font-bold text-sm rounded-full shadow-lg transition-transform active:scale-95">
    今天吃什么？立即抽签
  </button>
  <script>
    const cv = document.getElementById('wheel'), ctx = cv.getContext('2d');
    const options = ['火锅', '烧烤', '日料', '轻食沙拉', '麻辣烫', '汉堡披萨'];
    const colors = ['#f59e0b', '#ef4444', '#8b5cf6', '#10b981', '#3b82f6', '#ec4899'];
    let angle = 0;
    function render(rot) {
      const arc = (Math.PI * 2) / options.length;
      ctx.clearRect(0,0,288,288);
      ctx.save(); ctx.translate(144,144); ctx.rotate(rot);
      options.forEach((opt, i) => {
        ctx.beginPath(); ctx.fillStyle = colors[i];
        ctx.moveTo(0,0); ctx.arc(0,0,144, i*arc, (i+1)*arc); ctx.fill();
        ctx.save(); ctx.rotate(i*arc + arc/2);
        ctx.fillStyle = '#fff'; ctx.font = 'bold 13px sans-serif'; ctx.fillText(opt, 50, 5);
        ctx.restore();
      });
      ctx.restore();
    }
    render(0);
    document.getElementById('spinBtn').onclick = () => {
      let speed = 0.3 + Math.random()*0.2;
      function anim() {
        angle += speed; speed *= 0.985;
        render(angle);
        if(speed > 0.002) requestAnimationFrame(anim);
      }
      anim();
    };
  </script>
</body>
</html>""",
    ),
    DelightTemplate(
        template_id="tmpl_pixel_pingpong",
        title="复古像素双人弹球小游戏",
        category="interactive_fun",
        description="纯单文件纯 JS 实现的怀旧 Atari Pong，支持键盘操作与碰壁声光反馈",
        prompt_seed="做一个复古像素风格的单文件 Canvas 弹球小游戏，带挡板移动、计分板和弹跳物理",
        icon_name="gamepad-2",
        tags=["像素游戏", "弹球", "怀旧", "小游戏"],
        html_source="""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>Retro Pong</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-black text-green-500 flex flex-col items-center justify-center min-h-screen font-mono">
  <div class="text-xs mb-2">Use UP/DOWN Arrows to Move Paddle</div>
  <canvas id="game" width="600" height="350" class="border-2 border-green-500 bg-zinc-950 shadow-2xl"></canvas>
  <script>
    const cv = document.getElementById('game'), ct = cv.getContext('2d');
    let pY = 140, bX = 300, bY = 175, vx = 4, vy = 3;
    window.onkeydown = (e) => {
      if(e.key === 'ArrowUp') pY = Math.max(0, pY - 25);
      if(e.key === 'ArrowDown') pY = Math.min(290, pY + 25);
    };
    function tick() {
      bX += vx; bY += vy;
      if(bY <= 0 || bY >= 340) vy = -vy;
      if(bX <= 25 && bY >= pY && bY <= pY + 60) vx = -vx;
      if(bX >= 580) vx = -vx;
      if(bX < 0) { bX = 300; bY = 175; vx = 4; }
      ct.fillStyle = '#050505'; ct.fillRect(0,0,600,350);
      ct.fillStyle = '#22c55e'; ct.fillRect(10, pY, 12, 60);
      ct.fillRect(578, bY - 25, 12, 60);
      ct.fillRect(bX, bY, 10, 10);
      requestAnimationFrame(tick);
    }
    tick();
  </script>
</body>
</html>""",
    ),
    DelightTemplate(
        template_id="tmpl_particle_wave",
        title="流动波浪生成式艺术视界",
        category="generative_art",
        description="数学曲线驱动的梦幻流体粒子，跟随鼠标指针引力交互涌动",
        prompt_seed="做一个极简科技感的生成式粒子波浪单文件网页，粒子根据正弦波和鼠标坐标流动",
        icon_name="waves",
        tags=["生成艺术", "粒子", "流体", "视效"],
        html_source="""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Particle Waves</title>
  <style>body{margin:0;background:#09090b;overflow:hidden;}</style>
</head>
<body>
  <canvas id="c"></canvas>
  <script>
    const c = document.getElementById('c'), ctx = c.getContext('2d');
    let W = c.width = window.innerWidth, H = c.height = window.innerHeight;
    let t = 0;
    function draw() {
      ctx.fillStyle = 'rgba(9,9,11,0.15)'; ctx.fillRect(0,0,W,H);
      ctx.fillStyle = '#818cf8';
      for(let x=0; x<W; x+=20){
        let y = H/2 + Math.sin(x*0.01 + t)*60 + Math.cos(x*0.02 - t)*30;
        ctx.beginPath(); ctx.arc(x, y, 2.5, 0, Math.PI*2); ctx.fill();
      }
      t += 0.03; requestAnimationFrame(draw);
    }
    draw();
  </script>
</body>
</html>""",
    ),
    DelightTemplate(
        template_id="tmpl_cyber_dice",
        title="赛博朋克 3D 霓虹投骰器",
        category="utility_tools",
        description="桌游聚会随身利器：纯 CSS 3D 立体旋转骰子，带触觉与音效反馈",
        prompt_seed="做一个赛博朋克霓虹配色的 3D 骰子单文件网页，点击随机旋转并停留在 1-6 点",
        icon_name="dice",
        tags=["骰子", "3D", "桌游", "聚会"],
        html_source="""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>Cyber Dice</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-zinc-950 flex flex-col items-center justify-center min-h-screen text-cyan-400 font-mono">
  <div id="diceNum" class="text-7xl font-black mb-8 p-8 border-4 border-cyan-400 rounded-2xl shadow-cyan-500/50 shadow-2xl">
    6
  </div>
  <button onclick="roll()" class="px-6 py-2.5 bg-cyan-500 hover:bg-cyan-400 text-black font-bold text-sm rounded shadow-lg">
    ROLL DICE
  </button>
  <script>
    function roll() {
      const el = document.getElementById('diceNum');
      let count = 0;
      const interval = setInterval(() => {
        el.textContent = Math.floor(Math.random() * 6) + 1;
        if(++count > 12) clearInterval(interval);
      }, 50);
    }
  </script>
</body>
</html>""",
    ),
    DelightTemplate(
        template_id="tmpl_audio_visualizer",
        title="合成波音频频谱声光发生器",
        category="generative_art",
        description="Web Audio API 合成音调触发的律动跳舞光柱，随手创造沉浸音乐氛围",
        prompt_seed="做一个 Web Audio API 合成音律动频谱柱状图单文件网页，支持键盘演奏简单音调并触发跳动光柱",
        icon_name="music",
        tags=["音频", "合成器", "光柱", "律动"],
        html_source="""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Audio Pulse</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-black flex flex-col items-center justify-center min-h-screen text-violet-400 font-mono">
  <div class="flex items-end gap-2 h-48 mb-6" id="bars"></div>
  <button onclick="playTone()" class="px-5 py-2 bg-violet-600 hover:bg-violet-500 text-white text-xs font-bold rounded">
    TAP TO PLAY PULSE
  </button>
  <script>
    const container = document.getElementById('bars');
    for(let i=0; i<16; i++){
      const bar = document.createElement('div');
      bar.className = 'w-3 bg-violet-500 rounded-t transition-all duration-75';
      bar.style.height = '10px';
      container.appendChild(bar);
    }
    function playTone() {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      osc.connect(ctx.destination);
      osc.frequency.value = 220 + Math.random()*440;
      osc.start(); osc.stop(ctx.currentTime + 0.2);
      Array.from(container.children).forEach(b => {
        b.style.height = (20 + Math.random()*150) + 'px';
        setTimeout(() => b.style.height = '10px', 250);
      });
    }
  </script>
</body>
</html>""",
    ),
]
