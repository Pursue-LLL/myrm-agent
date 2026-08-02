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
  var functionalPrefixes=['/kanban','/settings','/projects','/eval-lab','/brain','/library','/artifacts','/cron','/work','/workspace','/audit','/security','/agents','/canvas','/batch-optimization','/skill-optimization','/journey','/subscription','/pricing','/health','/mobile','/auth','/payment','/growth'];
  var staticSegments={'agents':1,'audit':1,'artifacts':1,'auth':1,'batch-optimization':1,'brain':1,'canvas':1,'chat':1,'eval-lab':1,'growth':1,'health':1,'journey':1,'library':1,'mobile':1,'payment':1,'pricing':1,'projects':1,'security':1,'settings':1,'skill-optimization':1,'subscription':1,'workspace':1,'kanban':1,'cron':1,'work':1};
  var path=(location.pathname||'/').split('?')[0];
  if(path.length>1&&path.charAt(path.length-1)==='/'){path=path.slice(0,-1);}
  if(!path){path='/';}
  var sceneId='functional';
  if(path==='/'||path==='/chat'){sceneId='immersive';}
  else{
    var matched=false;
    for(var i=0;i<functionalPrefixes.length;i++){
      var p=functionalPrefixes[i];
      if(path===p||path.indexOf(p+'/')===0){matched=true;break;}
    }
    if(!matched){
      var segMatch=/^\/([^/]+)$/.exec(path);
      if(segMatch&&!staticSegments[segMatch[1]]){sceneId='immersive';}
    }
  }
  d.setAttribute('data-myrm-theme-profile',profileId);
  d.setAttribute('data-myrm-theme-layout',layoutId);
  d.setAttribute('data-myrm-theme-scene',sceneId);
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
  if(sceneId==='functional'&&artOn==='on'){
    d.style.setProperty('--myrm-theme-nav-opacity','0.92');
    d.style.setProperty('--myrm-theme-sidebar-opacity','0.9');
    d.style.setProperty('--myrm-theme-main-opacity','0.94');
    d.style.setProperty('--myrm-theme-surface-opacity','0.96');
    var wash=pre&&typeof pre.artWash==='number'?Math.max(pre.artWash,0.55):0.55;
    d.style.setProperty('--myrm-theme-art-wash',String(wash));
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
    if(sceneId!=='functional'&&typeof pre.artWash==='number'){
      d.style.setProperty('--myrm-theme-art-wash',String(pre.artWash));
    }
  }
  localStorage.removeItem('myrm-skin');
  localStorage.removeItem('myrm-font');
} catch(e){}
