const { chromium }=require('../frontend/node_modules/playwright');
const path=require('path');
const fs=require('fs');
const {pathToFileURL}=require('url');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 await page.goto(pathToFileURL(path.join(__dirname,'QADAM-demo.webm')).href);
 const video=page.locator('video');await video.waitFor();
 await video.evaluate(v=>{v.pause();v.controls=false;v.style.cssText='width:1440px;height:1000px;position:fixed;left:0;top:0;margin:0';document.body.style.margin='0';});
 const frames=[];
 for(const second of [45,80,115,140]){
   await video.evaluate(async(v,t)=>{v.currentTime=t;await new Promise(resolve=>v.addEventListener('seeked',resolve,{once:true}));},second);
   const file=path.join(__dirname,`frame-${second}.png`);
   await video.screenshot({path:file});frames.push(file);
 }
 const metadata=await video.evaluate(v=>({duration:v.duration,width:v.videoWidth,height:v.videoHeight,readyState:v.readyState}));
 fs.writeFileSync(path.join(__dirname,'video-check.json'),JSON.stringify(metadata,null,2));
 console.log(JSON.stringify(metadata));
 await browser.close();
})();
