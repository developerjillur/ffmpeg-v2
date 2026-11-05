import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

async function expectViewportFit(page){
  const limit=page.viewportSize().width;
  const layout=await page.evaluate(width=>({width:document.documentElement.scrollWidth,
    overflow:[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>width&&!e.closest('.table-wrap, pre, .sidebar'))
      .slice(0,12).map(e=>({tag:e.tagName,class:e.className,right:e.getBoundingClientRect().right,text:e.textContent.slice(0,120)}))}),limit);
  expect(layout.width,JSON.stringify(layout)).toBeLessThanOrEqual(limit);
}

test('overview has accessible navigation, contract and social metadata',async({page},info)=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('./');
  await expect(page.getByRole('heading',{level:1})).toContainText('Up to 28.48%');
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href','https://developerjillur.github.io/ffmpeg-v2/');
  await expect(page.locator('[data-released-results]')).toContainText('22.61%');
  await expect(page.locator('[data-released-results]')).toContainText('28.48%');
  await expect(page.locator('[data-baseline="prior-stock-preset"]')).toContainText('prior Stock workflow preset');
  await expect(page.locator('main')).not.toContainText(/Phase\s+\d/);
  await expectViewportFit(page);
  const result=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
  expect(result.violations).toEqual([]);expect(errors).toEqual([]);
  await page.screenshot({path:info.outputPath('overview.png'),fullPage:true});
});
test('benchmark filters keep failed sample gates explicit',async({page},info)=>{
  await page.goto('benchmarks/');
  await expect(page.locator('[data-released-results]')).toContainText('28.48%');
  await expect(page.locator('#same-tuning')).toBeVisible();
  await page.getByText('Experimental optimization results',{exact:true}).click();
  await expect(page.getByText('PGO candidate not promoted',{exact:true})).toBeVisible();
  await expect(page.locator('[data-result="direct"]')).toBeVisible();
  await page.getByRole('button',{name:'Complete workflow',exact:true}).click();
  await expect(page.locator('[data-result="direct"]')).toBeHidden();
  await expect(page.locator('[data-result="workflow"]')).toBeVisible();
  await page.getByRole('button',{name:'Direct encoder',exact:true}).click();
  await expect(page.locator('[data-result="workflow"]')).toBeHidden();
  await expect(page.locator('[data-result="direct"]')).toContainText('Insufficient');
  await page.getByRole('button',{name:'Show all',exact:true}).click();
  await expect(page.locator('[data-released-results]')).toBeVisible();
  const result=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
  expect(result.violations).toEqual([]);
  await expectViewportFit(page);
  await page.screenshot({path:info.outputPath('benchmarks.png'),fullPage:true});
});
test('report search preserves usable links',async({page})=>{
  await page.goto('reports/');
  await page.getByLabel('Find a method, workload or result').fill('Phase 11');
  const shown=page.locator('.report-item:visible');expect(await shown.count()).toBeGreaterThan(0);
  await shown.first().getByRole('link').click();
  await expect(page.getByText('Historical lab document.',{exact:true})).toBeVisible();
});
test('setup copy feedback, keyboard focus and accessibility',async({page},info)=>{
  await page.goto('getting-started/');
  await expect(page.getByRole('button',{name:'Copy code'}).first()).toBeVisible();
  await page.getByRole('button',{name:'Copy code'}).first().click();
  await expect(page.locator('#announce')).toContainText(/Code copied|Clipboard unavailable/);
  await page.goto('./');await page.keyboard.press('Tab');
  await expect(page.getByRole('link',{name:'Skip to content'})).toBeFocused();
  await page.goto('getting-started/');
  const result=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
  expect(result.violations).toEqual([]);
  await page.screenshot({path:info.outputPath('getting-started.png'),fullPage:true});
});
test('MCP guide exposes eight tools and local boundaries',async({page})=>{
  await page.goto('mcp/');
  await expect(page.getByRole('heading',{level:1})).toHaveText('FFmpeg MCP server');
  await expect(page.locator('article')).toContainText('ffv2_worker_start');
  await expect(page.locator('article')).toContainText('does not edit your');
  const result=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
  expect(result.violations).toEqual([]);
});
test('SEO sitemap and machine-readable comparisons are served',async({request})=>{
  const sitemap=await request.get('sitemap.xml');expect(sitemap.status()).toBe(200);
  expect(await sitemap.text()).toContain('/ffmpeg-v2/benchmarks/');
  const data=await request.get('files/docs/benchmarks/phase11-summary.json');
  expect(data.status()).toBe(200);expect((await data.json()).overall_promotion_accepted).toBe(false);
  const released=await request.get('files/docs/benchmarks/released-workflow-summary.json');
  expect(released.status()).toBe(200);
  expect((await released.json()).rows.map(r=>r.elapsed_reduction_percent_vs_prior_stock.toFixed(2))).toEqual(['22.61','28.48']);
});
test('product comparison explains additions and credits Stock controls',async({page},info)=>{
  await page.goto('why-ffmpeg-v2/');
  await expect(page.getByRole('heading',{level:1})).toHaveText('Why use FFmpeg-v2?');
  await expect(page.locator('article')).toContainText('28.48%');
  await expect(page.locator('article')).toContainText('Codec and filter thread controls');
  await expect(page.locator('article')).toContainText('Durable SQLite queue');
  await expectViewportFit(page);
  const result=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();
  expect(result.violations).toEqual([]);
  await page.screenshot({path:info.outputPath('product-comparison.png'),fullPage:true});
});
test('without JavaScript all comparisons remain available',async({browser,baseURL})=>{
  const context=await browser.newContext({javaScriptEnabled:false});const page=await context.newPage();
  await page.goto(new URL('benchmarks/',baseURL).href);
  await expect(page.locator('[data-released-results]')).toBeVisible();
  await page.getByText('Experimental optimization results',{exact:true}).click();
  await expect(page.locator('[data-result="workflow"]')).toBeVisible();
  await expect(page.locator('[data-result="direct"]')).toBeVisible();
  await context.close();
});
