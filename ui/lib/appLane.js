// The app lane (2026-10-16). Pure functions, shared by the /api/bf proxy, the console's own API routes
// and the app host page; tests/test_app_lane.py runs them under node.
//
// The finding: installed brain apps ran in an iframe sandboxed with allow-same-origin, so app code had
// the console's origin. The /api/bf proxy adds the owner key to every request, and /api/cli-info hands
// the key out, so an app could read local-only memory, chat history and settings, call admin routes,
// mint permits, or copy the owner key off the box. The fix has three layers:
//
//   1. The iframe drops allow-same-origin and every app file is served with
//      `Content-Security-Policy: sandbox allow-scripts allow-downloads`, so an app document has an
//      opaque origin however it is opened (framed by the console, or opened directly in a tab). It
//      cannot touch the parent page, its storage, or its fetch.
//   2. The proxy (and /api/permit, /api/cli-info, /api/proposal-decide) refuse any request that comes
//      from a page that is not the console itself: Origin "null", Sec-Fetch-Site cross-site/same-site,
//      or a Referer inside /api/bf/apps/. Only the app's own files (GET/HEAD apps/<id>/<file>) and the
//      app's own backend (apps/<id>/api/...) pass, and both go upstream WITHOUT the owner key.
//   3. The postMessage bridge in the host page stays the only way an app acts (ui/lib/appBridge.js).
//
// An opaque origin has no localStorage, so the app's own files get a small shim injected at the top
// of their HTML: localStorage and sessionStorage become in-page stores, and localStorage writes are
// sent to the host page, which keeps them per app (ui/lib/appBridge.js) and seeds them back on load.

// Manifest id pattern (api/schemas/brain-app.schema.json).
const APP_ID_RE = /^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$/
// First segments under apps/ that are the brain's own apps router (api/apps.py), never an app.
const APPS_ROUTER_WORDS = new Set(['list', 'install', 'packs'])

// The sandbox for app documents. Same list as the iframe's sandbox attribute in ui/pages/apps/[id].js.
// No allow-same-origin (the point), no allow-forms (apps use onClick), no popups, no top navigation.
const APP_SANDBOX = 'allow-scripts allow-downloads'
const APP_CSP = `sandbox ${APP_SANDBOX}`

function header(headers, name) {
  const v = headers ? headers[name] : undefined
  return Array.isArray(v) ? v[0] : (v == null ? '' : String(v))
}

// Does this request come from a page other than the console itself (an app frame, another site)?
// Browsers send Sec-Fetch-Site on every request; Origin is "null" from an opaque origin; a Referer
// inside /api/bf/apps/ is an app document that kept a real origin (only if the sandbox were undone).
// A request with none of these (curl, the CLI, server to server) is not a browser page and passes.
function fromForeignPage(headers) {
  const site = header(headers, 'sec-fetch-site').toLowerCase()
  if (site === 'cross-site' || site === 'same-site') return true
  if (header(headers, 'origin').toLowerCase() === 'null') return true
  const ref = header(headers, 'referer')
  if (ref) {
    let p = ''
    try { p = new URL(ref, 'http://x').pathname } catch (_) { p = '' }
    if (p.startsWith('/api/bf/apps/')) return true
  }
  return false
}

// Where an /api/bf path goes. Segments are the decoded catch-all parts (req.query.path).
//   { kind: 'app-static', appId }  GET/HEAD of an app's own file
//   { kind: 'app-api', appId }     the app's own backend router (apps/<id>/api/...)
//   { kind: 'core' }               everything else: the brain api with owner authority
//   { kind: 'bad' }                a path that tries to climb out (., .., empty, slashes in a segment)
function classify(parts, method) {
  const segs = Array.isArray(parts) ? parts.map(String) : [String(parts || '')]
  for (const s of segs) {
    if (s === '' || s === '.' || s === '..' || s.includes('/') || s.includes('\\') || s.includes('\0')) return { kind: 'bad' }
  }
  if (segs[0] === 'apps' && segs.length >= 3 && APP_ID_RE.test(segs[1]) && !APPS_ROUTER_WORDS.has(segs[1])) {
    const appId = segs[1]
    if (segs[2] === 'api') return { kind: 'app-api', appId }
    const m = String(method || 'GET').toUpperCase()
    if (m === 'GET' || m === 'HEAD') return { kind: 'app-static', appId }
    return { kind: 'core' }
  }
  return { kind: 'core' }
}

// The proxy's decision for one request.
//   { action: 'refuse', status, error }
//   { action: 'forward', ownerKey: bool, appFile: bool, cors: bool }
// ownerKey: attach BRAIN_API_KEY. appFile: an app document or asset (sandbox CSP, shim into HTML).
// cors: the caller is an app frame reading its own files or backend (opaque origin needs CORS).
function decide(parts, method, headers) {
  const c = classify(parts, method)
  if (c.kind === 'bad') return { action: 'refuse', status: 400, error: 'bad_path' }
  const foreign = fromForeignPage(headers)
  if (c.kind === 'app-static') return { action: 'forward', ownerKey: false, appFile: true, cors: foreign, appId: c.appId }
  if (c.kind === 'app-api') return { action: 'forward', ownerKey: !foreign, appFile: false, cors: foreign, appId: c.appId }
  if (foreign) return { action: 'refuse', status: 403, error: 'app_frame_refused' }
  return { action: 'forward', ownerKey: true, appFile: false, cors: false }
}

// CORS for an app frame reading its own files: the frame's origin serializes as "null". Credentials
// are allowed so the console's login (Caddy basicauth) still covers module scripts and fetches of the
// app's own assets. Only app files and app backends ever carry these headers, never a core route.
function corsHeaders(reqHeaders) {
  return {
    'access-control-allow-origin': 'null',
    'access-control-allow-credentials': 'true',
    'access-control-allow-methods': 'GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS',
    'access-control-allow-headers': header(reqHeaders, 'access-control-request-headers') || 'content-type',
    'access-control-max-age': '600',
    vary: 'Origin',
  }
}

// The shim every app HTML gets first in <head>. Runs in the app's opaque origin, before app code.
// localStorage: seeded from window.name (the host page writes the app's saved store there, see
// appBridge.seedName), writes posted to the host as 'storage.set' / 'storage.remove' / 'storage.clear'.
// sessionStorage: in-page only. fetch and XMLHttpRequest to the console's own host carry the login
// (an opaque origin sends none by default). A Worker from the app's own files, which an opaque origin
// may not start directly, starts from a small script that loads the same file with the same login patch
// (a blob for a classic worker; a data: URL for a module worker, the one form Chromium runs there).
// A classic worker the app starts from its own blob gets the same patch the same way.
const SHIM_JS = `(function(){
var PFX='bf-app-storage:';var seed={};
try{if(typeof window.name==='string'&&window.name.indexOf(PFX)===0){seed=JSON.parse(window.name.slice(PFX.length))||{};window.name='';}}catch(e){seed={};}
function mk(data,sync){var s={};
function post(m){if(!sync)return;try{m.request_id='bf-storage-'+Math.random().toString(36).slice(2);window.parent.postMessage(m,'*');}catch(e){}}
Object.defineProperties(s,{
length:{get:function(){return Object.keys(data).length;}},
key:{value:function(i){var k=Object.keys(data);return i>=0&&i<k.length?k[i]:null;}},
getItem:{value:function(k){k=String(k);return Object.prototype.hasOwnProperty.call(data,k)?data[k]:null;}},
setItem:{value:function(k,v){k=String(k);v=String(v);data[k]=v;post({type:'storage.set',payload:{key:k,value:v}});}},
removeItem:{value:function(k){k=String(k);delete data[k];post({type:'storage.remove',payload:{key:k}});}},
clear:{value:function(){for(var k in data)delete data[k];post({type:'storage.clear',payload:{}});}}
});return s;}
var real=null;try{real=window.localStorage;}catch(e){real=null;}
if(!real){try{Object.defineProperty(window,'localStorage',{value:mk(seed,true),configurable:true});}catch(e){}
try{Object.defineProperty(window,'sessionStorage',{value:mk({},false),configurable:true});}catch(e){}}
var host=location.protocol+'//'+location.host;
var CRED=function(G,host){function own(u){try{return new URL(u,G.location.href).origin===host;}catch(e){return false;}}
if(G.fetch){var f=G.fetch;G.fetch=function(input,init){try{var u=typeof input==='string'?input:(input&&input.url);if(own(u)&&!(init&&init.credentials)){init=Object.assign({},init||{},{credentials:'include'});}}catch(e){}return f.call(this,input,init);};}
if(G.XMLHttpRequest){var o=G.XMLHttpRequest.prototype.open;G.XMLHttpRequest.prototype.open=function(m,u){try{if(own(u))this.withCredentials=true;}catch(e){}return o.apply(this,arguments);};}};
CRED(window,host);
if(window.Worker){var W=window.Worker;var BW=function(url,opts){var u;try{u=new URL(String(url),location.href);}catch(e){return new W(url,opts);}
var mod=!!(opts&&opts.type==='module');
if(u.origin!==host&&!(u.protocol==='blob:'&&!mod))return new W(url,opts);
var pre='('+CRED.toString()+')(self,'+JSON.stringify(host)+');';
var src=mod?pre+'import '+JSON.stringify(u.href)+';':pre+'importScripts('+JSON.stringify(u.href)+');';
var o=Object.assign({},opts||{});if(mod&&!o.credentials)o.credentials='include';
var w=mod?'data:text/javascript;charset=utf-8,'+encodeURIComponent(src):URL.createObjectURL(new Blob([src],{type:'text/javascript'}));
return new W(w,o);};
BW.prototype=W.prototype;window.Worker=BW;}
})();`

// A URL in the app's own files (relative, or root-relative on the console's host), not a CDN.
function ownUrl(u) {
  const v = String(u || '').trim()
  if (!v) return false
  return !/^[a-z][a-z0-9+.-]*:/i.test(v) && !v.startsWith('//')
}

// Put the shim first in <head>, and give the app's own module scripts and CORS links the login
// (crossorigin="use-credentials"). Tags pointing at another host keep what they had: a CDN that
// answers "Access-Control-Allow-Origin: *" refuses credentialed requests.
function injectShim(html) {
  let s = String(html)
  const tag = `<script data-bf-app-shim>${SHIM_JS}</script>`
  s = s.replace(/<(script|link)\b[^>]*>/gi, (t, name) => {
    const m = t.match(/\s(?:src|href)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/i)
    const url = m ? (m[1] ?? m[2] ?? m[3]) : ''
    if (!ownUrl(url)) return t
    const isModule = name.toLowerCase() === 'script' && /\btype\s*=\s*["']?module["']?/i.test(t)
    if (/\scrossorigin\b/i.test(t)) return t.replace(/\scrossorigin(\s*=\s*("[^"]*"|'[^']*'|[^\s>]+))?/i, ' crossorigin="use-credentials"')
    if (isModule) return t.replace(/^<script\b/i, '<script crossorigin="use-credentials"')
    return t
  })
  const head = s.match(/<head\b[^>]*>/i)
  if (head) return s.replace(head[0], head[0] + tag)
  const htmlTag = s.match(/<html\b[^>]*>/i)
  if (htmlTag) return s.replace(htmlTag[0], htmlTag[0] + tag)
  return tag + s
}

module.exports = { APP_ID_RE, APP_SANDBOX, APP_CSP, SHIM_JS, fromForeignPage, classify, decide, corsHeaders, injectShim }
