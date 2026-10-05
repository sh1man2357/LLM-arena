/** Compare every rendered report field and every map/swap selection to frozen evidence. */
import {readFileSync,mkdirSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {chromium,expect} from '@playwright/test';
import {contrastReport} from './check-contrast.mjs';

const [base='http://127.0.0.1:8800',outputArg='../artifacts/acceptance/v0.2-development']=process.argv.slice(2);
const output=resolve(outputArg), visual=resolve(output,'visual/report-quality');mkdirSync(visual,{recursive:true});
const proof=JSON.parse(readFileSync(resolve(output,'checks/report-traces.json'),'utf8'));
const browser=await chromium.launch({channel:'chrome'}), context=await browser.newContext({baseURL:base,viewport:{width:1280,height:1000}});
const page=await context.newPage(),errors=[],checks=[],screenshots=[],contrasts=[];
page.on('pageerror',e=>errors.push(e.message));
try {
  for(const batch of proof.batches) {
    const response=await context.request.get(`/api/v1/tournaments/${batch.id}`);expect(response.ok()).toBe(true);
    const stored=await response.json();expect(stored.report).toEqual(batch.report);
    const api=await context.request.get(`/api/v1/tournaments/${batch.id}/analysis`);expect(api.ok()).toBe(true);
    const actual=await api.json();for(const [key,value] of Object.entries(batch.expected_analysis))expect(actual[key],key).toEqual(value);
    const samples=batch.traces.filter(t=>t.draw&&t.quiet_tail_ticks>0).sort((a,b)=>b.quiet_tail_ticks-a.quiet_tail_ticks||a.match_id.localeCompare(b.match_id)).slice(0,3);
    expect(actual.quiet_draw_examples.map(m=>({id:m.id,tail:m.quiet_tail_ticks}))).toEqual(samples.map(m=>({id:`${batch.id}-${m.match_id}`,tail:m.quiet_tail_ticks})));
    await page.goto(`/tournaments/${batch.id}`);await expect(page.locator('.ranking-row')).toHaveCount(batch.report.entrants.length);
    for(const r of batch.report.entrants) {
      const row=page.locator(`.ranking-row[data-entrant-id="${r.id}"]`), details=batch.report.pairs.filter(p=>p.entrant===r.id);
      const rank=1+batch.report.entrants.filter(e=>e.mean_placement>r.mean_placement).length;
      await expect(row.locator('.rank')).toHaveText(String(rank).padStart(2,'0'));
      await expect(row.locator('.ranking-score')).toHaveText(r.mean_placement.toFixed(3));
      await expect(row.locator('.ranking-name small')).toHaveText(`${r.opponent_count} 个对手`);
      await expect(row.locator('.ranking-wld')).toHaveText(`${details.reduce((s,p)=>s+p.wins,0)} / ${details.reduce((s,p)=>s+p.losses,0)} / ${details.reduce((s,p)=>s+p.draws,0)}`);
    }
    const all=[];
    for(let offset=0;offset<batch.report.valid_matches;offset+=100)all.push(...(await(await context.request.get(`/api/v1/matches?tournament_id=${batch.id}&limit=100&offset=${offset}`)).json()).items);
    expect(all).toHaveLength(batch.report.valid_matches);
    let caseSelections=0;
    for(const pair of batch.report.pairs) {
      const entrants=batch.report.entrants.map(e=>e.id).sort((a,b)=>batch.report.entrants.find(e=>e.id===b).mean_placement-batch.report.entrants.find(e=>e.id===a).mean_placement);
      const row=page.locator('.matrix tbody tr').nth(entrants.indexOf(pair.entrant));
      const cell=row.locator('td').nth(entrants.indexOf(pair.opponent)).locator('button');
      await expect(cell.locator('strong')).toHaveText(pair.mean_placement.toFixed(2));
      await expect(cell.locator('small')).toHaveText(`${pair.wins} / ${pair.losses} / ${pair.draws}`);
      await cell.click();
      const metrics=page.locator('.pair-metrics strong');
      await expect(metrics.nth(0)).toHaveText(pair.mean_placement.toFixed(3));
      await expect(metrics.nth(1)).toHaveText(pair.ci95?`${pair.ci95[0].toFixed(3)} — ${pair.ci95[1].toFixed(3)}`:'样本不足');
      await expect(metrics.nth(2)).toHaveText(pair.spawn_mean.map(v=>v.toFixed(3)).join(' / '));
      await expect(metrics.nth(3)).toHaveText(pair.mean_ticks.toFixed(1));
      const stats=page.locator('.pair-analysis .statistics-details');await stats.locator('summary').click();
      for(const [key,value] of Object.entries(pair.stats))await expect(stats.locator(`[data-stat="${key}"] b`)).toHaveText(String(value));
      for(const [key,value] of Object.entries(pair.rates))await expect(stats.locator(`[data-rate="${key}"] b`)).toHaveText(`${(value*100).toFixed(2)}%`);
      for(let index=0;index<pair.case_means.length;index++) {
        const dot=page.locator('.case-dot').nth(index), value=pair.case_means[index];
        await expect(dot).toHaveAttribute('aria-label',`地图案例 ${index+1}，均分 ${value}`);
        expect(await dot.locator('i').evaluate(e=>parseFloat(getComputedStyle(e).bottom))).toBeCloseTo(18+43*value,4);
        await dot.click();
        const expected=all.filter(m=>m.case_index===index&&m.entrants.some(e=>e.id===pair.entrant)&&m.entrants.some(e=>e.id===pair.opponent)).map(m=>`/matches/${m.id}`).sort();
        expect(expected).toHaveLength(2);
        await expect.poll(async()=> (await page.locator('.matches-section .match-row').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('href')).sort()))).toEqual(expected);
        caseSelections++;
      }
      await stats.locator('summary').click();
    }
    const draw=page.locator('.draw-analysis');await expect(draw.locator('h3').first()).toHaveText(`平局原因 · ${actual.draws} 局`);
    for(const [key,value] of Object.entries(actual.reasons))await expect(draw.locator(`[data-reason="${key}"] b`)).toHaveText(String(value));
    for(const [key,value] of Object.entries(actual.draw_reasons))await expect(draw.locator(`[data-draw-reason="${key}"] b`)).toHaveText(String(value));
    for(const [key,value] of Object.entries(actual.draw_patterns))await expect(draw.locator(`[data-pattern="${key}"] b`)).toHaveText(String(value));
    await draw.locator('summary').click();
    for(const [key,value] of Object.entries(actual.actions))await expect(draw.locator(`[data-action="${key}"] b`)).toHaveText(String(value));
    for(const key of ['moves','blocked_moves','bombs_placed','quiet_ticks','longest_quiet_run'])await expect(draw.locator(`[data-fact="${key}"] b`)).toHaveText(String(actual[key]));
    if(actual.quiet_draw_examples.length) {
      const sample=actual.quiet_draw_examples[0], target=`/matches/${sample.id}?frame=${Math.max(0,sample.ticks-sample.quiet_tail_ticks)}`;
      await expect(draw.locator('.analysis-examples a').first()).toHaveAttribute('href',target);
      await draw.locator('.analysis-examples a').first().click();
      await expect(page.getByRole('slider',{name:'回放帧'})).toHaveValue(String(Math.max(0,sample.ticks-sample.quiet_tail_ticks)));
      await page.goBack();await expect(page.locator('.ranking-row')).toHaveCount(batch.report.entrants.length);
    }
    checks.push({id:batch.id,entrants:batch.report.entrants.length,pairs:batch.report.pairs.length,case_selections:caseSelections,analysis_matches:actual.matches,tied_ranks:batch.report.entrants.length-new Set(batch.report.entrants.map(e=>e.mean_placement)).size});
  }
  for(const width of [390,768,1280,1440]) {
    await page.setViewportSize({width,height:1000});
    for(const batch of proof.batches) {
      await page.goto(`/tournaments/${batch.id}`);await expect(page.locator('.ranking-row')).toHaveCount(batch.report.entrants.length);
      await expect(page.locator('.draw-analysis')).toBeVisible();
      await page.locator('.pair-analysis summary').click();await page.locator('.draw-analysis summary').click();
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      const contrast=await contrastReport(page);expect(contrast.failures).toEqual([]);contrasts.push({batch:batch.id,width,...contrast});
      await page.evaluate(()=>document.fonts.ready);
      const name=`${batch.id}-${width}.png`;await page.screenshot({path:resolve(visual,name),fullPage:true});screenshots.push(name);
      const preview=`${batch.id}-${width}-viewport.png`;await page.locator('.draw-analysis').scrollIntoViewIfNeeded();await page.screenshot({path:resolve(visual,preview)});screenshots.push(preview);
    }
  }
  expect(errors).toEqual([]);
  writeFileSync(resolve(output,'checks/browser-report-quality.json'),JSON.stringify({status:'passed',browser:await browser.version(),checks,contrasts,screenshots,page_errors:errors},null,2)+'\n');
  console.log(`Verified ${checks.reduce((n,c)=>n+c.pairs,0)} directed pairs and ${checks.reduce((n,c)=>n+c.case_selections,0)} actual map/swap selections.`);
} finally {await context.close();await browser.close();}
