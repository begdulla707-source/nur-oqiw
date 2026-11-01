'use client';
import {memo,useCallback,useEffect,useMemo,useRef,useState} from 'react';

const API=process.env.NEXT_PUBLIC_BACKEND_URL||'https://nur-oqiw-bot.mcweb.uz';

const MATH_KEYS={
 number:['7','8','9','÷','x','n','4','5','6','×','π','e','1','2','3','−','(',')','0','.','=','+','√','^'],
 symbols:['sin(','cos(','tan(','ln(','log(','abs(','∞','≠','≤','≥','∈','∉','∪','∩','∑','∫','√(','lim','→','⇔','∀','∃','°'],
 letters:['a','b','c','d','e','f','g','h','i','j','k','l','m','n','p','q','r','s','t','u','v','x','y','z'],
 greek:['α','β','γ','δ','ε','θ','λ','μ','π','ρ','σ','φ','ω','τ','η','ξ','Δ','Σ','Ω','ψ','χ','ν','ι','ζ'],
};
const MATH_TABS=[
 {key:'number',title:'123'},
 {key:'symbols',title:'∞≠∈'},
 {key:'letters',title:'abc'},
 {key:'greek',title:'αβγ'},
];
function MathIcon({name}){
 if(name==='keyboard')return <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="2.5" y="5" width="19" height="14" rx="2.5"/><path d="M6 9h.01M10 9h.01M14 9h.01M18 9h.01M6 12h.01M10 12h.01M14 12h.01M18 12h.01M7 16h10"/></svg>;
 if(name==='undo')return <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-2"/></svg>;
 if(name==='redo')return <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m15 14 5-5-5-5"/><path d="M20 9H10a6 6 0 0 0 0 12h2"/></svg>;
 if(name==='delete')return <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9 4H20a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H9L2 12Z"/><path d="m12 9 6 6m0-6-6 6"/></svg>;
 return null;
}
const Written=memo(function Written({questionId,answer,onSave}){
 const [value,setValue]=useState(String(answer??''));
 const [tab,setTab]=useState('number');
 const [nativeKeyboard,setNativeKeyboard]=useState(false);
 const [keyboardOpen,setKeyboardOpen]=useState(false);
 const rootRef=useRef(null);
 const [,setHistoryVersion]=useState(0);
 const valueRef=useRef(String(answer??''));
 const timer=useRef(null);
 const inputRef=useRef(null);
 const selection=useRef({start:String(answer??'').length,end:String(answer??'').length});
 const history=useRef({past:[],future:[]});
 const lastSent=useRef(String(answer??''));
 const flush=useCallback(()=>{
  if(timer.current)clearTimeout(timer.current);
  timer.current=null;
  const next=valueRef.current.trim();
  if(next===lastSent.current)return;
  lastSent.current=next;
  onSave(questionId,next);
 },[questionId,onSave]);
 useEffect(()=>{
  if(!keyboardOpen)return;
  const closeOutside=event=>{if(rootRef.current&&!rootRef.current.contains(event.target))setKeyboardOpen(false)};
  document.addEventListener('pointerdown',closeOutside,{passive:true});
  return()=>document.removeEventListener('pointerdown',closeOutside);
 },[keyboardOpen]);
 useEffect(()=>{
  const callback=()=>flush();
  window.addEventListener('nur-flush-test-answers',callback);
  return()=>{window.removeEventListener('nur-flush-test-answers',callback);if(timer.current)clearTimeout(timer.current)};
 },[flush]);
 const applyValue=(next,record=true)=>{
  if(next===valueRef.current)return;
  if(record){
   history.current.past.push(valueRef.current);
   if(history.current.past.length>40)history.current.past.shift();
   history.current.future=[];
  }
  valueRef.current=next;
  setValue(next);
  setHistoryVersion(n=>n+1);
  if(timer.current)clearTimeout(timer.current);
  timer.current=setTimeout(flush,500);
 };
 const insert=token=>{
  const {start,end}=selection.current;
  const from=Math.min(start,valueRef.current.length),to=Math.min(end,valueRef.current.length);
  const next=valueRef.current.slice(0,from)+token+valueRef.current.slice(to);
  selection.current={start:from+token.length,end:from+token.length};
  applyValue(next);
 };
 const removeLast=()=>{
  const {start,end}=selection.current;
  const from=Math.min(start,valueRef.current.length),to=Math.min(end,valueRef.current.length);
  if(!from&&!to)return;
  const left=start===end?Math.max(0,from-1):from;
  selection.current={start:left,end:left};
  applyValue(valueRef.current.slice(0,left)+valueRef.current.slice(to));
 };
 const undo=()=>{
  if(!history.current.past.length)return;
  history.current.future.push(valueRef.current);
  const old=history.current.past.pop();
  selection.current={start:old.length,end:old.length};
  applyValue(old,false);
 };
 const redo=()=>{
  if(!history.current.future.length)return;
  history.current.past.push(valueRef.current);
  const next=history.current.future.pop();
  selection.current={start:next.length,end:next.length};
  applyValue(next,false);
 };
 return <div className="written-answer" ref={rootRef}>
  <div className="written-input-wrap">
   <input ref={inputRef} value={value} inputMode={nativeKeyboard?'text':'none'} spellCheck={false} autoComplete="off"
     onChange={e=>{selection.current={start:e.target.selectionStart??e.target.value.length,end:e.target.selectionEnd??e.target.value.length};applyValue(e.target.value)}}
     onSelect={e=>{selection.current={start:e.currentTarget.selectionStart??valueRef.current.length,end:e.currentTarget.selectionEnd??valueRef.current.length}}}
     onFocus={()=>setKeyboardOpen(true)} onBlur={flush} className="answer-input" placeholder="Javobıńızdı kiritiń..." aria-label="Yozma javob"/>
   <button type="button" className="keyboard-switch" aria-label={nativeKeyboard?'Maxsus matematik klaviatura':'Telefon klaviaturasini yoqish'}
    onClick={()=>{setKeyboardOpen(true);setNativeKeyboard(v=>!v);inputRef.current?.focus()}}><MathIcon name="keyboard"/></button>
   <button type="button" className="clear-answer" aria-label="Javobni tozalash" onClick={()=>{selection.current={start:0,end:0};applyValue('')}} disabled={!value}><MathIcon name="delete"/></button>
  </div>
  {keyboardOpen&&<div className="written-keyboard" aria-label="Matematik klaviatura">
   <div className="keyboard-toolbar">
    <div className="keyboard-tabs" role="tablist" aria-label="Belgilar turi">{MATH_TABS.map(t=><button type="button" key={t.key} role="tab" aria-selected={tab===t.key} className={tab===t.key?'active':''} onClick={()=>setTab(t.key)}>{t.title}</button>)}</div>
    <div className="keyboard-history"><button type="button" onClick={undo} disabled={!history.current.past.length} aria-label="Ortga qaytarish"><MathIcon name="undo"/></button><button type="button" onClick={redo} disabled={!history.current.future.length} aria-label="Qayta tiklash"><MathIcon name="redo"/></button></div>
   </div>
   <div className={'keyboard-keys keyset-'+tab}>{MATH_KEYS[tab].map((token,index)=><button type="button" key={tab+'-'+index} onClick={()=>insert(token)}>{token}</button>)}</div>
   <div className="keyboard-footer"><span>{tab==='symbols'?'Trigonometrik va matematik belgilar':tab==='greek'?'Yunon harflari':tab==='letters'?'Lotin harflari':'Sonlar va amallar'}</span><div className="keyboard-footer-actions"><button type="button" onClick={removeLast} disabled={!value} aria-label="Oxirgi belgini o‘chirish"><MathIcon name="delete"/></button><button type="button" onClick={()=>{flush();setKeyboardOpen(false);inputRef.current?.blur()}} aria-label="Klaviaturani yopish"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button></div></div>
  </div>}
 </div>;
});
const Question=memo(function Question({q,number,answer,onChoose}){
 const opts=Array.isArray(q.options)&&q.options.length?q.options:['A','B','C','D'];
 const options=opts.map((o,i)=>({letter:String.fromCharCode(65+i),label:String(o??String.fromCharCode(65+i)).trim()}));
 const isPlain=options.every(o=>o.label.toUpperCase()===o.letter);
 const placeholder=/^\s*(?:\d+\s*[-.]?\s*)?(?:savol|савол|question)\s*$/iu.test(String(q.question??'').trim());
 const compact=q.kind!=='written'&&isPlain&&placeholder;
 return <article className={'question-card'+(compact?' compact-choice':'')+(q.kind==='written'?' written-question':'')+(options.length>4?' many-options':'')} id={'question-'+q.id}>
  <div className="question-heading"><span className="question-number">{/^[0-9]+$/.test(String(q.display_number||number))?String(q.display_number||number)+'.':String(q.display_number||number)}</span><div className={'question-text'+(compact?' sr-only':'')}>{q.question||'Savol'}</div></div>
  {q.image_url&&<img src={q.image_url} alt="Savol rasmi" className="question-image" loading="lazy"/>}
  {q.kind==='written'?<Written questionId={q.id} answer={answer} onSave={onChoose}/>:<div className={'option-list'+(!isPlain?' with-descriptions':'')}>{options.map(({letter,label})=>{const picked=answer===letter;return <button type="button" key={letter} aria-label={label===letter?letter:letter+': '+label} aria-pressed={picked} className={'option-choice'+(picked?' is-selected':'')} onClick={()=>onChoose(q.id,letter)}><span className="option-letter">{letter}</span>{label.toUpperCase()!==letter&&<span className="option-label">{label}</span>}</button>})}</div>}
 </article>;
});
export default function Test(){
 const answerQueue=useRef({});
 const [initData,setInitData]=useState('');
 const [questions,setQuestions]=useState([]);
 const [answers,setAnswers]=useState({});
 
 const [status,setStatus]=useState('loading');
 const [message,setMessage]=useState('');
 const [name,setName]=useState('');
 const [testName,setTestName]=useState('');
 const [code,setCode]=useState('');
 const [endsAt,setEndsAt]=useState(null);
 const [now,setNow]=useState(Date.now());
 const [score,setScore]=useState(null);
 const [grade,setGrade]=useState('');
 const [correctCount,setCorrectCount]=useState(null);
 const [totalQuestions,setTotalQuestions]=useState(null);
 const [finishBusy,setFinishBusy]=useState(false);
 const codeFromUrl=useMemo(()=>{try{return new URLSearchParams(window.location.search).get('code')||''}catch{return ''}},[]);
 const load=useCallback(async(raw)=>{
  if(!raw){setStatus('blocked');setMessage('Telegram boti ichidan oching.');return}
  try{
   const response=await fetch(API+'/api/test/state?code='+encodeURIComponent(codeFromUrl),{cache:'no-store',headers:{Authorization:'tma '+raw}});
   const data=await response.json();
   if(!data.ok){
    setStatus(data.error==='already_submitted'?'done':'blocked');
    setMessage(data.error==='test_stopped'?'Test administrator tomonidan to‘xtatildi.':data.error==='test_closed'?'Test hozir yopiq.':data.error==='subscription_required'?'Davom etish uchun botdagi majburiy kanallarga obuna bo‘ling.':data.error==='test_not_found'?'Test kodi topilmadi.':data.error==='registration_required'?'Avval botda ro‘yxatdan o‘ting.':data.error==='already_submitted'?'Bu test avval yakunlangan.':'Test ma’lumotlarini olish imkoni bo‘lmadi.');
    setScore(data.score??null);setGrade(data.grade||'');setCorrectCount(data.correct_count??null);setTotalQuestions(data.total_questions??null);setName(data.full_name||'');setTestName(data.test_name||'');return;
   }
   if(!Array.isArray(data.questions))throw new Error('questions_missing');
   setQuestions(data.questions);setAnswers(data.answers||{});setName(data.full_name||'');setTestName(data.test_name||'');setCode(data.test_code||codeFromUrl);setEndsAt(data.ends_at||null);setStatus('test');
  }catch{setStatus('blocked');setMessage('Ulanishda xatolik. Bir ozdan keyin qayta oching.')}
 },[codeFromUrl]);
 useEffect(()=>{
  let cancelled=false;let attempts=0;let timer;
  const boot=()=>{if(cancelled)return;const tg=window.Telegram?.WebApp;const raw=tg?.initData||'';if(tg&&raw){try{tg.ready();tg.expand();tg.disableVerticalSwipes?.()}catch{}setInitData(raw);load(raw);return}attempts++;if(attempts<12){timer=setTimeout(boot,100);return}setStatus('blocked');setMessage('Mini Appni Telegram botidagi Testni boshlash tugmasi orqali oching.')};
  boot();
  return()=>{cancelled=true;clearTimeout(timer)}
 },[load]);
 useEffect(()=>{if(!endsAt)return;const clock=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(clock)},[endsAt]);
 const choose=useCallback(async(id,value)=>{
  if(value===undefined||value===null)return;
  setAnswers(old=>old[id]===value?old:{...old,[id]:value});setMessage('');
  const previous=answerQueue.current[id]||Promise.resolve();
  const task=previous.catch(()=>{}).then(async()=>{
   const response=await fetch(API+'/api/test/answer',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'tma '+initData},body:JSON.stringify({initData,code:code||codeFromUrl,question_id:id,answer:value})});
   const data=await response.json();if(!data.ok)throw new Error(data.error||'save_failed');return data;
  });
  answerQueue.current[id]=task;
  try{await task}catch{setMessage('Javob saqlanmadi. Internetni tekshirib, qayta tanlang.')}finally{
   if(answerQueue.current[id]===task)delete answerQueue.current[id];
  }
 },[initData,code,codeFromUrl]);
 const finish=useCallback(async()=>{
  if(status!=='test'||finishBusy)return;
  setFinishBusy(true);
  try{
   window.dispatchEvent(new Event('nur-flush-test-answers'));
   await Promise.resolve();
   await Promise.all(Object.values(answerQueue.current).map(p=>p.catch(()=>{})));
   const response=await fetch(API+'/api/test/finish',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'tma '+initData},body:JSON.stringify({initData,code:code||codeFromUrl})});
   const data=await response.json();
   if(data.ok||data.error==='already_submitted'){setScore(data.score??null);setGrade(data.grade||'');setCorrectCount(data.correct_count??null);setTotalQuestions(data.total_questions??questions.length);setStatus('done');setMessage('Test yakunlandi. Natijangiz saqlandi.')}
   else setMessage(data.error==='test_stopped'?'Test administrator tomonidan to‘xtatildi.':'Testni yakunlab bo‘lmadi. Qayta urinib ko‘ring.');
  }catch{setMessage('Natijani saqlashda xatolik. Qayta urinib ko‘ring.')}finally{setFinishBusy(false)}
 },[status,finishBusy,initData,code,codeFromUrl,questions.length]);
 const seconds=endsAt?Math.max(0,Math.floor((new Date(endsAt).getTime()-now)/1000)):null;
 useEffect(()=>{if(status==='test'&&seconds===0&&endsAt)finish()},[status,seconds,endsAt,finish]);
 const answered=Object.keys(answers).filter(k=>String(answers[k]??'').trim()).length;
 if(status==='loading')return <main className="test-loading" aria-label="Test"><div className="loading-mark" role="status" aria-label="Test yuklanmoqda"></div></main>;
 if(status!=='test')return <main className="test-result-page"><section className="result-card"><h1>{status==='done'?'Test yakunlandi':'Test ochilmadi'}</h1>{testName&&<p className="result-subtitle">{testName}</p>}{name&&<p className="result-subtitle">{name}</p>}<p>{message}</p>{score!==null&&<div className="result-score">{Number(score).toFixed(2)} <small>ball</small></div>}{grade&&<p>Baho: <b>{grade}</b></p>}{correctCount!==null&&totalQuestions!==null&&<p>To‘g‘ri javoblar: {correctCount}/{totalQuestions}</p>}<a className="result-link" href="/">Asosiy sahifa</a></section></main>;
 return <main className="test-page">
  <header className="test-topbar"><div className="top-brand"><div><strong>Nur oqıw orayı</strong><small>{testName||'Milliy sertifikat testi'}</small></div></div><div className="top-progress"><b>{answered}/{questions.length}</b><small>javob</small></div></header>
  <div className="test-meta"><span>{questions.length} savol</span><span>{seconds===null?'Vaqt cheklanmagan':String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0')}</span></div>
  <section className="test-introduction"><h1>{testName||'Test'}</h1><p>Barcha savollar ketma-ket joylangan. Tanlagan javobingizni istalgan payt o‘zgartirishingiz mumkin.</p></section>
  {message&&<p className="test-alert" role="status">{message}</p>}
  <section className="question-stack">{questions.map((q,index)=><Question key={q.id} q={q} number={index+1} answer={answers[q.id]} onChoose={choose}/>)}</section>
  <footer className="test-finish-panel"><div><strong>{answered} / {questions.length}</strong><span>savolga javob berildi</span></div><button type="button" onClick={finish} disabled={finishBusy}>{finishBusy?'Saqlanmoqda...':'Testni yakunlash'}</button></footer>
 </main>
}
