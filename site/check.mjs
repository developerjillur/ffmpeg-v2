import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const root=path.resolve('site-build');
const pages=JSON.parse(fs.readFileSync(path.join(root,'pages.json')));
const base=new URL(pages[0].url).pathname;
const titles=new Set();let links=0;
for(const page of pages){
  const html=fs.readFileSync(path.join(root,page.route,'index.html'),'utf8');
  assert(html.includes('<main id="main">'),page.route+' main landmark');
  assert((html.match(/<h1\b/g)||[]).length===1,page.route+' exactly one h1');
  assert(!titles.has(page.title),'Duplicate page title: '+page.title);titles.add(page.title);
  assert(html.includes(`rel="canonical" href="${page.url}"`),page.route+' canonical');
  assert(html.includes('name="description"'),page.route+' description');
  assert(html.includes('application/ld+json'),page.route+' structured data');
  for(const [,href] of html.matchAll(/(?:href|src)="([^"]+)"/g)){
    if(!href.startsWith(base))continue;
    const relative=href.slice(base.length).split('#')[0].split('?')[0];
    const target=path.resolve(root,relative);
    assert(target===root||target.startsWith(root+path.sep),'Path escapes build');
    assert(fs.existsSync(target),`${page.route}: missing ${href}`);links++;
    if(href.includes('#')){
      const fragment=decodeURIComponent(href.split('#')[1]);
      const source=fs.readFileSync(path.join(target,'index.html'),'utf8');
      assert(source.includes(`id="${fragment}"`),`Missing anchor ${href} from ${page.route}`);
    }
  }
  for(const match of html.matchAll(/<script type="application\/ld\+json">(.*?)<\/script>/gs))JSON.parse(match[1]);
}
const dataset=JSON.parse(fs.readFileSync('docs/benchmarks/phase11-summary.json'));
assert.equal(dataset.overall_promotion_accepted,false);
assert.equal(dataset.comparisons.filter(r=>r.pipeline==='workflow'&&r.release_eligible_group).length,4);
assert(dataset.comparisons.filter(r=>r.pipeline==='direct').every(r=>!r.release_eligible_group));
assert(fs.statSync(path.join(root,'assets/social.png')).size>1000,'Social preview PNG');
const sitemap=fs.readFileSync(path.join(root,'sitemap.xml'),'utf8');
for(const page of pages)assert(sitemap.includes(`<loc>${page.url}</loc>`),'Sitemap missing page');
assert(!JSON.stringify(pages).includes('/Users/'),'Private source path');
console.log(JSON.stringify({pages:pages.length,local_links:links,benchmark_contract:'passed',metadata:'passed'}));
