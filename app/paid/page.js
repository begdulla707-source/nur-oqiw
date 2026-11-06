'use client';
import {useEffect,useState} from 'react';
import Link from 'next/link';
import TabIcon from '../ui-icons';
const API=process.env.NEXT_PUBLIC_BACKEND_URL||'https://nur-oqiw-bot.mcweb.uz';
export default function PaidTests(){
 const [tests,setTests]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(true),[retry,setRetry]=useState(0);
 useEffect(()=>{
  let stopped=false;let ticker,attempts=0;let controller=new AbortController();
  const boot=async()=>{
   if(stopped)return;
   const raw=window.Telegram?.WebApp?.initData||'';
   if(!raw){
    if(attempts++<32){ticker=setTimeout(boot,120);return;}
    setError('Mini Appni Telegram botidagi «Pulli testlar» bo‘limidan oching.');setLoading(false);return;
   }
   try{
    window.Telegram?.WebApp?.ready?.();
    const timer=setTimeout(()=>controller.abort(),9000);
    try{
     const r=await fetch(API+'/api/test/paid',{cache:'no-store',signal:controller.signal,headers:{Authorization:'tma '+raw}});
     const j=await r.json();
     if(!j.ok)throw Error(j.error==='not_authorized'?'Botga /start bosing va qaytadan oching.':'Pulli testlar yuklanmadi.');
     if(!stopped)setTests(j.tests||[]);
    }finally{clearTimeout(timer)}
   }catch(e){if(!stopped)setError(e.name==='AbortError'?'Server javobi kechikyapti. Qayta urinib ko‘ring.':e.message)}
   finally{if(!stopped)setLoading(false)}
  };
  boot();
  return()=>{stopped=true;clearTimeout(ticker);controller.abort()};
 },[retry]);
 return <main className="paid-page"><section className="paid-card"><span className="paid-eyebrow">NUR O‘QIW ORAYI</span><h1>Pulli testlar</h1><p className="paid-intro">Bu yerda faqat administrator tasdiqlagan testlaringiz ko‘rinadi. Kirish huquqi Telegram chat ID’ingizga bog‘langan.</p>
  {loading?<p className="paid-state" role="status">Ruxsatli testlar yuklanmoqda…</p>:error?<div className="paid-state" role="alert"><p>{error}</p><button onClick={()=>{setLoading(true);setError('');setRetry(n=>n+1)}}>Qayta tekshirish</button></div>:tests?.length?<div className="paid-tests-list">{tests.map(t=><Link href={'/test?code='+encodeURIComponent(t.code)} className="paid-test-item" key={t.test_id}><span><strong>{t.name}</strong><small>Kod: {t.code} · {t.questions} savol</small></span><TabIcon name="arrow-right" size={20}/></Link>)}</div>:<p className="paid-state">Hozircha sizga pulli testga ruxsat berilmagan. Testni sotib olganingizdan so‘ng admin chat ID’ingiz orqali kirishni tasdiqlaydi.</p>}
  <a className="paid-contact" href="https://t.me/up17b">Sotib olish uchun @up17b ga yozish</a>
  <p className="paid-footnote">To‘lovni admin bilan kelishasiz. Testga kirish faqat tasdiqdan keyin ochiladi.</p>
 </section>
 <nav className="bottom-glass-nav" aria-label="Asosiy navigatsiya">
 <Link href="/" className="nav-item nav-tests"><TabIcon name="test"/><small>Test</small></Link>
 <Link href="/profile" className="nav-item nav-profile"><TabIcon name="profile"/><small>Profil</small></Link>
 <Link href="/?view=ranking" className="nav-item nav-ranking"><TabIcon name="ranking"/><small>Reyting</small></Link>
 </nav></main>;
}
