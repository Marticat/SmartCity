/** Real API/UI checks for reviewed sources, time selection and privacy.
 * Run after starting the production app: node scripts/verify-context.cjs
 * No mocked recommendations; public map tiles are blocked.
 */
const { chromium } = require('../frontend/node_modules/@playwright/test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const BASE = process.env.QADAM_URL || 'http://127.0.0.1:8000';
const OUTPUT = path.resolve(process.env.QADAM_ARTIFACTS || 'artifacts');

(async () => {
  fs.mkdirSync(OUTPUT, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 }, timezoneId: 'Pacific/Honolulu',
  });
  await context.route('https://tile.openstreetmap.org/**', route => route.abort());
  const page = await context.newPage();
  const checks = [];
  try {
    await page.goto(BASE);
    const locations = await (await context.request.get(`${BASE}/api/locations/search?q=EXPO`)).json();
    const expo = locations.locations.find(p => p.id === 'osm:way:454853233');
    assert(expo, 'EXPO anchor is a real saved OSM object');
    await page.getByTestId('location-search').fill(expo.name);
    await page.getByTestId('location-option').filter({ hasText: expo.name }).first().click();
    await page.getByTestId('time-120').click();
    await page.getByTestId('query-input').fill('Хочу ночную прогулку');
    const first = page.waitForResponse(r => r.url().endsWith('/api/recommend') && r.request().method() === 'POST');
    await page.getByTestId('submit-recommend').click();
    const clarification = await (await first).json();
    assert(clarification.clarifying_question && clarification.recommendations.length === 0);
    checks.push({ name: 'Night needs a planned time', passed: true });

    await page.locator('details.filters summary').click();
    await page.getByTestId('visit-scheduled').click();
    const planned = page.waitForResponse(r => r.url().endsWith('/api/recommend') && r.request().method() === 'POST');
    await page.getByTestId('visit-datetime').fill('2030-06-15T22:30');
    const plannedResponse = await planned;
    assert.equal(plannedResponse.request().postDataJSON().visit_datetime, '2030-06-15T22:30+05:00');
    const plannedBody = await plannedResponse.json();
    assert.equal(plannedBody.clarifying_question, null);
    assert.equal(plannedBody.weather.status, 'unavailable');
    assert(plannedBody.trace.applied_constraints.some(c => c.includes('22:30')));
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    checks.push({ name: 'Astana time independent of browser timezone', passed: true, detail: 'Honolulu browser sends22:30+05:00; future weather is not invented' });
    await page.getByTestId('reset-session').click();
    assert.equal(await page.getByTestId('location-search').inputValue(), '');
    assert(await page.evaluate(() => localStorage.length === 0));
    checks.push({ name: 'Scheduled visit reset', passed: true });

    // Verify the actual reviewed source appears in the real recommendation UI.
    await page.setViewportSize({ width: 1440, height: 1000 });
    const museum = await (await context.request.get(`${BASE}/api/pois/osm:node:4894937300`)).json();
    await page.getByTestId('location-search').fill(museum.name);
    await page.getByTestId('location-option').first().click();
    await page.getByTestId('query-input').fill('Хочу музей об истории Казахстана');
    const museumResponse = page.waitForResponse(r => r.url().endsWith('/api/recommend') && r.request().method() === 'POST');
    await page.getByTestId('submit-recommend').click();
    const museumBody = await (await museumResponse).json();
    const index = museumBody.recommendations.findIndex(r => r.poi.id === museum.id);
    assert(index >= 0, 'National museum retrieved near its real location');
    const card = page.getByTestId('recommendation-card').nth(index);
    await card.locator('details.source-details summary').click();
    const sourceLink = card.locator('a[href="https://nmrk.kz/ru/structure/exhibition-activities/"]').first();
    assert(await sourceLink.isVisible());
    assert(museumBody.recommendations[index].evidence_field_ids.includes('description'));
    assert(museumBody.recommendations[index].why_suitable.includes('закрыт'));
    await card.screenshot({ path: path.join(OUTPUT, 'official-source-card.png') });
    checks.push({ name: 'Official enrichment visible and cited', passed: true, detail: 'Real museum source and closed-hall caveat survive fallback' });

    fs.writeFileSync(path.join(OUTPUT, 'context-verification.json'), JSON.stringify({ tested_at: new Date().toISOString(), checks }, null, 2));
    console.log(JSON.stringify({ passed: checks.length, checks }, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
