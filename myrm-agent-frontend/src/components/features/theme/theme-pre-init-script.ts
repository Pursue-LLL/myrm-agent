/**
 * Blocking pre-hydration script for theme-color meta, skin, and font.
 * Served from /public/theme-init.js via next/script beforeInteractive.
 *
 * FONT_CHOICES stacks in @/lib/fonts must stay in sync when editing font maps here.
 */
export const THEME_PRE_INIT_SCRIPT = `
try {
  var d=document.documentElement;
  var theme=localStorage.getItem('theme');
  var isDark=theme==='dark';
  var meta=document.querySelector('meta[name="theme-color"]');
  if(meta)meta.setAttribute('content',isDark?'#0a0a0a':'#fdfdfb');
  var skin=localStorage.getItem('myrm-skin');
  if(skin&&skin!=='default')d.setAttribute('data-skin',skin);
  var font=localStorage.getItem('myrm-font');
  if(font&&font!=='inter'){
    d.setAttribute('data-font',font);
    var m={system:'ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Noto Sans SC","Microsoft YaHei",sans-serif',atkinson:'"Atkinson Hyperlegible Next",ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Noto Sans SC",sans-serif'};
    if(m[font])d.style.setProperty('--font-override',m[font]);
  }
} catch(e){}
`.trim();
