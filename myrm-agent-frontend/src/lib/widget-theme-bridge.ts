/**
 * Widget Theme Bridge
 *
 * Maps host application CSS variables to widget-friendly tokens,
 * provides scoped utility classes and pre-styled form elements
 * for AI-generated HTML widgets rendered inside sandboxed iframes.
 *
 * The bridge ensures widgets inherit the current theme (light/dark)
 * without loading external CSS frameworks like Tailwind CDN.
 */

// CSS variable names to resolve from the host document
const THEME_VAR_NAMES = [
  '--background',
  '--foreground',
  '--card',
  '--card-foreground',
  '--primary',
  '--primary-foreground',
  '--primary-hover',
  '--secondary',
  '--secondary-foreground',
  '--muted',
  '--muted-foreground',
  '--accent',
  '--accent-foreground',
  '--destructive',
  '--border',
  '--input',
  '--ring',
  '--chart-1',
  '--chart-2',
  '--chart-3',
  '--chart-4',
  '--chart-5',
  '--radius',
] as const;

/**
 * Read computed CSS variable values from the host document.
 * Must be called client-side only.
 */
export function resolveThemeVars(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  const computed = getComputedStyle(document.documentElement);
  const vars: Record<string, string> = {};
  for (const name of THEME_VAR_NAMES) {
    const val = computed.getPropertyValue(name).trim();
    if (val) vars[name] = val;
  }
  // Detect dark mode
  vars['--is-dark'] = document.documentElement.classList.contains('dark') ? '1' : '0';
  return vars;
}

// Semantic CSS variable bridge (maps guideline names to host tokens)
const CSS_BRIDGE = `
  --widget-bg: var(--background);
  --widget-bg-secondary: var(--muted);
  --widget-bg-card: var(--card);
  --widget-text: var(--foreground);
  --widget-text-secondary: var(--muted-foreground);
  --widget-text-card: var(--card-foreground);
  --widget-border: var(--border);
  --widget-input: var(--input);
  --widget-primary: var(--primary);
  --widget-primary-fg: var(--primary-foreground);
  --widget-primary-hover: var(--primary-hover);
  --widget-destructive: var(--destructive);
  --widget-ring: var(--ring);
  --widget-radius: var(--radius);
  --widget-chart-1: var(--chart-1);
  --widget-chart-2: var(--chart-2);
  --widget-chart-3: var(--chart-3);
  --widget-chart-4: var(--chart-4);
  --widget-chart-5: var(--chart-5);
`;

// Scoped utility classes (Tailwind-like subset)
const UTILITY_CLASSES = `
.flex{display:flex}.inline-flex{display:inline-flex}.grid{display:grid}.block{display:block}.hidden{display:none}
.flex-col{flex-direction:column}.flex-row{flex-direction:row}.flex-wrap{flex-wrap:wrap}.flex-1{flex:1 1 0%}.flex-none{flex:none}.shrink-0{flex-shrink:0}
.items-start{align-items:flex-start}.items-center{align-items:center}.items-end{align-items:flex-end}
.justify-start{justify-content:flex-start}.justify-center{justify-content:center}.justify-end{justify-content:flex-end}.justify-between{justify-content:space-between}
.grid-cols-1{grid-template-columns:repeat(1,minmax(0,1fr))}.grid-cols-2{grid-template-columns:repeat(2,minmax(0,1fr))}.grid-cols-3{grid-template-columns:repeat(3,minmax(0,1fr))}.grid-cols-4{grid-template-columns:repeat(4,minmax(0,1fr))}
.gap-1{gap:4px}.gap-2{gap:8px}.gap-3{gap:12px}.gap-4{gap:16px}.gap-6{gap:24px}.gap-8{gap:32px}
.m-0{margin:0}.m-2{margin:8px}.m-4{margin:16px}.mx-auto{margin-left:auto;margin-right:auto}
.mt-1{margin-top:4px}.mt-2{margin-top:8px}.mt-4{margin-top:16px}.mb-2{margin-bottom:8px}.mb-4{margin-bottom:16px}
.p-0{padding:0}.p-2{padding:8px}.p-3{padding:12px}.p-4{padding:16px}.p-6{padding:24px}
.px-2{padding-left:8px;padding-right:8px}.px-3{padding-left:12px;padding-right:12px}.px-4{padding-left:16px;padding-right:16px}
.py-1{padding-top:4px;padding-bottom:4px}.py-2{padding-top:8px;padding-bottom:8px}.py-3{padding-top:12px;padding-bottom:12px}
.w-full{width:100%}.w-auto{width:auto}.h-full{height:100%}.h-auto{height:auto}.min-h-0{min-height:0}
.max-w-full{max-width:100%}.max-w-sm{max-width:384px}.max-w-md{max-width:448px}.max-w-lg{max-width:512px}
.text-xs{font-size:12px;line-height:1.5}.text-sm{font-size:14px;line-height:1.5}.text-base{font-size:16px;line-height:1.6}.text-lg{font-size:18px;line-height:1.6}.text-xl{font-size:20px;line-height:1.4}.text-2xl{font-size:24px;line-height:1.3}.text-3xl{font-size:30px;line-height:1.2}
.font-normal{font-weight:400}.font-medium{font-weight:500}.font-semibold{font-weight:600}.font-bold{font-weight:700}
.text-left{text-align:left}.text-center{text-align:center}.text-right{text-align:right}
.truncate{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.tabular-nums{font-variant-numeric:tabular-nums}
.rounded{border-radius:8px}.rounded-md{border-radius:6px}.rounded-lg{border-radius:12px}.rounded-xl{border-radius:16px}.rounded-full{border-radius:9999px}
.border{border:1px solid var(--widget-border)}.border-0{border-width:0}.border-t{border-top:1px solid var(--widget-border)}.border-b{border-bottom:1px solid var(--widget-border)}
.overflow-hidden{overflow:hidden}.overflow-auto{overflow:auto}.overflow-x-auto{overflow-x:auto}
.relative{position:relative}.absolute{position:absolute}.inset-0{top:0;right:0;bottom:0;left:0}
.opacity-50{opacity:.5}.opacity-75{opacity:.75}.cursor-pointer{cursor:pointer}.select-none{user-select:none}
.transition{transition:all .15s ease}.transition-colors{transition:color .15s,background-color .15s,border-color .15s}
.{box-shadow:0 1px 2px rgba(0,0,0,.05)}
.bg-widget{background:var(--widget-bg)}.bg-widget-secondary{background:var(--widget-bg-secondary)}.bg-widget-card{background:var(--widget-bg-card)}.bg-transparent{background:transparent}
.text-widget{color:var(--widget-text)}.text-widget-secondary{color:var(--widget-text-secondary)}.text-widget-primary{color:var(--widget-primary)}
.border-widget{border-color:var(--widget-border)}
.space-y-1>*+*{margin-top:4px}.space-y-2>*+*{margin-top:8px}.space-y-3>*+*{margin-top:12px}.space-y-4>*+*{margin-top:16px}
`;

// Pre-styled form elements
const FORM_STYLES = `
input[type="range"]{height:4px;-webkit-appearance:none;appearance:none;background:var(--widget-border);border-radius:2px;outline:none}
input[type="range"]::-webkit-slider-thumb{-webkit-appearance:none;width:18px;height:18px;border-radius:50%;background:var(--widget-primary);cursor:pointer}
input[type="text"],input[type="number"],select,textarea{height:36px;padding:0 10px;border:1px solid var(--widget-border);border-radius:var(--widget-radius);background:var(--widget-bg);color:var(--widget-text);font-size:14px;font-family:inherit;outline:none}
input:focus,select:focus,textarea:focus{border-color:var(--widget-primary);box-shadow:0 0 0 2px color-mix(in srgb,var(--widget-primary) 30%,transparent)}
button{background:transparent;border:1px solid var(--widget-border);border-radius:var(--widget-radius);padding:6px 14px;font-size:14px;font-family:inherit;color:var(--widget-text);cursor:pointer;transition:background .15s,transform .1s}
button:hover{background:var(--widget-bg-secondary)}
button:active{transform:scale(.98)}
`;

/**
 * Generate the full CSS style block for iframe srcdoc.
 * Includes resolved theme variables, semantic bridge, utility classes,
 * form styles, and runtime scripts for height sync + link interception.
 */
export function buildWidgetStyleBlock(resolvedVars: Record<string, string>): string {
  const rootVars = Object.entries(resolvedVars)
    .filter(([k]) => k !== '--is-dark')
    .map(([k, v]) => `${k}:${v};`)
    .join('');
  const isDark = resolvedVars['--is-dark'] === '1';

  return `<style>
:root{${rootVars}}
${isDark ? '.dark{color-scheme:dark}' : ''}
body{${CSS_BRIDGE}
  margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
  font-size:16px;line-height:1.6;color:var(--widget-text);background:transparent;
}
*{box-sizing:border-box}
a{color:var(--widget-primary);text-decoration:none;cursor:pointer}
a:hover{text-decoration:underline}
${UTILITY_CLASSES}
${FORM_STYLES}
@keyframes widgetFadeIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
</style>`;
}

/**
 * Generate the runtime script injected into iframe srcdoc.
 * Handles:
 * 1. Height synchronization via ResizeObserver + postMessage
 * 2. Link click interception (opens in parent window)
 * 3. Theme update reception via postMessage
 * 4. Element picker mode (toggled by parent via postMessage)
 */
export function buildWidgetRuntimeScript(): string {
  return `<script>
(function(){
  // Height sync: observe body size changes and notify parent
  var lastH=0;
  function syncHeight(){
    var h=document.documentElement.scrollHeight;
    if(Math.abs(h-lastH)>=4){lastH=h;window.parent.postMessage({type:'widget-resize',height:h},'*')}
  }
  if(window.ResizeObserver){
    new ResizeObserver(syncHeight).observe(document.body);
  }
  syncHeight();
  setTimeout(syncHeight,100);
  setTimeout(syncHeight,500);

  // Link interception: external links open in parent
  document.addEventListener('click',function(e){
    if(window.__pickerActive)return;
    var a=e.target;
    while(a&&a.tagName!=='A')a=a.parentElement;
    if(!a||!a.href)return;
    var url=a.href;
    if(url.startsWith('#')||url.startsWith('javascript:'))return;
    e.preventDefault();
    window.parent.postMessage({type:'widget-navigate',url:url},'*');
  },true);

  // --- Element Picker ---
  window.__pickerActive=false;
  var overlay=null;
  var SKIP_TAGS={HTML:1,HEAD:1,BODY:1,SCRIPT:1,STYLE:1,LINK:1,META:1,NOSCRIPT:1};

  function bubbleUp(el){
    while(el&&el.parentElement){
      var tag=el.tagName;
      if(tag==='SPAN'||tag==='I'||tag==='B'||tag==='STRONG'||tag==='EM'||tag==='SMALL'||tag==='BR'){
        var p=el.parentElement;
        if(p&&!SKIP_TAGS[p.tagName]){el=p;continue}
      }
      break;
    }
    return el;
  }

  function cssSelector(el){
    var parts=[];
    while(el&&el.nodeType===1&&el.tagName!=='HTML'&&el.tagName!=='BODY'){
      var tag=el.tagName.toLowerCase();
      if(el.id){parts.unshift(tag+'#'+el.id);break}
      var cls=Array.prototype.slice.call(el.classList).filter(function(c){return c.indexOf('__picker')!==0}).slice(0,2).join('.');
      var seg=cls?tag+'.'+cls:tag;
      var parent=el.parentElement;
      if(parent){
        var siblings=parent.children;
        var same=0,idx=0;
        for(var i=0;i<siblings.length;i++){if(siblings[i].tagName===el.tagName){same++;if(siblings[i]===el)idx=same}}
        if(same>1)seg+=':nth-of-type('+idx+')';
      }
      parts.unshift(seg);
      el=parent;
      if(parts.length>=5)break;
    }
    return parts.join(' > ');
  }

  function breadcrumb(el){
    var crumbs=[];
    while(el&&el.nodeType===1&&el.tagName!=='HTML'){
      var tag=el.tagName.toLowerCase();
      if(tag==='body'){crumbs.unshift('body');break}
      var cls=el.classList.length?'.'+el.classList[0]:'';
      var id=el.id?'#'+el.id:'';
      crumbs.unshift(tag+id+cls);
      el=el.parentElement;
      if(crumbs.length>=6)break;
    }
    return crumbs.join(' > ');
  }

  function truncateHtml(html,max){return html.length>max?html.substring(0,max)+'...':html}

  function showOverlay(el){
    removeOverlay();
    var rect=el.getBoundingClientRect();
    overlay=document.createElement('div');
    overlay.className='__picker-overlay';
    overlay.style.cssText='position:fixed;pointer-events:none;z-index:999999;border:2px solid hsl(var(--widget-primary,217 91% 60%));background:hsla(var(--widget-primary,217 91% 60%),.08);transition:all .1s ease;';
    overlay.style.top=rect.top+'px';overlay.style.left=rect.left+'px';
    overlay.style.width=rect.width+'px';overlay.style.height=rect.height+'px';
    var label=document.createElement('div');
    label.className='__picker-label';
    label.style.cssText='position:absolute;top:-20px;left:0;font-size:11px;line-height:1;padding:2px 6px;border-radius:3px;background:hsl(var(--widget-primary,217 91% 60%));color:#fff;white-space:nowrap;font-family:monospace;pointer-events:none;';
    label.textContent=el.tagName.toLowerCase()+(el.id?'#'+el.id:el.classList.length?'.'+el.classList[0]:'');
    overlay.appendChild(label);
    document.body.appendChild(overlay);
  }

  function removeOverlay(){if(overlay){overlay.remove();overlay=null}}

  function onHover(e){
    if(!window.__pickerActive)return;
    var el=bubbleUp(e.target);
    if(!el||SKIP_TAGS[el.tagName])return;
    showOverlay(el);
  }
  function onPickClick(e){
    if(!window.__pickerActive)return;
    e.preventDefault();e.stopPropagation();e.stopImmediatePropagation();
    var el=bubbleUp(e.target);
    if(!el||SKIP_TAGS[el.tagName])return;
    removeOverlay();
    window.__pickerActive=false;
    document.body.style.cursor='';
    window.parent.postMessage({
      type:'widget-element-pick',
      selector:cssSelector(el),
      breadcrumb:breadcrumb(el),
      tagName:el.tagName.toLowerCase(),
      outerHTML:truncateHtml(el.outerHTML,800)
    },'*');
  }

  window.addEventListener('message',function(e){
    if(!e.data||typeof e.data!=='object')return;
    if(e.data.type==='widget-theme-update'){
      var vars=e.data.vars;var root=document.documentElement;
      for(var k in vars){if(vars.hasOwnProperty(k))root.style.setProperty(k,vars[k])}
    }
    if(e.data.type==='widget-picker-toggle'){
      window.__pickerActive=!!e.data.active;
      if(window.__pickerActive){
        document.body.style.cursor='crosshair';
      }else{
        document.body.style.cursor='';
        removeOverlay();
      }
    }
  });
  document.addEventListener('mouseover',onHover,true);
  document.addEventListener('click',onPickClick,true);
})();
</script>`;
}

// CDN allowlist for Content-Security-Policy
const CDN_ALLOWLIST = [
  'https://cdnjs.cloudflare.com',
  'https://cdn.jsdelivr.net',
  'https://unpkg.com',
  'https://esm.sh',
  'https://fonts.googleapis.com',
  'https://fonts.gstatic.com',
].join(' ');

/**
 * Build the Content-Security-Policy meta tag for widget iframe.
 */
export function buildWidgetCSP(): string {
  return `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' ${CDN_ALLOWLIST}; style-src 'unsafe-inline' ${CDN_ALLOWLIST}; img-src * data: blob:; font-src ${CDN_ALLOWLIST}; connect-src 'none'; media-src 'none'; frame-src 'none';">`;
}

/**
 * Strip all <script> tags from HTML for streaming preview (phase 1).
 * Returns sanitized HTML safe for visual-only rendering.
 */
export function stripScriptsForStreaming(html: string): string {
  return html.replace(/<script[\s\S]*?<\/script>/gi, '');
}

/**
 * Build the localStorage polyfill script for sandboxed iframes.
 * Overrides window.localStorage with a postMessage-based bridge that
 * communicates with the host to persist data in server-side SQLite.
 *
 * @param initialData - Pre-hydrated key-value pairs to avoid async loading race
 */
export function buildWidgetStorageScript(initialData: Record<string, string> = {}): string {
  const serializedData = JSON.stringify(initialData).replace(/<\//g, '<\\/');
  return `<script>
(function(){
  var _cache = ${serializedData};
  var _pendingWrites = {};
  var _debounceTimer = null;
  var DEBOUNCE_MS = 300;

  function _flush(){
    var entries = _pendingWrites;
    _pendingWrites = {};
    _debounceTimer = null;
    var keys = Object.keys(entries);
    if(!keys.length) return;
    var batch = keys.map(function(k){ return {key:k, value:entries[k]} });
    window.parent.postMessage({type:'widget-storage-batch', entries:batch},'*');
  }

  function _scheduleBatch(key, value){
    _pendingWrites[key] = value;
    if(_debounceTimer) clearTimeout(_debounceTimer);
    _debounceTimer = setTimeout(_flush, DEBOUNCE_MS);
  }

  var storage = {
    getItem: function(key){
      var v = _cache[key];
      return v === undefined ? null : v;
    },
    setItem: function(key, value){
      value = String(value);
      _cache[key] = value;
      _scheduleBatch(key, value);
    },
    removeItem: function(key){
      delete _cache[key];
      window.parent.postMessage({type:'widget-storage-remove', key:key},'*');
    },
    clear: function(){
      _cache = {};
      window.parent.postMessage({type:'widget-storage-clear'},'*');
    },
    key: function(n){
      return Object.keys(_cache)[n] || null;
    },
    get length(){
      return Object.keys(_cache).length;
    }
  };

  try{
    Object.defineProperty(window, 'localStorage', {
      value: storage, writable: false, configurable: true
    });
  }catch(e){}

  window.addEventListener('beforeunload', function(){
    if(_debounceTimer){ clearTimeout(_debounceTimer); _flush(); }
  });

  window.addEventListener('message', function(e){
    if(!e.data || typeof e.data !== 'object') return;
    if(e.data.type === 'widget-storage-quota-error'){
      var err = new DOMException('QuotaExceededError','QuotaExceededError');
      console.error('Widget storage quota exceeded:', e.data.key, err);
    }
  });
})();
</script>`;
}

/**
 * Build complete srcdoc HTML for the widget iframe.
 *
 * @param widgetHtml - The raw HTML content to render
 * @param themeVars - Resolved CSS variables from the host
 * @param isStreaming - If true, strips scripts for safe visual preview
 * @param storageData - Pre-hydrated KV data for localStorage polyfill
 */
export function buildWidgetSrcdoc(
  widgetHtml: string,
  themeVars: Record<string, string>,
  isStreaming: boolean,
  storageData?: Record<string, string>,
): string {
  const safeHtml = isStreaming ? stripScriptsForStreaming(widgetHtml) : widgetHtml;
  const isDark = themeVars['--is-dark'] === '1';
  const storageScript = !isStreaming && storageData ? buildWidgetStorageScript(storageData) : '';

  return `<!DOCTYPE html>
<html${isDark ? ' class="dark"' : ''}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
${buildWidgetCSP()}
${storageScript}
${buildWidgetStyleBlock(themeVars)}
</head>
<body>
${safeHtml}
${isStreaming ? '' : buildWidgetRuntimeScript()}
</body>
</html>`;
}
