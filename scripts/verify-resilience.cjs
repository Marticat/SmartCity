/**
 * Race/error tests. Only this isolated browser receives explicitly labelled
 * response fixtures; the running app, dataset and demo recording stay real.
 */
const { chromium } = require('../frontend/node_modules/@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const BASE = process.env.QADAM_URL || 'http://127.0.0.1:8000';
const OUTPUT = path.resolve(process.env.QADAM_ARTIFACTS || 'artifacts');

(async () => {
  fs.mkdirSync(OUTPUT, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  await context.route('https://tile.openstreetmap.org/**', route => route.abort());
  const page = await context.newPage();
  const checks = [];
  try {
    await page.goto(BASE);
    const { locations } = await (await context.request.get(`${BASE}/api/locations/search`)).json();
    await page.getByTestId('location-search').fill(locations[0].name);
    await page.getByTestId('location-option').first().click();
    await page.getByTestId('query-input').fill('Хочу парк');
    await page.getByTestId('submit-recommend').click();
    await page.getByTestId('recommendation-card').first().waitFor();

    let ordinal = 0, oldDone;
    const oldFinished = new Promise(resolve => { oldDone = resolve; });
    await page.route('**/api/recommend', async route => {
      const sequence = ++ordinal;
      const upstream = await route.fetch();
      const body = await upstream.json();
      body.summary = sequence === 1 ? 'ТЕСТ: устаревший ответ' : 'ТЕСТ: актуальный ответ';
      if (sequence === 1) await new Promise(resolve => setTimeout(resolve, 1600));
      try { await route.fulfill({ response: upstream, json: body }); }
      catch { /* Browser correctly cancelled the older response. */ }
      finally { if (sequence === 1) oldDone(); }
    });
    const olderRequest = page.waitForRequest(r => r.url().endsWith('/api/recommend'));
    await page.getByTestId('time-30').click();
    await olderRequest;
    await page.getByTestId('time-90').click();
    await page.getByText('ТЕСТ: актуальный ответ', { exact: true }).waitFor();
    await oldFinished;
    assert.equal(await page.getByText('ТЕСТ: устаревший ответ', { exact: true }).count(), 0);
    assert(await page.getByText('ТЕСТ: актуальный ответ', { exact: true }).isVisible());
    checks.push({ name: 'Out-of-order responses', passed: true, detail: 'Delayed older response cannot replace newer selection; isolated labelled response fixtures' });
    await page.unroute('**/api/recommend');

    await page.route('**/api/recommend', route => route.abort('failed'));
    await page.getByTestId('time-60').click();
    await page.getByText('Не получилось загрузить', { exact: true }).waitFor();
    assert.equal(await page.getByTestId('recommendation-card').count(), 0);
    await page.unroute('**/api/recommend');
    await page.getByRole('button', { name: 'Повторить', exact: true }).click();
    await page.getByTestId('recommendation-card').first().waitFor();
    checks.push({ name: 'Network failure and retry', passed: true, detail: 'Error is visible, old cards removed, retry restores real results' });

    await page.getByRole('button', { name: 'Выбрать точку', exact: true }).click();
    const next = page.waitForRequest(r => r.url().endsWith('/api/recommend'));
    const bounds = await page.locator('.city-map').boundingBox();
    await page.locator('.city-map').click({ position: { x: bounds.width * 0.7, y: bounds.height * 0.3 } });
    const origin = (await next).postDataJSON().origin;
    assert.equal(origin.label, 'Точка на карте');
    assert(origin.latitude !== locations[0].latitude || origin.longitude !== locations[0].longitude);
    checks.push({ name: 'Manual map origin', passed: true, detail: 'Map selection submits actual new coordinates in POST body' });
    fs.writeFileSync(path.join(OUTPUT, 'resilience-verification.json'), JSON.stringify({ tested_at: new Date().toISOString(), checks }, null, 2));
    console.log(JSON.stringify({ passed: checks.length, checks }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
