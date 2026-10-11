import { test, expect } from '@playwright/test';

test('每个游戏只有一个 0 分基准，未关联选手待定，败于基准后为负分', async ({page,request},testInfo) => {
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await expect.poll(async()=> (await (await request.get('/api/v1/status')).json()).busy,{timeout:40000}).toBe(false);
  for(const game of ['bomberman','gomoku']) {
    const bots=await (await request.get(`/api/v1/bots?game_id=${game}`)).json();
    expect(bots.items.filter((b:any)=>b.baseline)).toHaveLength(1);
    const reference=bots.items.find((b:any)=>b.baseline);
    expect(reference.status).toBe('ready');
    const board=await (await request.get(`/api/v1/leaderboard?game_id=${game}`)).json();
    expect(board.items.find((r:any)=>r.id===reference.id).rating).toBe(0);
    await page.goto('/');await page.getByLabel('游戏',{exact:true}).selectOption(game);
    await expect(page.locator('.bot-list')).toContainText('基准 BOT · 0 分');
  }
  const source=Buffer.from('#include "gomoku.hpp"\nnamespace bot {void init(uint64_t){} Action tick(const GameState&){return Action::resign();}}');
  const response=await request.post('/api/v1/bots',{headers:{'X-Arena-Local':'1'},multipart:{name:'Rating probe',game_id:'gomoku',file:{name:'bot.cpp',mimeType:'text/plain',buffer:source}}});
  const bot=await response.json();
  await expect.poll(async()=> (await (await request.get('/api/v1/bots?game_id=gomoku')).json()).items.find((b:any)=>b.id===bot.id)?.status,{timeout:40000}).toBe('ready');
  const play=async(ids:string[])=> {
    const result=await request.post('/api/v1/matches',{headers:{'X-Arena-Local':'1'},data:{bot_ids:ids,game_id:'gomoku'}});
    expect(result.status()).toBe(202);const run=await result.json();
    await expect.poll(async()=> (await (await request.get(`/api/v1/matches/${run.id}`)).json()).pair.counted,{timeout:40000}).toBe(true);
    return run;
  };
  await play([bot.id,bot.id]);
  await page.goto('/leaderboard');await page.getByLabel('榜单游戏').selectOption('gomoku');
  await expect(page.getByRole('row').filter({hasText:'Rating probe'})).toContainText('待定');
  const bots=await (await request.get('/api/v1/bots?game_id=gomoku')).json();
  const reference=bots.items.find((b:any)=>b.baseline);
  const run=await play([bot.id,reference.id]);
  await page.reload();
  const row=page.getByRole('row').filter({hasText:'Rating probe'});
  await expect(row.locator('.ranking-score')).toHaveText(/^-\d+\.\d{2}$/);
  await expect(page.getByRole('row').filter({hasText:'基准 BOT'}).locator('.ranking-score')).toHaveText('0.00');
  const board=await (await request.get('/api/v1/leaderboard?game_id=gomoku')).json();
  expect(board.items.find((r:any)=>r.id===bot.id).rating).toBeLessThan(0);
  await page.screenshot({path:testInfo.outputPath('reference-leaderboard.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:testInfo.outputPath('reference-leaderboard-mobile.png'),fullPage:true});
  const trashed=await request.post('/api/v1/matches/manage',{headers:{'X-Arena-Local':'1'},data:{action:'trash',ids:run.pair_runs}});
  expect(trashed.status()).toBe(200);
  const reverted=await (await request.get('/api/v1/leaderboard?game_id=gomoku')).json();
  expect(reverted.items.find((r:any)=>r.id===bot.id).rating).toBeNull();
  expect(errors).toEqual([]);
});
