/** Actual viewport views complement long full-page evidence; no fixture responses. */
import {chromium, expect} from '@playwright/test';
import {resolve} from 'node:path';
import {mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

const [base='http://127.0.0.1:8841', out='../artifacts/work/checks'] = process.argv.slice(2);
const output=resolve(out), visual=resolve(output,'visual/read-states-final');
mkdirSync(visual,{recursive:true});mkdirSync(resolve(output,'checks'),{recursive:true});
const browser=await chromium.launch({channel:'chrome'});
const context=await browser.newContext({baseURL:base,viewport:{width:1280,height:1000}});
const page=await context.newPage(), screenshots=[], errors=[];
page.on('pageerror',error=>errors.push(error.message));
try {
  for(const width of [390,1280])for(const [name,path,selector] of [
    ['hall','/','.feature-board canvas'],['viewer','/matches/reference-chain?frame=13','canvas'],
    ['batch','/tournaments/reference','.draw-analysis'],['entrants','/entrants','.entrant-card'],
    ['manage','/manage','.submission-row']]) {
    await page.setViewportSize({width,height:1000});await page.goto(path);
    await expect(page.locator(selector).first()).toBeVisible();
    if(name==='manage')await expect(page.getByRole('heading',{name:'正在读取工作台记录'})).toHaveCount(0);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    const file=`${name}-normal-viewport-${width}.png`;await page.screenshot({path:resolve(visual,file)});
    screenshots.push({file,width,height:1000,path,sha256:createHash('sha256').update(readFileSync(resolve(visual,file))).digest('hex')});
  }
  expect(errors).toEqual([]);
  writeFileSync(resolve(output,'checks/read-states-visual-review.json'),JSON.stringify({status:'captured',method:'real production pages and verified data; wait for actual preview/analysis/workbench reads',screenshots,page_errors:errors},null,2)+'\n');
  console.log(`Captured ${screenshots.length} actual viewport views.`);
} finally {await context.close();await browser.close();}
