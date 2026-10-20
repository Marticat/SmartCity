const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require('../frontend/node_modules/playwright');

(async()=>{
  const root=path.resolve(__dirname,'..');
  const assets=path.join(__dirname,'assets');fs.mkdirSync(assets,{recursive:true});
  for(const [subset,weight] of ['cyrillic','latin'].flatMap(subset=>[400,700].map(weight=>[subset,weight]))){
    const name=`arimo-${subset}-${weight}-normal.woff2`;
    fs.copyFileSync(path.join(root,'frontend/node_modules/@fontsource/arimo/files',name),path.join(assets,name));
  }
  fs.copyFileSync(path.join(root,'frontend/public/Arimo-LICENSE.txt'),path.join(assets,'Arimo-LICENSE.txt'));
  const screenshot=path.join(root,'demo/frame-45.png');
  if(!fs.existsSync(screenshot)) throw new Error('Run demo/record.cjs and demo/verify-video.cjs first: genuine video frame required.');
  fs.copyFileSync(screenshot,path.join(assets,'product.png'));
  const browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1440,height:900},deviceScaleFactor:1});
  await page.goto(pathToFileURL(path.join(__dirname,'slides.html')).href);
  await page.evaluate(()=>document.fonts.ready);
  const report=await page.locator('.slide').evaluateAll(slides=>slides.map((s,i)=>({
    slide:i+1,width:s.clientWidth,height:s.clientHeight,
    overflow:s.scrollWidth>s.clientWidth||s.scrollHeight>s.clientHeight,
    imageErrors:[...s.querySelectorAll('img')].filter(img=>!img.complete||img.naturalWidth===0).map(img=>img.src)
  })));
  if(report.some(r=>r.overflow||r.imageErrors.length)) throw new Error(JSON.stringify(report));
  await page.pdf({path:path.join(__dirname,'QADAM.pdf'),printBackground:true,preferCSSPageSize:true});
  const review=path.join(root,'artifacts/slides');fs.mkdirSync(review,{recursive:true});
  for(let i=0;i<8;i++) await page.locator('.slide').nth(i).screenshot({path:path.join(review,`slide-${i+1}.png`)});
  fs.writeFileSync(path.join(review,'layout-check.json'),JSON.stringify(report,null,2));
  await browser.close();
  console.log('Exported 8-slide PDF and review PNGs.');
})();
