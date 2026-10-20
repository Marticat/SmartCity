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
 const recording=JSON.parse(fs.readFileSync(path.join(__dirname,'recording.json'),'utf8'));
 const sceneSeconds=recording.captions.map(c=>Math.round(c.at_seconds+4));
 for(const second of [...new Set([45,80,115,140,...sceneSeconds])]){
   await video.evaluate(async(v,t)=>{v.currentTime=t;await new Promise(resolve=>v.addEventListener('seeked',resolve,{once:true}));},second);
   const folder=[45,80,115,140].includes(second)?__dirname:path.join(__dirname,'raw');
   const file=path.join(folder,`frame-${second}.png`);
   await video.screenshot({path:file});frames.push(file);
 }
 const metadata={...await video.evaluate(v=>({duration:v.duration,width:v.videoWidth,height:v.videoHeight,readyState:v.readyState})),scene_review_seconds:sceneSeconds};
 fs.writeFileSync(path.join(__dirname,'video-check.json'),JSON.stringify(metadata,null,2));
 console.log(JSON.stringify(metadata));
 await browser.close();
})();
