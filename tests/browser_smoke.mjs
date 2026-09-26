// Optional real-browser smoke: node tests/browser_smoke.mjs (Chrome/Edge + Python required).
import {spawn, execFileSync} from 'node:child_process';
import {mkdtempSync, readFileSync, existsSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import net from 'node:net';
import http from 'node:http';
function request(url, body){return new Promise((resolve,reject)=>{const req=http.request(url,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{}},res=>{let out='';res.on('data',c=>out+=c);res.on('end',()=>resolve({ok:res.statusCode===200,json:()=>JSON.parse(out)}))});req.on('error',reject);req.end(body?JSON.stringify(body):undefined)})}
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const dir=mkdtempSync(join(tmpdir(),'veyra-browser-'));
const chrome=process.env.CHROME_PATH || (process.platform==='win32'?'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe':'google-chrome');
let server,browser,ws;
try{
  const env={...process.env,VEYRA_DB:join(dir,'demo.sqlite3')};
  execFileSync('python',['seed.py'],{env,stdio:'pipe'});
  const probe=net.createServer();await new Promise(r=>probe.listen(0,'127.0.0.1',r));const port=probe.address().port;probe.close();
  server=spawn('python',['veyra.py'],{env:{...env,VEYRA_PORT:String(port)},stdio:'ignore'});
  const base=`http://127.0.0.1:${port}`;
  let ready=false;for(let i=0;i<70;i++){try{ready=(await request(base)).ok;if(ready)break}catch{}await sleep(100)}
  if(!ready)throw Error('server did not start');
  const token=(await (await request(base+'/api/signup',{username:'browser',password:'password1234'})).json()).token;
  browser=spawn(chrome,['--headless=new','--no-first-run','--disable-gpu','--disable-extensions','--remote-debugging-port=0','--remote-allow-origins=*','--user-data-dir='+join(dir,'profile'),base],{stdio:'ignore'});
  const portFile=join(dir,'profile','DevToolsActivePort');let debugPort;
  for(let i=0;i<100;i++){if(existsSync(portFile)){debugPort=Number(readFileSync(portFile,'utf8').split('\n')[0]);break}await sleep(100)}
  if(!debugPort)throw Error('browser did not start');
  const targets=await (await request(`http://127.0.0.1:${debugPort}/json`)).json();
  const tab=targets.find(t=>t.type==='page'&&t.url.startsWith(base));if(!tab)throw Error('no browser tab');
  ws=new WebSocket(tab.webSocketDebuggerUrl);await new Promise((r,j)=>{ws.addEventListener('open',r,{once:true});ws.addEventListener('error',j,{once:true})});
  let seq=0;const pending=new Map();ws.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.id&&pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id)}});
  async function evalJS(code){const id=++seq;const answer=new Promise(r=>pending.set(id,r));ws.send(JSON.stringify({id,method:'Runtime.evaluate',params:{expression:code,returnByValue:true,awaitPromise:true}}));const msg=await answer;if(msg.result?.exceptionDetails)throw Error(JSON.stringify(msg.result.exceptionDetails));return msg.result?.result?.value}
  async function waitFor(code){for(let i=0;i<70;i++){let value=await evalJS(code);if(value)return value;await sleep(100)}throw Error('UI did not reach: '+code)}
  await waitFor(`location.origin===${JSON.stringify(base)} && document.readyState==='complete'`);
  await evalJS(`sessionStorage.setItem('veyra_token',${JSON.stringify(token)});sessionStorage.setItem('veyra_user','browser')`);
  await evalJS(`location.reload()`).catch(()=>{});
  await waitFor(`document.querySelector('h1')?.textContent==='Dashboard'`);
  await evalJS(`document.querySelector('[data-page="Physical Verification"]').click()`);
  await waitFor(`!!document.querySelector('#count-start')`);
  await evalJS(`{let f=document.querySelector('#count-start');f.sku.value='S';f.location.value='WH/A';f.requestSubmit()}`);
  await waitFor(`!!document.querySelector('#count-submit')`);
  await evalJS(`{let f=document.querySelector('#count-submit');f.qty.value='761';f.requestSubmit()}`);
  await waitFor(`document.querySelector('h1')?.textContent==='Investigation' && document.querySelector('.investigate')?.textContent.includes('761')`);
  const snapshot=await evalJS(`document.querySelector('.investigate').textContent`);
  if(!snapshot.includes('768')||!snapshot.includes('-7')||!snapshot.includes('No recorded movement'))throw Error('incorrect investigation');
  await evalJS(`{let f=document.querySelector('#resolve');f.ref.value='A1';f.note.value='Bin checked manually';f.requestSubmit()}`);
  await waitFor(`document.querySelector('.investigate')?.textContent.includes('Adjusted via A1')`);
  await evalJS(`document.querySelector('#investigate-recount').click()`);
  await waitFor(`!!document.querySelector('#count-start')`);
  await evalJS(`{let f=document.querySelector('#count-start');f.sku.value='S';f.location.value='WH/A';f.requestSubmit()}`);
  await waitFor(`!!document.querySelector('#count-submit')`);
  await evalJS(`{let f=document.querySelector('#count-submit');f.qty.value='761';f.requestSubmit()}`);
  await waitFor(`document.querySelector('h1')?.textContent==='Investigation'`);
  await evalJS(`document.querySelector('[data-page="Receipts"]').click()`);
  await waitFor(`!!document.querySelector('#receipt')`);
  await evalJS(`{let f=document.querySelector('#receipt');for(let [k,v] of Object.entries({ref:'R1',contact:'Supplier',sku:'S',location:'WH/A',qty:'2'}))f[k].value=v;f.requestSubmit()}`);
  await waitFor(`document.querySelector('#content')?.textContent.includes('R1') || document.querySelector('#notice')?.textContent.includes('R1')`).catch(async e=>{throw Error(e.message+' | '+await evalJS(`document.querySelector('#notice')?.textContent`))});
  await evalJS(`document.querySelector('[data-page="Deliveries"]').click()`);
  await waitFor(`!!document.querySelector('#delivery')`);
  await evalJS(`{let f=document.querySelector('#delivery');for(let [k,v] of Object.entries({ref:'D1',sku:'S',location:'WH/A',qty:'9'}))f[k].value=v;f.requestSubmit()}`);
  await waitFor(`document.querySelector('#decision')?.textContent.includes('Inventory changed')`);
  await evalJS(`document.querySelector('#release').click()`);
  await waitFor(`document.querySelector('#decision')?.textContent.includes('DELIVERY HELD')`);
  await evalJS(`document.querySelector('#recount').click()`);
  await waitFor(`!!document.querySelector('#count-start')`);
  await evalJS(`{let f=document.querySelector('#count-start');f.sku.value='S';f.location.value='WH/A';f.requestSubmit()}`);
  await waitFor(`!!document.querySelector('#count-submit')`);
  await evalJS(`{let f=document.querySelector('#count-submit');f.qty.value='763';f.requestSubmit()}`);
  await waitFor(`document.querySelector('h1')?.textContent==='Investigation'`);
  await evalJS(`document.querySelector('[data-page="Deliveries"]').click()`);
  await waitFor(`!!document.querySelector('#delivery')`);
  await evalJS(`document.querySelector('#delivery').requestSubmit()`);
  await waitFor(`document.querySelector('#decision')?.textContent.includes('PHYSICAL EVIDENCE VERIFIED')`);
  await evalJS(`document.querySelector('#release').click()`);
  await waitFor(`document.querySelector('#decision')?.textContent.includes('DELIVERY COMPLETED')`);
  console.log('Browser PASS: count → discrepancy → resolution → recount → receipt → stale hold → recount → delivery');
} catch(e){console.error('Browser FAIL:',e);process.exitCode=1}
finally{ws?.close();browser?.kill();server?.kill();await sleep(300);rmSync(dir,{recursive:true,force:true})}
