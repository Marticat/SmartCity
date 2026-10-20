// Real UI recording, real backend. No API interception, fixtures or fake responses.
const { chromium } = require('../frontend/node_modules/playwright');
const fs = require('fs');
const path = require('path');

(async()=>{
  const browser=await chromium.launch({headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1000},recordVideo:{dir:path.join(__dirname,'raw'),size:{width:1440,height:1000}}});
  const page=await context.newPage();
  const started=Date.now();
  const base=process.env.QADAM_URL||'http://127.0.0.1:8000';
  const responses=[];
  const captions=[];
  let observedMode='not_requested';
  page.on('response',async response=>{
    if(response.url().endsWith('/api/recommend')&&response.status()===200){
      const body=await response.json();
      observedMode=body.mode;
      responses.push({mode:body.mode,poi_count:body.recommendations.length,semantic_ready:body.dataset.semantic_ready});
    }
  });
  const pause=ms=>page.waitForTimeout(ms);
  const caption=async(text)=>{
    captions.push({at_seconds:Number(((Date.now()-started)/1000).toFixed(2)),text});
    await page.evaluate(({text,mode})=>{
    let panel=document.getElementById('qadam-recording-caption');
    if(!panel){
      panel=document.createElement('div');panel.id='qadam-recording-caption';
      panel.style.cssText='position:fixed;top:10px;left:460px;right:24px;z-index:10000;background:#1d2523;color:#fff;padding:10px 18px;border-radius:8px;box-shadow:0 3px 18px #0002;pointer-events:none;font-family:Arial,sans-serif';
      document.body.appendChild(panel);
    }
    panel.replaceChildren();
    const label=document.createElement('div');label.style.cssText='font-size:11px;letter-spacing:1px;color:#c8d8d1;margin-bottom:4px';
    label.textContent='ЗАПИСЬ РЕАЛЬНОГО ДЕМО · '+(mode==='rag'?'RAG':mode==='not_requested'?'ЛОКАЛЬНЫЕ ДАННЫЕ':'ПОИСК БЕЗ ГЕНЕРАЦИИ');
    const line=document.createElement('div');line.style.cssText='font-size:18px;line-height:1.3';line.textContent=text;
    panel.append(label,line);
    },{text,mode:observedMode});
  };
  await page.goto(base,{waitUntil:'networkidle'});
  await caption('Есть час рядом с EXPO. Найдём конкретные варианты.');
  await pause(10000);
  const available=await (await context.request.get(base+'/api/locations/search?q=&limit=8')).json();
  const landmark=available.locations.find(p=>/әлем|alem|expo/i.test(p.name))||available.locations[0];
  await page.getByTestId('location-search').fill(landmark.name);
  await pause(5000);
  await page.getByTestId('location-option').first().click();
  await page.getByTestId('query-input').pressSequentially('Хочу немного прогуляться рядом',{delay:65});
  await pause(5000);
  const first=page.waitForResponse(r=>r.url().endsWith('/api/recommend')&&r.request().method()==='POST',{timeout:90000});
  await page.getByTestId('submit-recommend').click();await first;
  await page.getByTestId('recommendation-card').first().waitFor();
  await caption('1 / 4 · Реальные места, рекомендуемое время и источник.');
  await pause(14000);
  const card=page.getByTestId('recommendation-card').first();
  await card.scrollIntoViewIfNeeded();
  await card.getByText('Источники и сведения',{exact:true}).click();
  await caption('Факты имеют источник. Неизвестные свойства остаются неизвестными.');
  await pause(15000);
  await card.getByRole('button',{name:'На карте',exact:true}).click();
  await pause(10000);
  await page.getByTestId('time-30').scrollIntoViewIfNeeded();
  const recalc=page.waitForResponse(r=>r.url().endsWith('/api/recommend'),{timeout:90000});
  await page.getByTestId('time-30').click();await recalc;
  await caption('2 / 4 · Меняем 60 минут на 30 — сервер пересчитывает подбор.');
  await pause(10000);
  const museumQuery='Есть 1–2 часа, хочется интерактивный музей';
  const museumResult=page.waitForResponse(r=>r.url().endsWith('/api/recommend')&&
    r.request().postDataJSON()?.query===museumQuery,{timeout:90000});
  await page.getByTestId('time-120').click();
  await page.getByTestId('query-input').fill(museumQuery);
  const museumPayload=await (await museumResult).json();
  if(museumPayload.recommendations[0]?.poi.attributes.interactive!==true ||
     museumPayload.recommendations[0]?.poi.description_origin!=='official_source_summary')
    throw new Error('Expected evidenced interactive museum for recording; stop rather than claim unsupported description.');
  const museumCard=page.getByTestId('recommendation-card').first();
  await museumCard.waitFor();await museumCard.scrollIntoViewIfNeeded();
  await caption('3 / 4 · Интерес к интерактивному музею подкреплён официальным описанием.');
  await museumCard.getByText('Источники и сведения',{exact:true}).click();
  await pause(17000);
  await page.getByTestId('query-input').fill('Кофе с обязательной розеткой');
  await pause(7000);
  const strict=page.waitForResponse(r=>r.url().endsWith('/api/recommend'),{timeout:90000});
  await page.getByTestId('submit-recommend').click();await strict;
  await caption('4 / 4 · Без подтверждения розетки место не проходит строгое условие.');
  await pause(18000);
  const trace=page.locator('details.trace summary');
  if(await trace.count()){await trace.click();await trace.scrollIntoViewIfNeeded();}
  await caption('Прозрачный результат: что искали, что подтвердили, чего пока не знаем.');
  while(Date.now()-started<150000) await pause(Math.min(10000,150000-(Date.now()-started)));
  const video=page.video();
  await context.close();
  await video.saveAs(path.join(__dirname,'QADAM-demo.webm'));
  await video.delete();
  await browser.close();
  fs.writeFileSync(path.join(__dirname,'recording.json'),JSON.stringify({
    recorded_at:new Date().toISOString(),recording_process_wall_seconds:Math.round((Date.now()-started)/1000),
    viewport:'1440x1000',real_api:true,fixtures:false,voiceover:false,
    map_tiles:'normal browser requests; no prefetch',public_anchor_id:landmark.id,responses
    ,caption_method:'recording-only DOM annotations; no changes to responses or application source',captions
  },null,2));
  console.log('Saved demo/QADAM-demo.webm and recording.json');
})().catch(error=>{console.error(error);process.exit(1)});
