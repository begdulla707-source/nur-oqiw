'use client';
import TabIcon from '../ui-icons';
import {useEffect,useState} from 'react';
const API=process.env.NEXT_PUBLIC_BACKEND_URL||'https://nur-oqiw-bot.mcweb.uz';
export default function ProfilePage(){
 const [data,setData]=useState(null),[error,setError]=useState(''),[publicProfile,setPublicProfile]=useState(false),[loading,setLoading]=useState(true),[retry,setRetry]=useState(0);
 useEffect(()=>{
  let stopped=false,waitTimer=null,timeout=null,tries=0;
  const controller=new AbortController();
  const boot=async()=>{
   if(stopped)return;
   const raw=window.Telegram?.WebApp?.initData||'';
   if(!raw){
    if(tries++<35){waitTimer=setTimeout(boot,120);return;}
    setError('Telegram sessiyasi olinmadi. Profilni botning Mini App tugmasidan qayta oching.');setLoading(false);return;
   }
   try{
    window.Telegram?.WebApp?.ready?.();
    const target=new URLSearchParams(window.location.search).get('telegram_id')||'';
    setPublicProfile(Boolean(target));
    timeout=setTimeout(()=>controller.abort(),9500);
    const url=target?API+'/api/test/public-profile?telegram_id='+encodeURIComponent(target):API+'/api/test/profile';
    const r=await fetch(url,{cache:'no-store',signal:controller.signal,headers:{Authorization:'tma '+raw}});
    const j=await r.json();
    if(!j.ok)throw Error(j.error==='not_authorized'?'Avval botda /start bosing.':'Profil ma’lumotlari yuklanmadi.');
    if(!stopped)setData(j);
   }catch(e){if(!stopped)setError(e.name==='AbortError'?'Server javobi kechikyapti. Qayta urining.':e.message||'Internet aloqasini tekshiring.')}
   finally{clearTimeout(timeout);if(!stopped)setLoading(false)}
  };
  boot();
  return()=>{stopped=true;clearTimeout(waitTimer);clearTimeout(timeout);controller.abort()};
 },[retry]);
 const again=()=>{setError('');setLoading(true);setRetry(v=>v+1)};
 const tests=Array.isArray(data?.tests)?data.tests:[];
 return <main className="profile-shell" aria-label="Profil"><div className="profile-wrap">
  {loading&&!data?<section className="profile-card profile-loading-card" role="status"><h2>Profil yuklanmoqda…</h2><p>Ma’lumotlar serverdan olinmoqda.</p><button type="button" onClick={again}>Qayta urinish</button></section>:error&&!data?<section className="profile-card profile-loading-card" role="alert"><h2>Profil ochilmadi</h2><p>{error}</p><button type="button" onClick={again}>Qayta urinish</button></section>:data&&<>
   <section className="profile-card"><div className="profile-hero">{data.photo_url?<img className="profile-avatar" src={data.photo_url} alt="Profil rasmi" loading="lazy"/>:<div className="profile-avatar"/>}<div><h1>{data.full_name||'Foydalanuvchi'}</h1><p>{publicProfile?'Qatnashchi profili':'Shaxsiy profil'}</p>{data.username&&<p className="profile-username">@{data.username}</p>}</div></div></section>
   <section className="profile-card"><div className="profile-section-head"><h2>{publicProfile?'Test natijalari':'Testlarim'}</h2></div>{tests.length?tests.map((t,i)=><div className="history-row" key={t.test_id+'-'+i}><div className="history-main"><strong>{t.test_name}</strong><small>Kod: {t.code||'—'} · {t.submitted?'Yakunlangan':'Jarayonda'}</small></div><div className="history-score">{t.submitted?Number(t.score||0).toFixed(2)+'%':'—'}</div></div>):<p className="profile-muted">Hozircha test natijasi yo‘q.</p>}</section>
  </>}
 </div><nav className="bottom-glass-nav" aria-label="Asosiy navigatsiya">
 <a className="nav-item nav-tests" href="/"><TabIcon name="test"/><small>Test</small></a>
 <a className="nav-item nav-profile active" href="/profile"><TabIcon name="profile"/><small>Profil</small></a>
 <a className="nav-item nav-ranking" href={tests[0]?.code?'/?view=ranking&code='+encodeURIComponent(tests[0].code):'/?view=ranking'}><TabIcon name="ranking"/><small>Reyting</small></a>
 </nav></main>;
}
