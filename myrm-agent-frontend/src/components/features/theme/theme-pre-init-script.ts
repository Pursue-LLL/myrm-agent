/**
 * Blocking pre-hydration script for theme-color meta and Theme Engine tokens.
 * Served from /public/theme-init.js via next/script beforeInteractive.
 */
export const THEME_PRE_INIT_SCRIPT = `
try {
  var d=document.documentElement;
  var theme=localStorage.getItem('theme');
  var isDark=theme==='dark'||(theme!=='light'&&window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches);
  var meta=document.querySelector('meta[name="theme-color"]');
  if(meta)meta.setAttribute('content',isDark?'#0a0a0a':'#fdfdfb');
  var pre=null;
  try{pre=JSON.parse(localStorage.getItem('myrm-theme-preinit')||'null');}catch(e){}
  if(pre&&typeof pre.isDark==='boolean'){isDark=pre.isDark;}
  var profileId=pre&&pre.profileId?pre.profileId:'official-default';
  var layoutId=pre&&pre.layoutId?pre.layoutId:'full-bleed';
  var artOn=pre&&pre.artOn?'on':'off';
  d.setAttribute('data-myrm-theme-profile',profileId);
  d.setAttribute('data-myrm-theme-layout',layoutId);
  d.setAttribute('data-myrm-theme-art',artOn);
  if(pre&&pre.dualAccent){d.setAttribute('data-myrm-theme-dual-accent','true');}else{d.setAttribute('data-myrm-theme-dual-accent','false');}
  if(pre&&pre.primary){
    d.style.setProperty('--primary',pre.primary);
    d.style.setProperty('--primary-foreground',pre.primaryForeground||'#fbfbf8');
    d.style.setProperty('--primary-hover',pre.primaryHover||pre.primary);
    if(pre.accentWarm)d.style.setProperty('--accent-warm',pre.accentWarm);
  }else if(isDark){
    d.style.setProperty('--primary','#6ba3aa');
    d.style.setProperty('--primary-foreground','#0a0a0a');
    d.style.setProperty('--primary-hover','#7eb5bc');
    d.style.setProperty('--accent-warm','#f5b868');
  }else{
    d.style.setProperty('--primary','#588e95');
    d.style.setProperty('--primary-foreground','#fbfbf8');
    d.style.setProperty('--primary-hover','#4a7d84');
    d.style.setProperty('--accent-warm','#e07830');
  }
  if(pre&&pre.artPosterUrl&&artOn==='on'){
    var preloadId='myrm-theme-art-preload';
    var existing=document.getElementById(preloadId);
    if(!existing){
      var link=document.createElement('link');
      link.id=preloadId;
      link.rel='preload';
      link.as='image';
      link.href=pre.artPosterUrl;
      document.head.appendChild(link);
    }
    if(typeof pre.artWash==='number'){
      d.style.setProperty('--myrm-theme-art-wash',String(pre.artWash));
    }
  }
  localStorage.removeItem('myrm-skin');
  localStorage.removeItem('myrm-font');
} catch(e){}
`.trim();
