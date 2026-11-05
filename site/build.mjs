import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {marked} from 'marked';
import {renderHome,renderResults} from './product.mjs';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const out=path.join(root,'site-build');
const origin=(process.env.SITE_ORIGIN||'https://developerjillur.github.io').replace(/\/$/,'');
const base=`/${(process.env.SITE_BASE_PATH||'ffmpeg-v2').replace(/^\/+|\/+$/g,'')}/`;
const repo='https://github.com/developerjillur/ffmpeg-v2';
const date='2026-11-05';
const socialImage='assets/social.png?v='+createHash('sha256').update(fs.readFileSync(path.join(root,'site/assets/social.png'))).digest('hex').slice(0,12);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const routes=new Map([
 ['README.md',''],['docs/WHY-FFMPEG-V2.md','why-ffmpeg-v2/'],['docs/WORKFLOW-RESULTS.md','benchmarks/released-workflow/'],['docs/GETTING-STARTED.md','getting-started/'],['docs/CLI.md','cli/'],
 ['docs/MCP-PUBLIC.md','mcp/'],['docs/PYTHON.md','python/'],['docs/CONFIGURATION.md','configuration/'],
 ['docs/BENCHMARKS.md','benchmarks/method/'],['docs/REPORTS.md','reports/guide/'],
 ['docs/ARCHITECTURE.md','architecture/'],['docs/LIMITATIONS.md','limitations/'],
 ['docs/NATIVE-BUILDS.md','native-builds/'],['CONTRIBUTING.md','contributing/'],
 ['docs/PUBLICATION.md','publication/'],['docs/DISCOVERY.md','discovery/'],['docs/ROADMAP.md','roadmap/'],
 ['SECURITY.md','security/'],['CHANGELOG.md','changelog/'],['SUPPORT.md','support/'],
 ['CODE_OF_CONDUCT.md','community/'],['THIRD-PARTY-NOTICES.md','licenses/'],
 ['README.bn.md','reports/historical-overview/'],['docs/site/RESEARCH.md','publication/research/'],
 ['docs/site/BRIEF.md','publication/brief/']
]);
function walk(dir){return fs.readdirSync(path.join(root,dir),{withFileTypes:true}).flatMap(e=>e.isDirectory()?walk(path.posix.join(dir,e.name)):[path.posix.join(dir,e.name)]);}
const docs=[...fs.readdirSync(root).filter(f=>f.endsWith('.md')), ...walk('docs').filter(f=>f.endsWith('.md')),
 ...walk('third_party').filter(f=>f.endsWith('README.md'))];
for(const file of docs)if(!routes.has(file))routes.set(file,`reports/${file.replace(/\.md$/i,'').replaceAll('/','-').toLowerCase()}/`);
const publicGuides=new Set(['docs/WHY-FFMPEG-V2.md','docs/WORKFLOW-RESULTS.md','README.md','docs/GETTING-STARTED.md','docs/CLI.md','docs/MCP-PUBLIC.md','docs/PYTHON.md','docs/CONFIGURATION.md','docs/BENCHMARKS.md','docs/REPORTS.md','docs/LIMITATIONS.md','docs/NATIVE-BUILDS.md','docs/PUBLICATION.md','docs/DISCOVERY.md','docs/ROADMAP.md','CONTRIBUTING.md','SECURITY.md','SUPPORT.md','CODE_OF_CONDUCT.md','THIRD-PARTY-NOTICES.md','CHANGELOG.md','docs/site/RESEARCH.md','docs/site/BRIEF.md']);
const titleOverrides={
 'docs/PHASE11-RESULTS.md':'Phase 11 results: conditioned PGO, quality and retained default',
 'docs/PHASE11-RESEARCH.md':'Phase 11 method: CPU load, cache and paired confirmation',
 'docs/PHASE10-RESULTS.md':'Phase 10 results: x264 progress and wall-clock limits',
 'docs/PHASE9-RESULTS.md':'Phase 9 results: same-tuning HD/raw gaps and rejected lookahead',
 'docs/PHASE8-RESULTS.md':'Phase 8 results: scoped M4 Max thread-pool tuning',
 'docs/ARCHITECTURE.md':'Architecture: typed plan, supervision and verified publication',
 'docs/UPSTREAM.md':'Historical native build and source provenance',
 'README.bn.md':'বাংলা: local development and benchmark overview'
};
function sourceText(file){return fs.readFileSync(path.join(root,file),'utf8');}
function titleFor(file){return titleOverrides[file]||sourceText(file).match(/^#\s+(.+)$/m)?.[1]||path.basename(file);}
const descriptions={
 '':'Tuned FFmpeg workflows with recorded 22.61–28.48% less time vs prior Stock presets on M4 Max, plus MCP, durable queues and verified outputs.',
 'getting-started/':'Install FFmpeg-v2 from source on macOS. Configure local media paths, inspect a typed job plan and run a verified FFmpeg workflow.',
 'why-ffmpeg-v2/':'See how FFmpeg-v2 adds tuned M4 Max profiles, a durable queue, automatic output verification and eight local MCP tools to Stock FFmpeg.',
 'benchmarks/released-workflow/':'Recorded native M4 Max workflow gains: 22.61% less HD time and 28.48% less live-action time vs prior Stock presets, with quality and matched controls.',
 'mcp/':'Connect a local FFmpeg MCP server with eight typed tools. Plan, submit, explicitly start a worker, poll status and verify output.',
 'benchmarks/':'Compare FFmpeg-v2 workflow gains: 22.61% less HD time and 28.48% less live-action time vs prior Stock presets, with quality and same-tuning controls.',
 'reports/':'Inspect the technical methods, quality evidence, diagnostics and retained experiments behind the measured workflow improvements in FFmpeg-v2.'
};
function descriptionFor(route,title){return descriptions[route]||`${title}. FFmpeg-v2 source documentation, evidence and limitations by Jillur Rahman.`;}
const url=route=>base+route;
const canonical=route=>origin+url(route);
function navLink(label,route,current,cls=''){return `<a href="${url(route)}"${route===current?' aria-current="page"':''}${cls?` class="${cls}"`:''}>${label}</a>`;}
function header(route){return `<a class="skip" href="#main">Skip to content</a><header class="topbar"><div class="wrap"><nav class="nav" aria-label="Main"><a class="brand" href="${base}"><img src="${url('assets/mark.svg')}" width="38" height="38" alt=""><span>FFmpeg-v2</span></a><div class="navlinks">${navLink('Why FFmpeg-v2','why-ffmpeg-v2/',route)}${navLink('Docs','getting-started/',route)}${navLink('Results','benchmarks/',route)}<a class="repo" href="${repo}">GitHub <span aria-hidden="true">↗</span></a></div></nav></div></header>`;}
function footer(){return `<footer class="footer"><div class="wrap footer-row"><div><strong>FFmpeg-v2 · Jillur Rahman</strong><p>Independent local workflow toolkit. FFmpeg is the underlying engine. Source release 0.6.1 · GPL-3.0-or-later.</p></div><nav aria-label="Footer">${navLink('License','licenses/','_')}${navLink('Security','security/','_')}${navLink('Contribute','contributing/','_')}${navLink('Technical archive','reports/','_')}${navLink('Publication','publication/','_')}<a href="${url('sitemap.xml')}">Sitemap</a></nav></div></footer><div class="sr-only" id="announce" role="status" aria-live="polite"></div>`;}
function sidebar(route){const links=[['Why FFmpeg-v2','why-ffmpeg-v2/'],['Start here','getting-started/'],['CLI reference','cli/'],['MCP server','mcp/'],['Python integration','python/'],['Configuration','configuration/'],['Native builds','native-builds/'],['Architecture','architecture/'],['Results','benchmarks/'],['Technical archive','reports/'],['Limitations','limitations/'],['Contributing','contributing/']];return `<aside class="sidebar" aria-label="Documentation"><div class="eyebrow">Documentation</div>${links.map(([l,r])=>navLink(l,r,route)).join('')}</aside>`;}
const pages=[];
function write(route,title,body,{layout='article',file,lang='en',description,noindex=false}={}){
  const desc=description||descriptionFor(route,title);
  const metadata={ '@context':'https://schema.org','@type':route===''?'SoftwareSourceCode':'TechArticle',name:route===''?'FFmpeg-v2':title,
    description:desc,url:canonical(route),author:{'@type':'Person',name:'Jillur Rahman'},inLanguage:lang,
    ...(route===''?{codeRepository:repo,programmingLanguage:['Python','C'],runtimePlatform:'macOS',version:'0.6.1',license:repo+'/blob/main/LICENSE'}:{datePublished:date,isPartOf:{'@type':'WebSite',name:'FFmpeg-v2',url:canonical('')}})};
  const content=layout==='home'?body:`<div class="wrap article-shell">${sidebar(route)}<article class="article"><div class="meta"><span>FFMPEG-V2 / ${esc(route.split('/')[0])}</span>${file?`<a href="${repo}/blob/main/${esc(file)}">View source ↗</a>`:''}</div>${body}</article></div>`;
  const html=`<!doctype html><html lang="${lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(title)}${route?' | FFmpeg-v2':''}</title><meta name="description" content="${esc(desc)}"><link rel="canonical" href="${canonical(route)}"><meta name="robots" content="${noindex?'noindex,follow':'index,follow'}"><meta name="theme-color" content="#203d30"><meta property="og:type" content="${route?'article':'website'}"><meta property="og:site_name" content="FFmpeg-v2"><meta property="og:title" content="${esc(title)}"><meta property="og:description" content="${esc(desc)}"><meta property="og:url" content="${canonical(route)}"><meta property="og:image" content="${canonical(socialImage)}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta property="og:image:alt" content="FFmpeg-v2: 22.61% HD and 28.48% live-action less elapsed time vs prior Stock preset on M4 Max, by Jillur Rahman"><meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="${esc(title)}"><meta name="twitter:description" content="${esc(desc)}"><meta name="twitter:image" content="${canonical(socialImage)}"><link rel="icon" href="${url('assets/mark.svg')}" type="image/svg+xml"><link rel="alternate" type="application/atom+xml" title="FFmpeg-v2 releases" href="${url('feed.xml')}"><link rel="stylesheet" href="${url('assets/site.css')}"><script type="application/ld+json">${JSON.stringify(metadata).replaceAll('<','\\u003c')}</script><script defer src="${url('assets/site.js')}"></script></head><body>${header(route)}<main id="main">${content}</main>${footer()}</body></html>`;
  const destination=route==='404.html'?path.join(out,route):path.join(out,route,'index.html');
  fs.mkdirSync(path.dirname(destination),{recursive:true});fs.writeFileSync(destination,html);
  if(!noindex)pages.push({route,title,description:desc,url:canonical(route),source:file||null});
}
function rewriteHref(href,file){
  if(/^(https?:|mailto:|#)/i.test(href))return href;
  if(/^[a-z]+:/i.test(href))return '#';
  const [relative,fragment]=href.split('#');
  const resolved=path.posix.normalize(path.posix.join(path.posix.dirname(file),relative));
  if(routes.has(resolved))return url(routes.get(resolved))+(fragment?'#'+fragment:'');
  if(resolved==='site/assets/mark.svg')return url('assets/mark.svg');
  const absolute=path.join(root,resolved);
  if(resolved.startsWith('docs/')&&resolved.endsWith('.json')&&fs.existsSync(absolute))return url('files/'+resolved);
  const isDir=fs.existsSync(absolute)&&fs.statSync(absolute).isDirectory();
  return `${repo}/${isDir?'tree':'blob'}/main/${resolved}`+(fragment?'#'+fragment:'');
}
function markdown(file){
  let html=marked.parse(sourceText(file),{gfm:true});
  html=html.replace(/href="([^"]*)"/g,(_,href)=>`href="${esc(rewriteHref(href.replaceAll('&amp;','&'),file))}"`);
  const slugs=new Map();
  html=html.replace(/<h([1-6])>(.*?)<\/h\1>/gs,(_,level,body)=>{
    const slug=body.replace(/<[^>]*>/g,'').toLowerCase().replace(/&[^;]+;/g,'').replace(/[^\p{L}\p{N}\p{M}\s_-]/gu,'').replace(/\s/g,'-');
    const n=slugs.get(slug)||0;slugs.set(slug,n+1);return `<h${level} id="${esc(slug+(n?'-'+n:''))}">${body}</h${level}>`;
  });
  html=html.replace(/<table>/g,'<div class="table-wrap" tabindex="0" role="region" aria-label="Scrollable data table"><table>').replace(/<\/table>/g,'</table></div>');
  return html;
}

fs.mkdirSync(out,{recursive:true});fs.cpSync(path.join(root,'site/assets'),path.join(out,'assets'),{recursive:true});
for(const file of walk('docs').filter(f=>f.endsWith('.json'))){const dest=path.join(out,'files',file);fs.mkdirSync(path.dirname(dest),{recursive:true});fs.copyFileSync(path.join(root,file),dest);}
const released=JSON.parse(sourceText('docs/benchmarks/released-workflow-summary.json'));
const experiment=JSON.parse(sourceText('docs/benchmarks/phase11-summary.json'));
write('','FFmpeg-v2 — faster FFmpeg workflows, CLI and MCP for macOS',renderHome({url,repo,released}),{layout:'home'});
write('benchmarks/','FFmpeg-v2 vs Stock FFmpeg: measured workflow improvements',renderResults({url,released,experiment,experimentalReport:url(routes.get('docs/PHASE11-RESULTS.md'))}));

const historical=docs.filter(f=>!publicGuides.has(f));
const reportItems=historical.sort((a,b)=>a.localeCompare(b)).map(f=>`<li class="report-item"><a href="${url(routes.get(f))}">${esc(titleFor(f))}</a><span>${esc(f)} · historical lab document · ${f==='README.bn.md'?'Bengali overview':'original evidence and scope'}</span></li>`).join('');
write('reports/','FFmpeg-v2 technical evidence archive',`<h1>Technical evidence archive</h1><p>Inspect the methods, quality checks, diagnostics and retained experiments behind the product. Start with the <a href="${url('benchmarks/released-workflow/')}">English released-profile results</a> or <a href="${url('benchmarks/')}">the public comparison</a>; original technical documents are mostly Bengali.</p><div class="note">Historical lab measurements describe their original code, machine and engine. They are not a rerun of public 0.6.1. Public evidence indexes are redacted summaries, not local release activation manifests. Raw media and private profiles are not bundled.</div><p><a href="${url('reports/guide/')}">Technical reading guide and machine-readable evidence →</a></p><div class="report-search"><label for="report-search">Find a method, workload or result</label><input id="report-search" type="search" placeholder="Try: quality, cache, thread pools, Metal" autocomplete="off"><p class="fine" id="report-count" role="status">${historical.length} reports shown</p></div><ul class="report-list">${reportItems}</ul>`);
for(const [file,route] of routes){
  if(file==='README.md')continue;
  const historical=!publicGuides.has(file);
  const notice=historical?`<div class="note"><strong>Historical lab document.</strong> Original machine, code and acceptance scope apply. Private paths are redacted; this is not a fresh public 0.6.1 benchmark. Read <a href="${url('benchmarks/')}">the latest outcome</a> and <a href="${url('configuration/')}">public configuration</a>.</div>`:'';
  write(route,titleFor(file),notice+markdown(file),{file,lang:historical?'bn':'en'});
}
write('404.html','Page not found',`<h1>This path is not in the current documentation.</h1><p>Start with <a href="${base}">the overview</a>, <a href="${url('getting-started/')}">setup</a> or <a href="${url('reports/')}">the report archive</a>.</p>`,{noindex:true});
fs.writeFileSync(path.join(out,'sitemap.xml'),`<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${pages.map(p=>`<url><loc>${esc(p.url)}</loc><lastmod>${date}</lastmod></url>`).join('')}</urlset>`);
fs.writeFileSync(path.join(out,'robots.txt'),`User-agent: *\nAllow: /\nSitemap: ${canonical('sitemap.xml')}\n`);
fs.writeFileSync(path.join(out,'feed.xml'),`<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>FFmpeg-v2 source releases</title><id>${canonical('')}</id><link href="${canonical('feed.xml')}" rel="self"/><link href="${repo}/releases"/><updated>${date}T00:00:00Z</updated><author><name>Jillur Rahman</name></author><entry><title>0.6.1 — first public source release</title><id>${repo}/releases/tag/v0.6.1</id><link href="${repo}/releases/tag/v0.6.1"/><updated>${date}T00:00:00Z</updated><summary>Portable macOS workflow configuration, CLI/MCP guides and the complete historical report archive. No PGO promotion or bundled native engine.</summary></entry></feed>`);
fs.writeFileSync(path.join(out,'.nojekyll'),'');
fs.writeFileSync(path.join(out,'pages.json'),JSON.stringify(pages,null,2)+'\n');
console.log(JSON.stringify({pages:pages.length,output:'site-build',base,bytes:walk('site-build').reduce((n,f)=>n+fs.statSync(path.join(root,f)).size,0)}));
