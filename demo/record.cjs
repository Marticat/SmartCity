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
  let observedCount=null;
  page.on('response',async response=>{
    if(response.url().endsWith('/api/recommend')&&response.status()===200){
      const body=await response.json();
      observedMode=body.mode;
      observedCount=body.recommendations.length;
      responses.push({mode:body.mode,poi_count:body.recommendations.length,semantic_ready:body.dataset.semantic_ready});
      await page.evaluate(({mode,count})=>{
        const label=document.querySelector('#qadam-recording-caption > div');
        if(label) label.textContent='QADAM · '+(count===0?'НЕТ СОВПАДЕНИЙ':mode==='rag'?'ОТВЕТ GEMINI ПО НАЙДЕННЫМ МЕСТАМ':'РЕЗЕРВНЫЙ ПОИСК');
      },{mode:observedMode,count:observedCount}).catch(()=>{});
    }
  });
  const pause=ms=>page.waitForTimeout(ms);
  const caption=async(text)=>{
    captions.push({at_seconds:Number(((Date.now()-started)/1000).toFixed(2)),text});
    await page.evaluate(({text,mode,count})=>{
    let panel=document.getElementById('qadam-recording-caption');
    if(!panel){
      panel=document.createElement('div');panel.id='qadam-recording-caption';
      panel.style.cssText='position:fixed;top:10px;left:460px;right:24px;z-index:10000;background:#1d2523;color:#fff;padding:10px 18px;border-radius:8px;box-shadow:0 3px 18px #0002;pointer-events:none;font-family:Arial,sans-serif';
      document.body.appendChild(panel);
    }
    panel.replaceChildren();
    const label=document.createElement('div');label.style.cssText='font-size:11px;letter-spacing:1px;color:#c8d8d1;margin-bottom:4px';
    label.textContent='QADAM · '+(count===0?'НЕТ СОВПАДЕНИЙ':mode==='rag'?'ОТВЕТ GEMINI ПО НАЙДЕННЫМ МЕСТАМ':mode==='not_requested'?'АСТАНА':'РЕЗЕРВНЫЙ ПОИСК');
    const line=document.createElement('div');line.style.cssText='font-size:18px;line-height:1.3';line.textContent=text;
    panel.append(label,line);
    },{text,mode:observedMode,count:observedCount});
  };
  const productShot=async(name)=>{
    await page.locator('#qadam-recording-caption').evaluate(el=>el.style.visibility='hidden');
    await page.screenshot({path:path.join(__dirname,name)});
    await page.locator('#qadam-recording-caption').evaluate(el=>el.style.visibility='visible');
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
  await page.getByTestId('submit-recommend').click();
  const firstPayload=await (await first).json();
  if(firstPayload.mode!=='rag') throw new Error('The opening scene must show a real RAG response; recording stopped.');
  observedMode=firstPayload.mode;observedCount=firstPayload.recommendations.length;
  await page.getByTestId('recommendation-card').first().waitFor();
  await page.getByTestId('recommendation-card').first().scrollIntoViewIfNeeded();
  await pause(700);
  await caption('Вот что нашлось рядом. Gemini объясняет, почему эти места подходят.');
  await productShot('product-rag.png');
  fs.writeFileSync(path.join(__dirname,'raw','rag-example.json'),JSON.stringify(firstPayload,null,2));
  await pause(14000);
  const card=page.getByTestId('recommendation-card').first();
  await card.scrollIntoViewIfNeeded();
  await card.getByText('Источники и сведения',{exact:true}).click();
  await caption('Можно открыть источник и проверить сведения о месте.');
  await pause(15000);
  await card.getByRole('button',{name:'На карте',exact:true}).click();
  await pause(10000);
  await page.getByTestId('time-30').scrollIntoViewIfNeeded();
  const recalc=page.waitForResponse(r=>r.url().endsWith('/api/recommend'),{timeout:90000});
  await page.getByTestId('time-30').click();await recalc;
  await caption('Теперь у нас полчаса. Проверим, что предложит сервис.');
  await pause(13000);
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
  await caption('Другой запрос: интерактивный музей. Открываем официальный источник.');
  await museumCard.getByText('Источники и сведения',{exact:true}).click();
  await productShot('product-museum.png');
  await pause(20000);
  await caption('А если нужна обязательная розетка? Проверим ещё одно условие.');
  await page.getByTestId('query-input').fill('Кофе с обязательной розеткой');
  await pause(7000);
  const strict=page.waitForResponse(r=>r.url().endsWith('/api/recommend'),{timeout:90000});
  await page.getByTestId('submit-recommend').click();await strict;
  await page.locator('.empty-results').scrollIntoViewIfNeeded();
  await page.locator('.empty-results').screenshot({path:path.join(__dirname,'product-empty.png')});
  await pause(18000);
  const trace=page.locator('details.trace summary');
  if(await trace.count()){await trace.click();await trace.scrollIntoViewIfNeeded();}
  await caption('Поиск и Gemini работают вместе. Пешеходные маршруты ещё предстоит подключить.');
  await pause(24000);
  while(Date.now()-started<150000) await pause(Math.min(10000,150000-(Date.now()-started)));
  const video=page.video();
  await context.close();
  await video.saveAs(path.join(__dirname,'QADAM-demo.webm'));
  await video.delete();
  await browser.close();
  fs.writeFileSync(path.join(__dirname,'recording.json'),JSON.stringify({
    recorded_at:new Date().toISOString(),recording_process_wall_seconds:Math.round((Date.now()-started)/1000),
    viewport:'1440x1000',real_api:true,fixtures:false,voiceover:false,opening_scene_verified_rag:true,
    map_tiles:'normal browser requests; no prefetch',public_anchor_id:landmark.id,responses
    ,caption_method:'recording-only DOM annotations; no changes to responses or application source',captions
  },null,2));
  console.log('Saved demo/QADAM-demo.webm and recording.json');
})().catch(error=>{console.error(error);process.exit(1)});
