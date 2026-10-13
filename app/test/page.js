'use client';
import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {NUR_LOGO_DATA} from '../logo-data';

const API=process.env.NEXT_PUBLIC_BACKEND_URL||'https://nur-oqiw.onrender.com';
function Logo(){return <img src={NUR_LOGO_DATA} alt="Nur oqıw orayı" className="brand-logo-image"/>}

function Written({questionId,answer,onSave}){
 const [value,setValue]=useState(answer??'');
 const [tab,setTab]=useState('number');
 const timer=useRef(null);
 useEffect(()=>setValue(answer??''),[questionId,answer]);
 useEffect(()=>()=>{if(timer.current)clearTimeout(timer.current)},[]);
 const keyRows={
  symbols:['x','y','π','√','(',')','^','²','³','+','−','×','÷','=','<','>','/'],
  number:['1','2','3','4','5','6','7','8','9','0','.','−','+','=','(',')','/']
 };
 const updateValue=(next)=>{
  setValue(next);
  if(timer.current)clearTimeout(timer.current);
  timer.current=setTimeout(()=>onSave(questionId,next.trim()),450);
 };
 const insert=(k)=>updateValue(value+k);
 return <div className="written-answer">
  <div className="written-input-wrap"><input value={value} onChange={e=>updateValue(e.target.value)} className="answer-input" placeholder="Javobıńızdı kiritiń..." aria-label="Yozma javob"/><button type="button" className="clear-answer" onClick={()=>updateValue('')} disabled={!value}>×</button></div>
  <div className="written-keyboard">
   <div className="keyboard-tabs"><button type="button" className={tab==='number'?'active':''} onClick={()=>setTab('number')}>Raqamlar</button><button type="button" className={tab==='symbols'?'active':''} onClick={()=>setTab('symbols')}>Belgilar</button></div>
   <div className="keyboard-keys">{keyRows[tab].map((k,i)=><button type="button" key={k+'-'+i} onClick={()=>insert(k)}>{k}</button>)}<button type="button" onClick={()=>updateValue(value.slice(0,-1))} disabled={!value}>⌫</button></div>
  </div>
 </div>
}
function Question({q,number,answer,onChoose}){
 const opts=Array.isArray(q.options)&&q.options.length?q.options:['A','B','C','D'];
 return <article className="question-card" id={'question-'+q.id}>
  <div className="question-heading"><span className="question-number">{number}.</span><div className="question-text">{q.question||'Savol'}</div></div>
  {q.image_url&&<img src={q.image_url} alt="Savol rasmi" className="question-image" loading="lazy"/>}
  {q.kind==='written'?<Written questionId={q.id} answer={answer} onSave={onChoose}/>:<div className="option-list">{opts.map((option,i)=>{const letter=String.fromCharCode(65+i);const picked=answer===letter;return <button type="button" key={letter} aria-pressed={picked} className={'option-choice'+(picked?' is-selected':'')} onClick={()=>onChoose(q.id,letter)}><span className="option-letter">{letter}</span><span className="option-label">{String(option??letter)}</span></button>})}</div>}
 </article>
}
export default function Test(){
 const answerQueue=useRef({});
 const [initData,setInitData]=useState('');
 const [questions,setQuestions]=useState([]);
 const [answers,setAnswers]=useState({});
 const [saving,setSaving]=useState({});
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
    setMessage(data.error==='test_stopped'?'Test administrator tomonidan to‘xtatildi.':data.error==='test_closed'?'Test hozir yopiq.':data.error==='test_not_found'?'Test kodi topilmadi.':data.error==='registration_required'?'Avval botda ro‘yxatdan o‘ting.':data.error==='already_submitted'?'Bu test avval yakunlangan.':'Test ma’lumotlarini olish imkoni bo‘lmadi.');
    setScore(data.score??null);setGrade(data.grade||'');setCorrectCount(data.correct_count??null);setTotalQuestions(data.total_questions??null);setName(data.full_name||'');setTestName(data.test_name||'');return;
   }
   if(!Array.isArray(data.questions))throw new Error('questions_missing');
   setQuestions(data.questions);setAnswers(data.answers||{});setName(data.full_name||'');setTestName(data.test_name||'');setCode(data.test_code||codeFromUrl);setEndsAt(data.ends_at||null);setStatus('test');
  }catch{setStatus('blocked');setMessage('Ulanishda xatolik. Bir ozdan keyin qayta oching.')}
 },[codeFromUrl]);
 useEffect(()=>{
  let cancelled=false;let attempts=0;let timer;
  const boot=()=>{if(cancelled)return;const tg=window.Telegram?.WebApp;const raw=tg?.initData||'';if(tg&&raw){try{tg.ready();tg.expand();tg.disableVerticalSwipes?.()}catch{}setInitData(raw);load(raw);return}attempts++;if(attempts<12){timer=setTimeout(boot,100);return}setStatus('blocked');setMessage('Mini Appni Telegram botidagi Testni boshlash tugmasi orqali oching.')};
  boot();const clock=setInterval(()=>setNow(Date.now()),1000);
  return()=>{cancelled=true;clearTimeout(timer);clearInterval(clock)}
 },[load]);
 const choose=useCallback(async(id,value)=>{
  if(value===undefined||value===null)return;
  setAnswers(old=>({...old,[id]:value}));setSaving(old=>({...old,[id]:true}));setMessage('');
  const previous=answerQueue.current[id]||Promise.resolve();
  const task=previous.catch(()=>{}).then(async()=>{
   const response=await fetch(API+'/api/test/answer',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'tma '+initData},body:JSON.stringify({initData,code:code||codeFromUrl,question_id:id,answer:value})});
   const data=await response.json();if(!data.ok)throw new Error(data.error||'save_failed');return data;
  });
  answerQueue.current[id]=task;
  try{await task}catch{setMessage('Javob saqlanmadi. Internetni tekshirib, qayta tanlang.')}finally{
   if(answerQueue.current[id]===task){delete answerQueue.current[id];setSaving(old=>{const next={...old};delete next[id];return next})}
  }
 },[initData,code,codeFromUrl]);
 const finish=useCallback(async()=>{
  if(status!=='test'||finishBusy)return;
  setFinishBusy(true);
  try{
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
 if(status==='loading')return <main className="test-loading" aria-label="Test"><div className="loading-mark"><Logo/></div></main>;
 if(status!=='test')return <main className="test-result-page"><section className="result-card"><Logo/><h1>{status==='done'?'Test yakunlandi':'Test ochilmadi'}</h1>{testName&&<p className="result-subtitle">{testName}</p>}{name&&<p className="result-subtitle">{name}</p>}<p>{message}</p>{score!==null&&<div className="result-score">{Number(score).toFixed(2)} <small>ball</small></div>}{grade&&<p>Baho: <b>{grade}</b></p>}{correctCount!==null&&totalQuestions!==null&&<p>To‘g‘ri javoblar: {correctCount}/{totalQuestions}</p>}<a className="result-link" href="/">Asosiy sahifa</a></section></main>;
 return <main className="test-page">
  <header className="test-topbar"><div className="top-brand"><Logo/><div><strong>Nur oqıw orayı</strong><small>{testName||'Milliy sertifikat testi'}</small></div></div><div className="top-progress"><b>{answered}/{questions.length}</b><small>javob</small></div></header>
  <div className="test-meta"><span>{questions.length} savol</span><span>{seconds===null?'Vaqt cheklanmagan':String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0')}</span></div>
  <section className="test-introduction"><h1>{testName||'Test'}</h1><p>Barcha savollar ketma-ket joylangan. Tanlagan javobingizni istalgan payt o‘zgartirishingiz mumkin.</p></section>
  {message&&<p className="test-alert" role="status">{message}</p>}
  <section className="question-stack">{questions.map((q,index)=><Question key={q.id} q={q} number={index+1} answer={answers[q.id]} onChoose={choose} saving={saving}/>)}</section>
  <footer className="test-finish-panel"><div><strong>{answered} / {questions.length}</strong><span>savolga javob berildi</span></div><button type="button" onClick={finish} disabled={finishBusy}>{finishBusy?'Saqlanmoqda...':'Testni yakunlash'}</button></footer>
 </main>
}
