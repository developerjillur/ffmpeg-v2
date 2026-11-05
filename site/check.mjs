import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
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
const released=JSON.parse(fs.readFileSync('docs/benchmarks/released-workflow-summary.json'));
const releasedEvidence=fs.readFileSync(released.provenance.public_index);
assert.equal(createHash('sha256').update(releasedEvidence).digest('hex'),released.provenance.public_index_sha256,'Released results bind the retained source evidence');
for(const row of released.rows){
  assert.equal(row.trials_per_configuration,9);
  assert(row.quality_gates_passed);
  assert(Math.abs((1-row.v2_native_profile_seconds/row.stock_prior_preset_seconds)*100-row.elapsed_reduction_percent_vs_prior_stock)<1e-9,'Elapsed percentage must match its stated baseline');
  assert(row.paired_ratio_95_vs_prior_stock[1]<1,'Released comparison confidence gate');
  assert(!row.matched_encoder_speed_advantage_proven,'Same-tuning uncertainty retained');
}
const home=fs.readFileSync(path.join(root,'index.html'),'utf8');
const main=home.match(/<main id="main">([\s\S]*?)<\/main>/)[1];
assert(main.includes('22.61%')&&main.includes('28.48%'),'Product results first');
assert(main.includes('prior Stock workflow preset'),'Headline must name its baseline');
assert(!/Phase\s+\d/.test(main),'Internal phase chronology is not homepage positioning');
assert(fs.statSync(path.join(root,'assets/social.png')).size>1000,'Social preview PNG');
const sitemap=fs.readFileSync(path.join(root,'sitemap.xml'),'utf8');
for(const page of pages)assert(sitemap.includes(`<loc>${page.url}</loc>`),'Sitemap missing page');
assert(!JSON.stringify(pages).includes('/Users/'),'Private source path');
console.log(JSON.stringify({pages:pages.length,local_links:links,benchmark_contract:'passed',metadata:'passed'}));
