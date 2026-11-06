'use client';
import TabIcon from '../ui-icons';
import {useCallback,useEffect,useState} from 'react';
const API=process.env.NEXT_PUBLIC_BACKEND_URL||'https://nur-oqiw-bot.mcweb.uz';
function telegramProfileUrl(user){
 const name=String(user?.username||'').replace(/^@/,'');
 if(/^[A-Za-z0-9_]{5,32}$/.test(name))return 'https://t.me/'+name;
 const id=Number(user?.telegram_id);
 return Number.isSafeInteger(id)&&id>0?'tg://user?id='+id:null;
}
function adminDateTime(value){
 const date=new Date(value||'');
 if(!value||Number.isNaN(date.getTime()))return '—';
 return new Intl.DateTimeFormat('uz-UZ',{timeZone:'Asia/Tashkent',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(date);
}
function adminAnswers(value){
 const answers=Object.entries(value||{}).filter(([key])=>/^\d+$/.test(key)).sort(([a],[b])=>Number(a)-Number(b));
 return answers.length?answers.map(([number,answer])=>number+'. '+String(answer||'—')).join(' · '):'Javob kiritilmagan';
}
function MenuEditor({initData}){
 const [role,setRole]=useState('user');
 const [menus,setMenus]=useState(null);
 const [drafts,setDrafts]=useState({});
 const [busy,setBusy]=useState('');
 const [error,setError]=useState('');
 const load=useCallback(async()=>{
  if(!initData)return;
  setBusy('load');setError('');
  try{
   const res=await fetch(API+'/api/admin/menus',{headers:{Authorization:'tma '+initData},cache:'no-store'});
   const data=await res.json();
   if(!data.ok)throw new Error(data.error||'Menyular olinmadi');
   setMenus(data.menus);setDrafts({});
  }catch(e){setError(e.message)}finally{setBusy('')}
 },[initData]);
 useEffect(()=>{load()},[load]);
 async function update(item,action='save',direction=0){
  setBusy(item.key);setError('');
  try{
   const values={...item,...(drafts[item.key]||{})};
   const res=await fetch(API+'/api/admin/menus',{
    method:'POST',headers:{Authorization:'tma '+initData,'Content-Type':'application/json'},
    body:JSON.stringify({role,key:item.key,action,direction,label:values.label,style:values.style,emoji_id:values.emoji_id,visible:values.visible})
   });
   const data=await res.json();
   if(!data.ok)throw new Error(data.error||'Saqlashda xatolik');
   setMenus(data.menus);
   setDrafts(old=>({...old,[item.key]:undefined}));
  }catch(e){setError(e.message)}finally{setBusy('')}
 }
 const entries=menus?.[role]||[];
 return <section className="admin-card menu-editor">
  <div className="admin-section-title"><div><h2>Menyu sozlamalari</h2><p>Telegram pastki klaviaturasi: nom, rang, premium emoji, tartib va ko‘rinish.</p></div><button className="admin-refresh" onClick={load} disabled={!!busy}>Yangilash</button></div>
  <div className="menu-editor-tabs"><button className={role==='user'?'selected':''} onClick={()=>{setRole('user');setDrafts({})}}>Foydalanuvchilar</button><button className={role==='admin'?'selected':''} onClick={()=>{setRole('admin');setDrafts({})}}>Admin</button></div>
  {error&&<p role="alert" className="admin-error">{error}</p>}
  {!menus?<p className="admin-muted">Menyu yuklanmoqda…</p>:<div className="menu-editor-items">{entries.map((item,index)=>{
   const val={...item,...(drafts[item.key]||{})};
   const change=(field,value)=>setDrafts(old=>({...old,[item.key]:{...(old[item.key]||{}),[field]:value}}));
   return <div className="menu-editor-item" key={item.key}>
    <div className="menu-editor-top"><strong>{index+1}. {item.key}</strong><span>{val.style==='success'?'Yashil':val.style==='danger'?'Qizil':val.style==='primary'?'Ko‘k':'Oddiy'}</span></div>
    <div className="menu-editor-fields"><label>Tugma nomi<input value={val.label} maxLength={55} onChange={e=>change('label',e.target.value)}/></label>
    <label>Rang<select value={val.style} onChange={e=>change('style',e.target.value)}><option value="primary">Ko‘k</option><option value="success">Yashil</option><option value="danger">Qizil</option><option value="default">Rangsiz</option></select></label>
    <label>Premium emoji ID<input value={val.emoji_id||''} inputMode="numeric" placeholder="Telegram custom emoji ID" onChange={e=>change('emoji_id',e.target.value)}/></label></div>
    <div className="menu-editor-actions">
    <label className="menu-editor-checkbox"><input type="checkbox" checked={val.visible} disabled={item.key==='Aktiv testlar'||item.key==='Menyu sozlamalari'} onChange={e=>change('visible',e.target.checked)}/> Ko‘rsatish</label>
    <button onClick={()=>update(item,'move',-1)} disabled={!!busy||index===0} title="Yuqoriga">↑</button>
    <button onClick={()=>update(item,'move',1)} disabled={!!busy||index===entries.length-1} title="Pastga">↓</button>
    <button className="action-danger" onClick={()=>update(item,'reset')} disabled={!!busy}>Tiklash</button>
    <button className="admin-primary" onClick={()=>update(item)} disabled={!!busy}>{busy===item.key?'Saqlanmoqda…':'Saqlash'}</button>
    </div>
   </div>
  })}</div>}
  <p className="admin-muted">Premium emoji ID ni olish uchun Telegram botidagi «Menyu sozlamalari» bo‘limidan emoji yuboring. Rang va emoji ko‘rinishi Telegram versiyasiga bog‘liq. O‘zgarishlar foydalanuvchi /start bosganda yoki menyu qayta ko‘rsatilganda kuchga kiradi.</p>
 </section>;
}

function mockTimerLabel(test,now){
 if(!test?.timer_ends_at)return test?.active?'Taymer birinchi qatnashchida boshlanadi':'Taymer boshlanmagan';
 const end=Date.parse(test.timer_ends_at);
 if(!Number.isFinite(end))return 'Taymer holati aniqlanmadi';
 const seconds=Math.max(0,Math.ceil((end-now)/1000));
 const value=String(Math.floor(seconds/3600)).padStart(2,'0')+':'+String(Math.floor((seconds%3600)/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0');
 if(seconds===0)return test.active?'Vaqt tugadi · yakunlanmoqda':'Yakunlangan';
 return test.active?'Qolgan vaqt '+value:'To‘xtatilgan · '+value+' qoldi';
}
export default function Admin(){
 const [mockClockNow,setMockClockNow]=useState(()=>Date.now());
 useEffect(()=>{const timer=setInterval(()=>setMockClockNow(Date.now()),1000);return()=>clearInterval(timer)},[]);
 const [showMenuEditor,setShowMenuEditor]=useState(false);
 const [mockBusy,setMockBusy]=useState('');
 const [initData,setInitData]=useState(''),[loading,setLoading]=useState(true),[data,setData]=useState(null),[error,setError]=useState(''),[note,setNote]=useState(''),[busy,setBusy]=useState('');
 const [schedule,setSchedule]=useState({date:'',start:'08:00',end:'22:00',timezone:'Asia/Tashkent'});
 const [newTestName,setNewTestName]=useState(''),[newTestCode,setNewTestCode]=useState(''),[newTestBusy,setNewTestBusy]=useState(false);
 const [diagnostics,setDiagnostics]=useState(null),[diagnosticsBusy,setDiagnosticsBusy]=useState(false);
 const [jarvisMessages,setJarvisMessages]=useState([]),[jarvisAction,setJarvisAction]=useState(null),[jarvisDraft,setJarvisDraft]=useState(''),[jarvisBusy,setJarvisBusy]=useState(false),[jarvisError,setJarvisError]=useState('');
 const [jarvisModel,setJarvisModel]=useState('Astra 6'),[jarvisModelOpen,setJarvisModelOpen]=useState(false);
 const jarvisModels=['Astra 6','Astra 5','Claude Opus 4.6','Claude Sonnet 4.6','Claude Haiku 4.5','GPT latest','GPT pro','GPT fast','Gemini Pro','Gemini Flash','DeepSeek R1','DeepSeek V3','Grok latest','Qwen latest','Llama latest','Mistral latest','Custom model','JARVIS Core'];
 const [editingTest,setEditingTest]=useState(''),[editQuestions,setEditQuestions]=useState([]),[resultsTest,setResultsTest]=useState(''),[fullResults,setFullResults]=useState([]),[editorBusy,setEditorBusy]=useState('');
 const [rankUsername,setRankUsername]=useState(''),[rankPosition,setRankPosition]=useState('1');
 const request=useCallback(async(raw,method='GET',body)=>{const res=await fetch(API+(method==='GET'?'/api/admin/overview':'/api/admin/test/toggle'),{method,cache:'no-store',headers:{Authorization:'tma '+raw,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});return res.json()},[]);
 const refresh=useCallback(async(raw)=>{setLoading(true);setError('');try{const j=await request(raw);if(!j.ok)throw new Error(j.error==='admin_only'?'Bu bo‘lim faqat administrator uchun.':'Admin ma’lumotlari yuklanmadi.');setData(j);const sr=await fetch(API+'/api/admin/schedule',{cache:'no-store',headers:{Authorization:'tma '+raw}});const sj=await sr.json();if(sj.ok&&sj.schedule)setSchedule(sj.schedule)}catch(e){setError(e.message||'Server bilan aloqa yo‘q.');}finally{setLoading(false)}},[request]);
 useEffect(()=>{const target=window.location.hash.slice(1);if(['jarvis','results'].includes(target)){let tries=0;const scroll=()=>{const element=document.getElementById(target);if(element){element.scrollIntoView({behavior:'smooth',block:'start'});return}if(tries++<20)window.setTimeout(scroll,250)};scroll()}},[]);
 useEffect(()=>{let stopped=false,timer=null,tries=0;const boot=()=>{if(stopped)return;const tg=window.Telegram?.WebApp;const raw=tg?.initData||'';if(tg){try{tg.ready();tg.expand();}catch{}}if(raw){setInitData(raw);setError('');refresh(raw);return}tries++;if(tries<40){timer=window.setTimeout(boot,250);return}setError('Telegram sessiyasi olinmadi. Admin panelini bot ichidagi “Mini App admini” yoki “Jarvis” tugmasidan oching. So‘ng “Qayta ulanish”ni bosing.');setLoading(false)};const retry=()=>{if(stopped)return;tries=0;setLoading(true);boot()};boot();window.addEventListener('pageshow',retry);window.addEventListener('focus',retry);return()=>{stopped=true;if(timer)window.clearTimeout(timer);window.removeEventListener('pageshow',retry);window.removeEventListener('focus',retry)}},[refresh]);
 useEffect(()=>{if(!initData)return;const id=window.setInterval(()=>refresh(initData),15000);return()=>window.clearInterval(id)},[initData,refresh]);
 async function runDiagnostics(){if(!initData){setDiagnostics({ok:false,error:'no_telegram_session'});setNote('Telegram sessiyasi yo‘q. Admin panelini bot ichidagi Mini App tugmasidan oching.');return}setDiagnosticsBusy(true);setNote('Diagnostika serverdan so‘ralmoqda…');try{const controller=new AbortController();const timer=window.setTimeout(()=>controller.abort(),30000);let r;try{r=await fetch(API+'/api/admin/diagnostics?ts='+Date.now(),{cache:'no-store',signal:controller.signal,headers:{Authorization:'tma '+initData}})}finally{window.clearTimeout(timer)}const j=await r.json().catch(()=>({ok:false,error:'invalid_response'}));if(!r.ok&&!j.error)j.error='http_'+r.status;setDiagnostics(j);setNote(j.ok?'Diagnostika yakunlandi. Natija quyida ko‘rsatilgan.':j.error==='admin_only'?'Telegram admin ID serverdagi ADMIN_CHAT_ID bilan mos emas.':j.error==='no_telegram_session'?'Telegram sessiyasi yo‘q. Mini Appni bot ichidan oching.':j.error==='invalid_response'?'Backend JSON javobi qaytmadi; server loglarini tekshirish kerak.':'Diagnostika muvaffaqiyatsiz: '+(j.error||'noma’lum xato'))}catch(e){setDiagnostics({ok:false,error:e.name==='AbortError'?'timeout':'network'});setNote(e.name==='AbortError'?'Diagnostika 30 soniyada javob olmadi. Backend loglarini tekshirish kerak.':'Diagnostika backendiga ulanib bo‘lmadi. Internet, CORS va server holatini tekshirish kerak.')}finally{setDiagnosticsBusy(false)}}
 async function saveSchedule(){if(!initData||!schedule.date||!schedule.start||!schedule.end){setNote('Sana, boshlanish va tugash vaqtini kiriting.');return}setBusy('schedule');setNote('');try{const r=await fetch(API+'/api/admin/schedule',{method:'POST',headers:{Authorization:'tma '+initData,'Content-Type':'application/json'},body:JSON.stringify(schedule)});const j=await r.json();if(!j.ok)throw new Error('Sana yoki vaqt formati noto‘g‘ri.');setSchedule(j.schedule);setNote(j.message||'Jadval saqlandi.')}catch(e){setNote(e.message||'Jadvalni saqlab bo‘lmadi.')}finally{setBusy('')}}
 async function createTest(e){e.preventDefault();if(!initData){setNote('Telegram sessiyasi topilmadi. Panelni bot ichidan qayta oching.');return}const name=newTestName.trim(),code=newTestCode.trim();if(!name||!/^[A-Za-z0-9_-]{3,40}$/.test(code)){setNote('Test nomini va 3–40 belgili lotin harf/raqamdan iborat kodni kiriting.');return}setNewTestBusy(true);setNote('');try{const r=await fetch(API+'/api/admin/test/create',{method:'POST',cache:'no-store',headers:{Authorization:'tma '+initData,'Content-Type':'application/json'},body:JSON.stringify({name,code})});const j=await r.json();if(!j.ok)throw new Error(j.error==='code_exists'?'Bu kod avval ishlatilgan. Boshqa kod tanlang.':j.error==='admin_only'?'Administrator ruxsati tasdiqlanmadi.':'Test yaratilmadi. Server javobini tekshiring.');setNewTestName('');setNewTestCode('');setNote(j.message||'Test yaratildi.');await refresh(initData);if(j.test?.test_id)await loadQuestions(j.test.test_id)}catch(e){setNote(e.message||'Test yaratishda xatolik yuz berdi.')}finally{setNewTestBusy(false)}}
 async function sendMockPdf(testId,kind){setMockBusy(kind+'-'+testId);try{const r=await fetch(API+'/api/admin/mock/'+(kind==='questions'?'questions-pdf':'results-pdf'),{method:'POST',headers:{Authorization:'tma '+initData,'Content-Type':'application/json'},body:JSON.stringify({test_id:testId})});const j=await r.json();if(!j.ok)throw new Error(j.error==='code_required'?'Avval yakuniy test kodini saqlang.':j.error==='questions_channel_required'?'Savollar PDF kanali sozlanmagan.':j.error==='questions_required'?'Testga avval savollar qo‘shing.':j.error==='questions_pdf_failed'?'Bot kanalga PDF yubora olmadi. Botni kanalga administrator qilib qo‘shing.':j.error==='results_pdf_failed'?'Natijalar PDF’i yuborilmadi. Backend logini tekshiring.':j.error==='no_results'?'Testda hali yakunlangan natija yo‘q.':'PDF yuborilmadi.');setNote(j.message||'PDF yuborildi.');if(kind==='questions')await refresh(initData)}catch(e){setNote(e.message||'PDF yuborishda xatolik.')}finally{setMockBusy('')}}
 async function startMock(t){
  if(!window.confirm(t.name+' testini hozir boshlaysizmi? Belgilangan taymer shu zahoti yuradi.'))return;
  setMockBusy('start-'+t.test_id);setNote('');
  try{const r=await fetch(API+'/api/admin/mock/start',{method:'POST',headers:{Authorization:'tma '+initData,'Content-Type':'application/json'},body:JSON.stringify({test_id:t.test_id})});const j=await r.json();if(!j.ok)throw new Error(j.message||'MOCK testni boshlash imkoni bo‘lmadi.');setNote(j.message||'Test boshlandi.');await refresh(initData)}
  catch(e){setNote(e.message||'MOCK testni boshlashda xatolik.')}
  finally{setMockBusy('')}
 }
 async function stopMock(t){
  if(!window.confirm(t.name+' testini hozir to‘xtatib, qatnashchilarni hisoblaymi?'))return;
  await toggle(t);
 }
 async function restartMock(t){
  if(!window.confirm(t.name+' testini qayta o‘tkazasizmi? Eski natijalar saqlanadi; test kodi o‘zgarmaydi.'))return;
  setMockBusy('restart-'+t.test_id);setNote('');
  try{const r=await fetch(API+'/api/admin/mock/restart',{method:'POST',headers:{Authorization:'tma '+initData,'Content-Type':'application/json'},body:JSON.stringify({test_id:t.test_id})});const j=await r.json();if(!j.ok)throw new Error(j.message|| (j.error==='mock_in_progress'?'Test hali davom etmoqda. Timer tugagach qayta o‘tkazing.':'Testni qayta ochib bo‘lmadi.'));setNote(j.message||'MOCK test qayta ochildi.');await refresh(initData)}
  catch(e){setNote(e.message||'MOCK testni qayta ochishda xatolik.')}
  finally{setMockBusy('')}
 }
 async function toggle(t){setBusy(t.test_id);setNote('');try{const j=await request(initData,'POST',{test_id:t.test_id});if(!j.ok)throw new Error(j.error==='admin_only'?'Admin ruxsati tasdiqlanmadi.':'Test holatini o‘zgartirib bo‘lmadi.');setNote(j.message+(j.finalized?' Yakunlangan urinishlar: '+j.finalized+'.':''));await refresh(initData)}catch(e){setNote(e.message||'Xatolik yuz berdi.')}finally{setBusy('')}}
 async function loadQuestions(testId){
  if(!initData)return;setEditorBusy('questions');setEditingTest(testId);
  try{const r=await fetch(API+'/api/admin/test/questions?test_id='+encodeURIComponent(testId),{cache:'no-store',headers:{Authorization:'tma '+initData}});const j=await r.json();if(!j.ok)throw Error();setEditQuestions(j.questions||[])}catch{setNote('Savollar yuklanmadi. Backendni tekshiring.');setEditingTest('')}finally{setEditorBusy('')}
 }
 async function saveQuestion(q){
  setEditorBusy('q'+q.number);
  try{const r=await fetch(API+'/api/admin/test/question/update',{method:'POST',headers:{Authorization:'tma '+initData,'Content-Type':'application/json'},body:JSON.stringify({test_id:editingTest,number:q.number,question:q.question,options:q.options,answer:q.answer,kind:q.kind})});const j=await r.json();if(!j.ok)throw Error();setNote(j.message||'Savol saqlandi.');await loadQuestions(editingTest);await refresh(initData)}catch{setNote(q.number+'-savol saqlanmadi. Javobni tekshiring.')}finally{setEditorBusy('')}
 }
 async function loadFullResults(testId){
  setEditorBusy('results');setResultsTest(testId);setFullResults([]);
  try{const r=await fetch(API+'/api/admin/test/results?test_id='+encodeURIComponent(testId),{cache:'no-store',headers:{Authorization:'tma '+initData}});const j=await r.json();if(!j.ok)throw Error();setFullResults(j.results||[]);document.getElementById('results')?.scrollIntoView({behavior:'smooth',block:'start'})}catch{setNote('Natijalar yuklanmadi. Backendni tekshiring.');setResultsTest('')}finally{setEditorBusy('')}
 }
 async function setRankOverride(testId,username,rank){
  const clean=String(username||'').trim().replace(/^@/,'');
  if(!clean){setNote('Foydalanuvchining @username ini kiriting.');return}
  const verb=Number(rank)===0?'avtomatik reytingga qaytarish':Number(rank)+'-o‘ringa qo‘yish';
  if(!window.confirm('@'+clean+' uchun '+verb+'? Qo‘lda o‘zgartirilmagan o‘rinlar ball bo‘yicha avtomatik belgilanadi.'))return;
  setEditorBusy('rank');
  try{const r=await fetch(API+'/api/admin/test/top1',{method:'POST',headers:{Authorization:'tma '+initData,'Content-Type':'application/json'},body:JSON.stringify({test_id:testId,username:clean,rank:Number(rank)})});const j=await r.json();if(!j.ok)throw Error(j.error||'save_failed');setNote(j.message||'Reyting saqlandi.');await refresh(initData);if(resultsTest===testId)await loadFullResults(testId)}catch(e){setNote(e.message==='username_not_found'?'Bu @username hali bazada topilmadi. Foydalanuvchi Mini Appni kamida bir marta ochishi kerak.':'Reyting o‘zgartirilmadi. Qatnashchi testni yakunlaganini tekshiring.')}finally{setEditorBusy('')}
 }
 async function confirmJarvisAction(){if(!jarvisAction||!initData||busy==='jarvis-action')return;setBusy('jarvis-action');setJarvisError('');try{const response=await fetch(API+'/api/admin/jarvis/action',{method:'POST',cache:'no-store',headers:{Authorization:'tma '+initData,'Content-Type':'application/json'},body:JSON.stringify({action:jarvisAction})});const result=await response.json();if(!result.ok)throw new Error(result.error==='channels_missing'?'Avval majburiy obuna kanallarini sozlang.':result.error==='code_exists'?'Bu test kodi band. Boshqa kod tanlang.':result.error==='pdf_export_failed'?'PDF tayyorlanmadi yoki Telegramga yuborilmadi. Backend logini tekshirish kerak.':result.error==='question_save_failed'?'Savol bazaga saqlanmadi. Backend logini tekshirish kerak.':'Amal bajarilmadi. Ruxsat, kod va server holatini tekshiring.');setJarvisMessages(v=>[...v,{role:'assistant',content:'Bajarildi: '+result.message}]);setJarvisAction(null);await refresh(initData)}catch(e){setJarvisError(e.message||'Amalni bajarib bo‘lmadi.')}finally{setBusy('')}}
 async function sendJarvis(e){
  e.preventDefault();
  const prompt=jarvisDraft.trim();
  if(!prompt||jarvisBusy)return;
  if(!initData){setJarvisError('Telegram sessiyasi aniqlanmadi. Bu sahifani oddiy brauzerdan emas, Telegram botidagi “Jarvis” tugmasi orqali oching. Sahifani qayta ochib ham tekshiring.');return;}
  const next=[...jarvisMessages,{role:'user',content:prompt}];
  setJarvisMessages(next);setJarvisDraft('');setJarvisBusy(true);setJarvisError('');
  try{
   const requestBody=JSON.stringify({messages:next,context:{stats:data?.stats||{},tests:(data?.tests||[]).map(t=>({name:t.name,code:t.code,active:t.active,questions:t.questions,participants:t.participants,completed:t.completed}))}});
   let response=null,lastError=null;
   for(let attempt=0;attempt<2;attempt++){
    try{
     const controller=new AbortController();const timer=window.setTimeout(()=>controller.abort(),50000);
     try{response=await fetch(API+'/api/admin/jarvis',{method:'POST',cache:'no-store',signal:controller.signal,headers:{Authorization:'tma '+initData,'Content-Type':'application/json'},body:requestBody})}finally{window.clearTimeout(timer)}
     if(response.status>=500&&attempt===0){await new Promise(resolve=>window.setTimeout(resolve,700));continue}
     break;
    }catch(err){lastError=err;if(attempt===0){await new Promise(resolve=>window.setTimeout(resolve,700));continue}throw lastError}
   }
   if(!response)throw lastError||new Error('No response');
   const result=await response.json();
   if(!result.ok){
    const message=result.error==='api_key_missing'?'Jarvis API kaliti ulanmagan. MCWeb muhitiga OPENAI_API_KEY qo‘shing.':result.error==='api_key_invalid'?'OpenAI API kaliti noto‘g‘ri yoki bekor qilingan.':result.error==='api_quota_exceeded'?'OpenAI API krediti yoki foydalanish limiti tugagan. OpenAI platformasida Billing/Usage holatini tekshiring.':result.error==='api_permission_denied'?'OpenAI API kalitida ushbu model uchun ruxsat yo‘q. Kalit va loyiha ruxsatlarini tekshiring.':result.error==='api_request_invalid'?'OpenAI so‘rovi rad etildi. OPENAI_MODEL qiymatini va API sozlamasini tekshirish kerak.':result.error==='admin_only'?'Bu yordamchi faqat administrator uchun.':result.error==='empty_response'?'AI bo‘sh javob qaytardi. Qisqaroq savol bilan qayta urinib ko‘ring.':'Jarvis serverida xatolik yuz berdi. Birozdan keyin qayta urinib ko‘ring.';
    setJarvisError(message);return;
   }
   setJarvisMessages(v=>[...v,{role:'assistant',content:result.reply}]);setJarvisAction(result.action||null);
  }catch{setJarvisError('Jarvis serveriga ulanib bo‘lmadi. Internet va API sozlamalarini tekshiring.')}
  finally{setJarvisBusy(false)}
 }
 const resultTests=(data?.tests||[]).filter(t=>t.participants>0||(t.historical_completed||0)>0);
 return <main className="admin-shell"><header className="admin-header"><div><div className="admin-brand">A+</div><div><p>NUR O‘QIW ORAYI</p><h1>Admin boshqaruvi</h1></div></div><button className="admin-refresh" onClick={()=>initData&&refresh(initData)} disabled={loading||!initData}>Yangilash</button></header>
 <section className="admin-card admin-diagnostics"><div className="admin-section-title"><div><h2>Tizim diagnostikasi</h2><p>Admin sessiyasi, saqlash turi va zarur API sozlamalarining holati.</p></div><button className="admin-refresh" onClick={runDiagnostics} disabled={diagnosticsBusy||!initData}>{diagnosticsBusy?'Tekshirilmoqda…':'Tizimni tekshirish'}</button></div>{diagnostics?.ok?<><div className="admin-diagnostic-grid"><div><span>Backend</span><strong>Ulangan</strong></div><div><span>Admin sessiyasi</span><strong>{diagnostics.admin_authorized?'Tasdiqlangan':'Tasdiqlanmagan'}</strong></div><div><span>Ma’lumotlar bazasi</span><strong>{diagnostics.storage}</strong></div><div><span>Testlar / savollar</span><strong>{diagnostics.tests} / {diagnostics.questions}</strong></div><div><span>OpenAI kaliti</span><strong>{diagnostics.openai_key_configured?'Sozlangan':'Sozlanmagan'}</strong></div></div><p className="admin-muted">Bu tekshiruv kalitlarning mavjudligini ko‘rsatadi, ularning qiymatini ochmaydi va OpenAI balansini tasdiqlamaydi.</p></>:diagnostics&&!diagnostics.ok?<p className="admin-muted">{diagnostics.error==='admin_only'?'Telegram admin ID serverdagi ADMIN_CHAT_ID bilan mos kelmadi.':'Diagnostika API bilan bog‘lanib bo‘lmadi. Telegram sessiyasini va backendni tekshiring.'}</p>:<p className="admin-muted">“Tizimni tekshirish” tugmasi orqali admin ruxsati, backend, ma’lumotlar bazasi va API kalitlari holatini ko‘ring.</p>}</section>
 <div className="admin-menu-config-trigger"><button className="admin-primary" onClick={()=>setShowMenuEditor(v=>!v)}>{showMenuEditor?'Menyu sozlamalarini yopish':'Menyu sozlamalari'}</button><a className="admin-primary admin-results-jump" href="#results">Natijalar</a></div>
 {showMenuEditor&&<MenuEditor initData={initData}/>}
 {note&&<p className="admin-note">{note}</p>}
{error&&<section className="admin-error"><strong>{error}</strong><p>Admin paneliga faqat administratorning Telegram akkaunti orqali kirish mumkin.</p><button onClick={()=>window.location.reload()}>Qayta ulanish</button></section>}
 {loading&&!data?<section className="admin-card admin-skeleton" aria-hidden="true"></section>:null}
 {data&&<><section className="admin-stats">{[['Foydalanuvchilar',data.stats.users],['Testlar',data.stats.tests],['Urinishlar',data.stats.participants],['Yakunlangan',data.stats.completed]].map(([label,value])=><div className="admin-stat" key={label}><span>{label}</span><strong>{value}</strong></div>)}</section><details className="admin-details admin-user-directory"><summary>Ishtirokchilar — Telegram profilini ochish ({data.users?.length||0})</summary><p className="admin-muted">Faqat admin ko‘radi. Ism ustiga bosib foydalanuvchining Telegram profilini oching.</p><div className="admin-participants">{(data.users||[]).map(u=><div className="admin-participant" key={u.telegram_id}><div>{telegramProfileUrl(u)?<a className="admin-profile-link" href={telegramProfileUrl(u)} rel="noopener noreferrer">{u.full_name||'Ismsiz'}</a>:<strong>{u.full_name||'Ismsiz'}</strong>}<small>ID: {u.telegram_id}{u.username?' · @'+u.username:''}</small></div></div>)}</div></details>
 <section id="results" className="admin-card admin-results-section"><div className="admin-section-title"><div><h2>Natijalar</h2><p>Test yakunlanganda qatnashchilar, javoblar, to‘g‘ri javoblar va ballar shu yerda saqlanadi.</p></div><span>{resultTests.length} ta test</span></div>
 {resultTests.length===0?<p className="admin-muted">Hozircha natijasi bor test yo‘q.</p>:<div className="admin-result-tests">{resultTests.map(t=><article className="admin-result-test" key={t.test_id}><div><h3>{t.name}</h3><p>{t.is_mock?'MOCK test':'Test'} · {t.total_completed??t.completed} ta natija · {t.active?'Jarayonda':t.participants?'To‘xtatilgan':'Yakunlangan'}{t.is_mock?' · '+mockTimerLabel(t,mockClockNow):''}</p></div><div className="admin-result-actions"><button className="admin-primary" type="button" onClick={()=>loadFullResults(t.test_id)} disabled={editorBusy==='results'}>{editorBusy==='results'&&resultsTest===t.test_id?'Yuklanmoqda…':resultsTest===t.test_id?'Tanlandi':'Natijalarni ko‘rish'}</button>{t.is_mock&&(t.total_completed||t.completed)>0&&<button type="button" onClick={()=>sendMockPdf(t.test_id,'results')} disabled={mockBusy==='results-'+t.test_id}>{mockBusy==='results-'+t.test_id?'Yuborilmoqda…':'Natijalar PDF’ini olish'}</button>}{t.is_mock&&!t.timer_ends_at&&<button type="button" onClick={()=>startMock(t)} disabled={!!mockBusy}>{mockBusy==='start-'+t.test_id?'Boshlanmoqda…':'TESTNI BOSHLASH'}</button>}{t.is_mock&&t.timer_ends_at&&t.active&&(t.timer_remaining_seconds||0)>0&&<button type="button" onClick={()=>stopMock(t)} disabled={!!busy}>{busy===t.test_id?'To‘xtatilmoqda…':'TESTNI TO‘XTATISH'}</button>}{t.is_mock&&t.timer_ends_at&&(!t.active||(t.timer_remaining_seconds||0)<=0)&&<button type="button" onClick={()=>restartMock(t)} disabled={!!mockBusy}>{mockBusy==='restart-'+t.test_id?'Qayta ochilmoqda…':'Qayta o‘tkazish'}</button>}</div></article>)}</div>}
 {resultsTest&&<section className="admin-result-detail"><div className="admin-section-title"><div><h3>{data.tests.find(t=>t.test_id===resultsTest)?.name||'Test natijalari'}</h3><p>{fullResults.length} ta natija / urinish</p></div><button type="button" onClick={()=>{setResultsTest('');setFullResults([])}}>Yopish</button></div>{editorBusy==='results'?<p className="admin-muted">Natijalar yuklanmoqda…</p>:fullResults.length===0?<p className="admin-muted">Bu testda hali qatnashchi yo‘q.</p>:<div className="admin-result-table-wrap"><table className="admin-result-table"><thead><tr><th>№</th><th>Ism-familiya</th><th>To‘g‘ri</th><th>Ball</th><th>Baho</th><th>Holat</th><th>Tugagan vaqt</th><th>Javoblar</th></tr></thead><tbody>{fullResults.map((a,i)=><tr key={a.telegram_id+'-'+i}><td>{a.submitted?(a.rank||i+1):'—'}</td><td><strong>{a.full_name||'Ismsiz'}</strong></td><td>{a.correct_count??0}/{a.total_questions??0}</td><td>{a.submitted?(Number(a.score)||0).toFixed(2)+' ball':'—'}</td><td>{a.grade||'—'}</td><td><span className={'admin-result-status '+(a.submitted?'is-done':'is-running')}>{a.submitted?'Yakunlangan':'Jarayonda'}</span></td><td>{adminDateTime(a.finished_at||a.started_at)}</td><td><details className="admin-result-answers"><summary>Ko‘rish</summary><p>{adminAnswers(a.answers)}</p></details></td></tr>)}</tbody></table></div>}</section>}
 </section>
 <section className="admin-card admin-create-test"><div className="admin-section-title"><div><h2>Yangi oddiy test</h2><p>Pulli testlarni faqat Telegram botdagi «Pulli testlar» menyusida yarating va boshqaring.</p></div></div><form className="admin-create-form" onSubmit={createTest}><label>Test nomi<input value={newTestName} onChange={e=>setNewTestName(e.target.value)} placeholder="Masalan: Matematika — 1-variant" maxLength={120} required /></label><label>Kirish kodi<input value={newTestCode} onChange={e=>setNewTestCode(e.target.value.replace(/[^a-zA-Z0-9_-]/g,''))} placeholder="MAT2026" minLength={3} maxLength={40} required /></label><button className="admin-primary" type="submit" disabled={newTestBusy||!initData}>{newTestBusy?'Yaratilmoqda…':'Test yaratish'}</button></form></section>
 <div className="admin-section-title"><div><h2>Testlarni boshqarish</h2><p>Testni ochish/yopish, qatnashchilar va reyting.</p></div><span>{data.tests.length} ta</span></div>
 {!data.tests.some(t=>!t.paid&&!t.is_mock)&&<section className="admin-card">Hozircha test yo‘q. Yangi test yaratish uchun Telegram botidagi admin menyusidan foydalaning.</section>}
 <div className="admin-test-list">{data.tests.filter(t=>!t.paid&&!t.is_mock).map(t=><section className="admin-card admin-test-card" key={t.test_id}><div className="admin-test-top"><div><h3>{t.name}</h3><p>Kod: <b>{t.code}</b> · {t.questions} savol</p></div><span className={'admin-status '+(t.active?'is-active':'is-stopped')}>{t.active?'Faol':'To‘xtatilgan'}</span></div><div className="admin-test-stats"><span><b>{t.participants}</b> qatnashchi</span><span><b>{t.completed}</b> yakunlagan</span></div>
 <div className="admin-test-actions"><button className={"admin-primary "+(t.active?"action-danger":"action-success")} onClick={()=>toggle(t)} disabled={busy===t.test_id}>{busy===t.test_id?'Saqlanmoqda…':t.active?'Testni to‘xtatish':'Testni qayta ochish'}</button><a href={'/ranking?code='+encodeURIComponent(t.code)}>Reytingni ko‘rish</a><button onClick={()=>navigator.clipboard?.writeText(t.code)}>Kodni nusxalash</button></div>
 <div className="admin-test-actions"><button type="button" onClick={()=>loadQuestions(t.test_id)}>Savollar va to‘g‘ri javoblar</button><button type="button" onClick={()=>loadFullResults(t.test_id)}>Barcha natijalar</button></div>
 <form className="admin-rank-editor" onSubmit={e=>{e.preventDefault();setRankOverride(t.test_id,rankUsername,rankPosition)}}><strong>Reytingni @username orqali tahrirlash</strong><div><input value={rankUsername} onChange={e=>setRankUsername(e.target.value)} placeholder="@username" aria-label="Telegram username"/><select value={rankPosition} onChange={e=>setRankPosition(e.target.value)} aria-label="Reytingdagi o‘rin">{Array.from({length:15},(_,i)=><option key={i+1} value={i+1}>{i+1}-o‘rin</option>)}<option value="0">Avtomatik reyting</option></select><button type="submit" disabled={editorBusy==='rank'}>{editorBusy==='rank'?'Saqlanmoqda…':'Saqlash'}</button></div><small>Faqat belgilangan o‘rin qo‘lda boshqariladi. Qolganlari natija balli bo‘yicha avtomatik saralanadi.</small></form>
 {editingTest===t.test_id&&<section className="admin-details"><div className="admin-section-title"><h3>Savollar va javoblar</h3><button type="button" onClick={()=>setEditQuestions(old=>[...old,{number:Math.max(0,...old.map(q=>q.number))+1,question:'',options:['A','B','C','D'],answer:'A',kind:'choice',isNew:true}])}>+ Savol qo‘shish</button><button type="button" onClick={()=>setEditingTest("")}>Yopish</button></div>{editQuestions.map(q=><div className="admin-question-edit" key={q.number}><strong>{q.number}-savol</strong><label>Savol turi<select value={q.kind} onChange={e=>setEditQuestions(old=>old.map(x=>x.number===q.number?{...x,kind:e.target.value,options:e.target.value==='choice'?(x.options?.length===4?x.options:['A','B','C','D']):[],answer:e.target.value==='choice'?'A':x.answer}:x))}><option value="choice">Variantli A/B/C/D</option><option value="written">Yozma javob</option></select></label><label>Savol matni<textarea value={q.question} onChange={e=>setEditQuestions(old=>old.map(x=>x.number===q.number?{...x,question:e.target.value}:x))}/></label>{q.kind==="choice"&&<div>{(q.options||[]).map((v,i)=><label key={i}>{String.fromCharCode(65+i)} varianti<input value={v} onChange={e=>setEditQuestions(old=>old.map(x=>x.number===q.number?{...x,options:x.options.map((z,j)=>j===i?e.target.value:z)}:x))}/></label>)}</div>}<label>To‘g‘ri javob<input value={q.answer} onChange={e=>setEditQuestions(old=>old.map(x=>x.number===q.number?{...x,answer:e.target.value}:x))}/></label><button type="button" className="admin-primary" onClick={()=>saveQuestion(q)} disabled={editorBusy==="q"+q.number}>{editorBusy==="q"+q.number?"Saqlanmoqda…":"Savolni saqlash"}</button></div>)}</section>}
 <details className="admin-details"><summary>Ishtirokchilar va natijalar ({t.recent.length})</summary>{t.recent.length===0?<p className="admin-muted">Hali qatnashchilar yo‘q.</p>:<div className="admin-participants">{t.recent.map((a,i)=><div className="admin-participant" key={a.telegram_id+'-'+i}><div><strong>{a.full_name}</strong><small>Telegram ID: {a.telegram_id} · {a.submitted?'Yakunlangan':'Jarayonda'}</small></div><b>{a.submitted?a.score.toFixed(2)+' ball':'—'}</b></div>)}</div>}</details>
 {t.ranking.length>0&&<details className="admin-details"><summary>Top reyting ({t.ranking.length})</summary><div className="admin-participants">{t.ranking.map(a=><div className="admin-participant" key={a.rank}><div><strong>{a.rank}. {a.full_name}</strong><small>{a.grade||'Baho yo‘q'}</small></div><b>{a.score.toFixed(2)} ball</b></div>)}</div></details>}</section>)}</div></>}
 <nav className="bottom-glass-nav" aria-label="Asosiy navigatsiya">
 <a className="nav-item nav-tests" href="/"><TabIcon name="test"/><small>Test</small></a>
 <a className="nav-item nav-ranking" href="/ranking"><TabIcon name="ranking"/><small>Reyting</small></a>
 <a className="nav-item nav-admin active" href="/admin"><TabIcon name="admin"/><small>Admin</small></a>
 </nav>
 </main>
}
