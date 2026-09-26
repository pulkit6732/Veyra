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
  // Hold an older count open until after the receipt and the v2 recount.
  const oldCount=await evalJS(`(async()=>{let user=await api('signup',{username:'latecounter',password:'password1234'});sessionStorage.setItem('late_count_token',user.token);return (await fetch('/api/counts/start',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+user.token},body:JSON.stringify({sku:'S',location:'WH/A'})})).json()})()`);
  await evalJS(`document.querySelector('[data-page="Receipts"]').click()`);
  await waitFor(`!!document.querySelector('#receipt')`);
  await evalJS(`{let f=document.querySelector('#receipt');for(let [k,v] of Object.entries({ref:'R1',contact:'Supplier',sku:'S',location:'WH/A',qty:'2'}))f[k].value=v;f.requestSubmit()}`);
  await waitFor(`document.querySelector('#content')?.textContent.includes('R1') || document.querySelector('#notice')?.textContent.includes('R1')`).catch(async e=>{throw Error(e.message+' | '+await evalJS(`document.querySelector('#notice')?.textContent`))});
  // B is the second real seeded bin balance; verify it before the two-line document.
  await evalJS(`document.querySelector('[data-page="Physical Verification"]').click()`);
  await waitFor(`!!document.querySelector('#count-start')`);
  await evalJS(`{let f=document.querySelector('#count-start');f.sku.value='B';f.location.value='WH/A';f.requestSubmit()}`);
  await waitFor(`!!document.querySelector('#count-submit')`);
  await evalJS(`{let f=document.querySelector('#count-submit');f.qty.value='5';f.requestSubmit()}`);
  await waitFor(`document.querySelector('h1')?.textContent==='Investigation'`);
  await evalJS(`document.querySelector('[data-page="Deliveries"]').click()`);
  await waitFor(`!!document.querySelector('#delivery')`);
  await evalJS(`document.querySelector('#add-line').click()`);
  await evalJS(`{let f=document.querySelector('#delivery'),rows=f.querySelectorAll('.editor-line');f.ref.value='D1';for(let [row,sku,qty] of [[rows[0],'S','9'],[rows[1],'B','3']]){row.querySelector('[name=sku]').value=sku;row.querySelector('[name=location]').value='WH/A';row.querySelector('[name=qty]').value=qty;row.querySelector('[name=qty]').dispatchEvent(new Event('input',{bubbles:true}))}}`);
  if(!await evalJS(`!document.querySelector('#delivery button:not([type])').disabled && document.querySelectorAll('.line-feedback.ok').length===2 && document.querySelectorAll('.line-feedback.ok')[0].textContent.includes('Stale') && document.querySelectorAll('.line-feedback.ok')[1].textContent.includes('Latest shown count agrees')`))throw Error('editor did not show availability and evidence for both lines');
  for(const [sku,location,qty,expected] of [['S','WH/A','1','Duplicate'],['B','WH/A','6','Only 5'],['B','WH/A','0','positive'],['B','WH/A','abc','positive'],['BAD','WH/A','3','Select product']]){
    const result=await evalJS(`{let row=document.querySelectorAll('.editor-line')[1];row.querySelector('[name=sku]').value=${JSON.stringify(sku)};row.querySelector('[name=location]').value=${JSON.stringify(location)};row.querySelector('[name=qty]').value=${JSON.stringify(qty)};row.querySelector('[name=qty]').dispatchEvent(new Event('input',{bubbles:true}));[document.querySelector('#delivery button:not([type])').disabled,row.querySelector('.line-feedback').textContent]}`);
    if(!result[0]||!result[1].includes(expected))throw Error('editor accepted invalid line: '+JSON.stringify([sku,location,qty,result]));
  }
  await evalJS(`{let row=document.querySelectorAll('.editor-line')[1];row.querySelector('[name=sku]').value='B';row.querySelector('[name=qty]').value='3';row.querySelector('[name=qty]').dispatchEvent(new Event('input',{bubbles:true}))}`);
  if(!await evalJS(`!document.querySelector('#delivery button:not([type])').disabled`))throw Error('editor did not recover');
  await evalJS(`document.querySelector('#delivery').requestSubmit()`);
  await waitFor(`document.querySelector('.progress')?.textContent.includes('DRAFT')`);
  for(const [action,expected] of [['READY','READY'],['START_PICKING','PICKING']]){
    await evalJS(`document.querySelector('[data-step="${action}"]').click();document.querySelector('[data-step="${action}"]')?.click()`);
    await waitFor(`document.querySelector('.progress .current')?.textContent==='${expected}'`);
    await evalJS(`location.reload()`).catch(()=>{});
    await waitFor(`document.querySelector('.progress .current')?.textContent==='${expected}'`);
  }
  for(const [qty,remaining] of [['9',1],['3',0]]){await evalJS(`{let f=document.querySelector('#delivery-quantity');f.qty.value='${qty}';f.requestSubmit()}`);await waitFor(`document.querySelectorAll('#delivery-quantity option').length===${remaining}`)}
  await evalJS(`document.querySelector('[data-step="COMPLETE_PICKING"]').click()`);
  await waitFor(`document.querySelector('.progress .current')?.textContent==='PICKED'`);
  await evalJS(`location.reload()`).catch(()=>{});
  await waitFor(`document.querySelector('.progress .current')?.textContent==='PICKED'`);
  await evalJS(`document.querySelector('[data-step="START_PACKING"]').click()`);
  await waitFor(`document.querySelector('.progress .current')?.textContent==='PACKING'`);
  await evalJS(`location.reload()`).catch(()=>{});
  await waitFor(`document.querySelector('.progress .current')?.textContent==='PACKING'`);
  for(const [qty,remaining] of [['9',1],['3',0]]){await evalJS(`{let f=document.querySelector('#delivery-quantity');f.qty.value='${qty}';f.requestSubmit()}`);await waitFor(`document.querySelectorAll('#delivery-quantity option').length===${remaining}`)}
  await evalJS(`document.querySelector('[data-step="COMPLETE_PACKING"]').click()`);
  await waitFor(`document.querySelector('.progress .current')?.textContent==='PACKED'`);
  await evalJS(`location.reload()`).catch(()=>{});
  await waitFor(`document.querySelector('h1')?.textContent==='Deliveries' && document.querySelector('.progress .current')?.textContent==='PACKED'`);
  await evalJS(`document.querySelector('[data-page="Inventory"]').click()`);
  await waitFor(`document.querySelector('h1')?.textContent==='Inventory'`);
  await evalJS(`history.back()`);
  await waitFor(`document.querySelector('h1')?.textContent==='Deliveries' && document.querySelector('.progress .current')?.textContent==='PACKED'`);
  await evalJS(`history.forward()`);
  await waitFor(`document.querySelector('h1')?.textContent==='Inventory'`);
  await evalJS(`history.back()`);
  await waitFor(`document.querySelector('.progress .current')?.textContent==='PACKED'`);
  await evalJS(`document.querySelector('#release').click();document.querySelector('#release')?.click()`);
  await waitFor(`document.querySelector('#decision')?.textContent.includes('DELIVERY BLOCKED') && document.querySelector('#decision')?.textContent.includes('Recount this product') && document.querySelector('#decision')?.textContent.includes('Current count agrees')`);
  if(!await evalJS(`(async()=>{let s=await api('inventory'),m=await api('movements'),d=(await api('decisions')).filter(x=>x.ref==='D1'&&x.stage==='COMMIT');return s.find(x=>x.sku==='S').qty===763&&s.find(x=>x.sku==='B').qty===5&&!m.some(x=>x.kind==='DELIVER')&&d.length===2})()`))throw Error('double-click blocked commit or mutated stock');
  await evalJS(`location.reload()`).catch(()=>{});
  await waitFor(`document.querySelector('.progress .current')?.textContent==='PACKED' && document.querySelector('#content')?.textContent.includes('Latest recorded final attempt')`);
  if(!await evalJS(`document.querySelector('[data-recount-sku="S"]')?.textContent.includes('Count this line')`))throw Error('persisted blocked attempt lost next action');
  await evalJS(`document.querySelector('[data-page="Evidence Holds"]').click()`);
  await waitFor(`document.querySelector('#content')?.textContent.includes('STALE_PHYSICAL_EVIDENCE')`);
  await evalJS(`document.querySelector('[data-page="Deliveries"]').click()`);
  await waitFor(`document.querySelector('.progress .current')?.textContent==='PACKED'`);
  await evalJS(`document.querySelector('[data-recount-sku="S"]')?.click()`).catch(()=>{});
  if(!await evalJS(`document.querySelector('h1')?.textContent==='Physical Verification'`))await evalJS(`document.querySelector('[data-page="Physical Verification"]').click()`);
  await waitFor(`!!document.querySelector('#count-start')`);
  await evalJS(`{let f=document.querySelector('#count-start');f.sku.value='S';f.location.value='WH/A';f.requestSubmit()}`);
  await waitFor(`!!document.querySelector('#count-submit')`);
  await evalJS(`{let f=document.querySelector('#count-submit');f.qty.value='763';f.requestSubmit()}`);
  await waitFor(`document.querySelector('h1')?.textContent==='Investigation'`);
  const lateResult=await evalJS(`fetch('/api/counts/submit',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+sessionStorage.getItem('late_count_token')},body:JSON.stringify({session_id:${oldCount.session_id},qty:761})}).then(r=>r.json())`);
  if(lateResult?.status!=='STALE')throw Error('late observation was not stale: '+JSON.stringify({oldCount,lateResult}));
  await evalJS(`document.querySelector('[data-page="Deliveries"]').click()`);
  await waitFor(`!!document.querySelector('[data-order="D1"]')`);
  await evalJS(`document.querySelector('[data-order="D1"]').click()`);
  await waitFor(`document.querySelector('#release')!==null`);
  if(!await evalJS(`document.querySelector('.line-table tbody tr')?.textContent.includes('CURRENT')`))throw Error('late stale observation hid current count in delivery');
  await evalJS(`document.querySelector('#release').click()`);
  await waitFor(`document.querySelector('#decision')?.textContent.includes('DELIVERY COMPLETED')`);
  await evalJS(`document.querySelector('[data-page="Inventory"]').click()`);
  await waitFor(`document.querySelector('#content')?.textContent.includes('754') && document.querySelector('#content')?.textContent.includes('2')`);
  await evalJS(`document.querySelector('[data-page="Audit"]').click()`);
  await waitFor(`document.querySelector('#content')?.textContent.includes('COMPLETE_PACKING') && document.querySelector('#content')?.textContent.includes('DELIVER')`);
  if(!await evalJS(`(async()=>{let s=await api('inventory'),m=(await api('movements')).filter(x=>x.delivery_ref==='D1'),e=(await api('delivery-events')).filter(x=>x.ref==='D1'&&x.action==='COMMIT'),d=(await api('decisions')).filter(x=>x.ref==='D1'&&x.stage==='COMMIT');return s.find(x=>x.sku==='S').qty===754&&s.find(x=>x.sku==='B').qty===2&&m.length===2&&e.length===2&&e.every(x=>x.evidence_id)&&d.length===4&&d.filter(x=>x.status==='BLOCKED').length===1})()`))throw Error('final ledger/evidence/decision linkage incorrect');
  const renderMs=await evalJS(`(async()=>{let t=performance.now();await render('Deliveries');return Math.round((performance.now()-t)*100)/100})()`);
  // Inspect the real narrow viewport, including the guided editor and detail table.
  const mobileId=++seq;const mobileResult=new Promise(r=>pending.set(mobileId,r));ws.send(JSON.stringify({id:mobileId,method:'Emulation.setDeviceMetricsOverride',params:{width:390,height:844,deviceScaleFactor:1,mobile:true}}));await mobileResult;
  await waitFor(`!!document.querySelector('.editor-line') && !!document.querySelector('.line-table') && !!document.querySelector('nav')`);
  const mobile=await evalJS(`({viewport:document.documentElement.clientWidth,content:document.documentElement.scrollWidth,nav:getComputedStyle(document.querySelector('nav')).display,editorColumns:getComputedStyle(document.querySelector('.editor-line')).gridTemplateColumns,tableScroll:document.querySelector('.line-table')?.closest('.table-wrap').scrollWidth})`);
  if(mobile.content>mobile.viewport+2||mobile.nav!=='flex'||!mobile.editorColumns||!mobile.tableScroll)throw Error('mobile delivery layout overflows: '+JSON.stringify(mobile));
  for(const width of [430,768,1024,1280,1440]){
    const id=++seq,answer=new Promise(r=>pending.set(id,r));ws.send(JSON.stringify({id,method:'Emulation.setDeviceMetricsOverride',params:{width,height:900,deviceScaleFactor:1,mobile:width===768}}));await answer;
    const layout=await evalJS(`({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,nav:getComputedStyle(document.querySelector('nav')).display})`);
    if(layout.width<width-20||layout.width>width||layout.scroll>layout.width+2||layout.nav===(width<=768?'grid':'flex'))throw Error('layout at '+width+': '+JSON.stringify(layout));
  }
  for(const width of [390,768,1440]){
    const id=++seq,answer=new Promise(r=>pending.set(id,r));ws.send(JSON.stringify({id,method:'Emulation.setDeviceMetricsOverride',params:{width,height:900,deviceScaleFactor:1,mobile:width<800}}));await answer;
    for(const page of ['Dashboard','Inventory','Physical Verification','Investigation','Receipts','Deliveries','Audit']){
      await evalJS(`document.querySelector('[data-page=${JSON.stringify(page)}]')?.click()`);
      await waitFor(`document.querySelector('h1')?.textContent===${JSON.stringify(page)} && !document.querySelector('#content')?.textContent.startsWith('Loading')`);
      const sizes=await evalJS(`({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,buttons:[...document.querySelectorAll('#content button')].filter(b=>{let r=b.getBoundingClientRect();return !b.closest('.table-wrap, nav') && r.width>0 && (r.left< -1||r.right>innerWidth+1)}).length})`);
      if(sizes.scroll>sizes.width+2||sizes.buttons)throw Error('section overflow '+page+' at '+width+': '+JSON.stringify(sizes));
    }
  }
  await evalJS(`location.hash='Deliveries/not-found'`);
  await waitFor(`document.querySelector('#content')?.textContent.includes('Delivery not-found was not found')`);
  await evalJS(`window.realFetch=window.fetch;window.fetch=(...args)=>String(args[0]).includes('/api/inventory')?Promise.resolve(new Response(JSON.stringify({error:'UNAVAILABLE'}),{status:503,headers:{'Content-Type':'application/json'}})):window.realFetch(...args);render('Inventory')`);
  await waitFor(`document.querySelector('#content')?.textContent.includes('Unable to load Inventory')`);
  await evalJS(`window.fetch=window.realFetch;document.querySelector('[data-page="Inventory"]').click()`);
  await waitFor(`document.querySelector('#stock-table')?.textContent.includes('754')`);
  await evalJS(`window.fetch=(...args)=>String(args[0]).includes('/api/inventory')?new Promise(resolve=>setTimeout(()=>resolve(window.realFetch(...args)),350)):window.realFetch(...args);window.slowRender=render('Inventory');'started'`);
  if(!await evalJS(`document.querySelector('#content')?.textContent.includes('Loading')`))throw Error('slow API did not retain loading state');
  await waitFor(`document.querySelector('#stock-table')?.textContent.includes('754')`);
  await evalJS(`window.fetch=window.realFetch;location.hash='Deliveries/%'`);
  await waitFor(`document.querySelector('h1')?.textContent==='Dashboard'`);
  // On the real seeded ledger, an agreeing latest count must not hide an older conflict.
  await evalJS(`document.querySelector('[data-page="Physical Verification"]').click()`);
  await waitFor(`!!document.querySelector('#count-start')`);
  for(const quantity of ['1','2']){
    await evalJS(`{let f=document.querySelector('#count-start');f.sku.value='B';f.location.value='WH/A';f.requestSubmit()}`);
    await waitFor(`!!document.querySelector('#count-submit')`);
    await evalJS(`{let f=document.querySelector('#count-submit');f.qty.value='${quantity}';f.requestSubmit()}`);
    await waitFor(`document.querySelector('h1')?.textContent==='Investigation'`);
    if(quantity==='1'){await evalJS(`document.querySelector('[data-page="Physical Verification"]').click()`);await waitFor(`!!document.querySelector('#count-start')`)}
  }
  await waitFor(`document.querySelector('.investigate')?.textContent.includes('CONFLICTING COUNTS') && !!document.querySelector('#resolve')`);
  if(!await evalJS(`(async()=>{let r=await api('deliveries/preflight',{ref:'CONFLICT',sku:'B',location:'WH/A',qty:1});return r.reason==='CONFLICTING_PHYSICAL_EVIDENCE'})()`))throw Error('agreeing latest count cleared conflict');
  await evalJS(`{let f=document.querySelector('#resolve');f.ref.value='ACK1';f.note.value='Bin and movement records reviewed; keep ledger';f.requestSubmit()}`);
  await waitFor(`document.querySelector('.investigate')?.textContent.includes('Conflict acknowledged; ledger quantity unchanged')`);
  if(!await evalJS(`(async()=>{let s=await api('inventory'),m=await api('movements');return s.find(x=>x.sku==='B').qty===2 && s.find(x=>x.sku==='B').version===2 && m.find(x=>x.ref==='ACK1').qty===2})()`))throw Error('conflict acknowledgment changed ledger total');
  // Exercise a real 409 through the form, not just the API helper: duplicate receipt ref.
  await evalJS(`document.querySelector('[data-page="Receipts"]').click()`);
  await waitFor(`!!document.querySelector('#receipt')`);
  await evalJS(`{let f=document.querySelector('#receipt');for(let [k,v] of Object.entries({ref:'R1',contact:'Supplier',sku:'S',location:'WH/A',qty:'2'}))f[k].value=v;f.requestSubmit()}`);
  await waitFor(`document.querySelector('#notice')?.textContent.includes('reference')`);
  if(!await evalJS(`(async()=>{let x=await api('inventory');return x.find(r=>r.sku==='S').qty===754})()`))throw Error('duplicate receipt changed stock');
  // A 500 must remain an error, and a lost session must return to sign-in.
  await evalJS(`window.fetch=(...args)=>String(args[0]).includes('/api/inventory')?Promise.resolve(new Response(JSON.stringify({error:'UNAVAILABLE'}),{status:500,headers:{'Content-Type':'application/json'}})):window.realFetch(...args);render('Inventory')`);
  await waitFor(`document.querySelector('#content')?.textContent.includes('Server error')`);
  await evalJS(`window.fetch=window.realFetch;sessionStorage.setItem('veyra_token','expired');state.token='expired';render('Inventory')`);
  await waitFor(`!!document.querySelector('#auth')`);
  await evalJS(`{let f=document.querySelector('#auth');f.username.value='browser';f.password.value='password1234';f.requestSubmit()}`);
  await waitFor(`document.querySelector('h1')?.textContent==='Inventory' && document.querySelector('#stock-table')?.textContent.includes('754')`);
  await evalJS(`document.querySelector('[data-page="Dashboard"]').click()`);
  await waitFor(`document.querySelector('#content')?.textContent.includes('Operational overview')`);
  console.log('Chrome two-line Deliveries render (including API calls):',renderMs,'ms; 390px mobile:',JSON.stringify(mobile));
  console.log('Browser PASS: seeded discrepancy → adjustment → receipt → stale hold → recount → two-line atomic commit → audit');
} catch(e){console.error('Browser FAIL:',e);process.exitCode=1}
finally{ws?.close();browser?.kill();server?.kill();await sleep(300);rmSync(dir,{recursive:true,force:true})}
