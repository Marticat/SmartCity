/**
 * Integration check against the actual running app and dataset.
 * Public map tiles are blocked during automated scenario loops.
 * Run: node scripts/verify-browser.cjs
 */
const { chromium } = require('../frontend/node_modules/@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const BASE = process.env.QADAM_URL || 'http://127.0.0.1:8000';
const OUTPUT = process.env.QADAM_ARTIFACTS ? path.resolve(process.env.QADAM_ARTIFACTS) : path.resolve(__dirname, '../artifacts');
const checks = [];
const record = (name, detail) => checks.push({ name, passed: true, detail });

(async () => {
  fs.mkdirSync(OUTPUT, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    reducedMotion: 'reduce',
  });
  await context.route(/https?:\/\/[^/]*(tile\.openstreetmap\.org|basemaps\.cartocdn\.com)\//, route => route.abort());
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const requests = [];
  page.on('request', request => {
    if (request.url().includes('/api/recommend') && request.method() === 'POST') {
      requests.push(request.postDataJSON());
    }
  });
  try {
    await page.goto(BASE, { waitUntil: 'networkidle' });
    await page.getByTestId('query-input').waitFor();
    record('Initial render', 'No geolocation permission required');
    assert(await page.evaluate(() => localStorage.length === 0), 'No location persisted in localStorage');
    await page.screenshot({ path: path.join(OUTPUT, 'desktop-initial.png'), fullPage: true });

    const locationsResponse = await context.request.get(`${BASE}/api/locations/search?q=&limit=8`);
    assert(locationsResponse.ok(), 'Real location search endpoint');
    const { locations } = await locationsResponse.json();
    assert(locations.length > 0, 'Dataset has selectable locations');
    const input = page.getByTestId('location-search');
    await input.fill(locations[0].name);
    const option = page.getByTestId('location-option').first();
    await option.waitFor();
    await option.click();
    await page.getByTestId('query-input').fill('Хочу немного прогуляться рядом');
    const responsePromise = page.waitForResponse(
      r => r.url().includes('/api/recommend') && r.request().method() === 'POST',
      { timeout: 90000 },
    );
    await page.getByTestId('submit-recommend').click();
    const response = await responsePromise;
    assert(response.ok(), 'Recommendation endpoint succeeds');
    const payload = await response.json();
    assert(payload.recommendations.length >= 1 && payload.recommendations.length <= 3);
    await page.getByTestId('recommendation-card').first().waitFor();
    record('Live selection to recommendations', {
      mode: payload.mode,
      count: payload.recommendations.length,
      semantic_ready: payload.dataset.semantic_ready,
    });
    for (const recommendation of payload.recommendations) {
      assert(recommendation.poi.source_url.startsWith('https://www.openstreetmap.org/'));
      assert(recommendation.distance_method !== 'straight_line' || recommendation.walking_minutes === null);
    }

    const secondCard = page.getByTestId('recommendation-card').nth(Math.min(1, payload.recommendations.length - 1));
    await secondCard.getByRole('button', { name: /^Выбрать на карте:/ }).click();
    assert.equal(await secondCard.getAttribute('data-selected'), 'true');
    const activeMarker = page.locator('.numbered-marker.active');
    await activeMarker.waitFor();
    assert.equal(await activeMarker.textContent(), String(Math.min(2, payload.recommendations.length)));
    record('Card/map synchronization', 'Selecting a card selects its numbered map marker');
    await page.locator('.results').evaluate(element => element.scrollIntoView({ block: 'start' }));
    await page.screenshot({ path: path.join(OUTPUT, 'desktop.png'), fullPage: true });

    const previousCount = requests.length;
    const recalc = page.waitForResponse(
      r => r.url().includes('/api/recommend') && r.request().method() === 'POST',
      { timeout: 90000 },
    );
    await page.getByTestId('time-30').click();
    await recalc;
    assert(requests.length > previousCount);
    assert.equal(requests.at(-1).time_budget_minutes, 30);
    record('Time recalculation', '30-minute selection submits a new request');

    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByTestId('mobile-list').click();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
    await page.screenshot({ path: path.join(OUTPUT, 'mobile.png'), fullPage: true });
    await page.getByTestId('mobile-map').click();
    await page.getByTestId('map-panel').waitFor({ state: 'visible' });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
    record('Mobile 390px', 'List/map switching; no horizontal overflow');

    await page.getByTestId('mobile-list').click();
    await page.getByRole('button', { name: 'Изменить пожелания' }).click();
    await page.getByTestId('location-search').waitFor({ state: 'visible' });
    await page.getByTestId('location-search').scrollIntoViewIfNeeded();
    const strictResponse = page.waitForResponse(r => r.url().includes('/api/recommend') && r.request().method() === 'POST');
    await page.locator('details.filters summary').click();
    await page.getByLabel('Нужна розетка', { exact: true }).check();
    const strict = await (await strictResponse).json();
    assert.equal(strict.recommendations.length, 0, 'Current real dataset has no confirmed sockets');
    await page.getByText('Пока без совпадений.', { exact: true }).waitFor();
    record('Strict unknown amenity', 'No fabricated socket availability; empty result shown');

    await page.getByTestId('reset-session').click();
    await page.getByTestId('query-input').waitFor();
    assert.equal(await page.getByTestId('location-search').inputValue(), '');
    assert.equal(await page.getByTestId('query-input').inputValue(), '');
    assert.equal(await page.getByTestId('recommendation-card').count(), 0);
    assert(await page.evaluate(() => localStorage.length === 0));
    record('Session reset', 'Location, query and recommendations cleared; no localStorage');

    await page.getByRole('button', { name: 'Моя геопозиция', exact: true }).click();
    await page.getByText(/Не удалось получить геопозицию|Геолокация недоступна/).waitFor({ timeout: 15000 });
    await page.getByTestId('location-search').fill(locations[0].name);
    await page.getByTestId('location-option').first().click();
    assert.equal(await page.getByTestId('location-search').inputValue(), locations[0].name);
    record('Denied geolocation', 'Manual landmark selection remains usable');

    assert.equal(errors.length, 0, `Browser exceptions: ${errors.join('; ')}`);
    record('Runtime', 'No browser JavaScript exceptions');
    console.log(JSON.stringify({ passed: checks.length, checks }, null, 2));
  } catch (error) {
    await page.screenshot({ path: path.join(OUTPUT, 'failure.png'), fullPage: true }).catch(() => {});
    checks.push({ name: 'Failure', passed: false, detail: String(error) });
    throw error;
  } finally {
    fs.writeFileSync(
      path.join(OUTPUT, 'browser-verification.json'),
      JSON.stringify({ tested_at: new Date().toISOString(), base_url: BASE, tiles: 'blocked during automation', checks }, null, 2),
    );
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
