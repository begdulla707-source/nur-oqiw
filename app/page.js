'use client';
import {useState} from 'react';
import Link from 'next/link';
export default function Home(){
 const [code,setCode]=useState('');
 const start=(e)=>{e.preventDefault();const c=code.trim();if(c)window.location.href='/test?code='+encodeURIComponent(c);};
 return <main className="landing"><div className="landing-orb orb-one"/><div className="landing-orb orb-two"/>
  <section className="landing-card"><div className="brand-mark">N</div><p className="landing-eyebrow">NUR O‘QIW ORAYI</p>
   <h1>Milliy sertifikat<br/>test tizimi</h1><p className="landing-copy">Test kodingizni kiriting va bilim darajangizni sinab ko‘ring.</p>
   <form className="start-form" onSubmit={start}><label htmlFor="test-code">Test kodi</label><input id="test-code" value={code} onChange={e=>setCode(e.target.value)} placeholder="Masalan: MAT2026" autoCapitalize="characters" autoComplete="off"/>
    <button className="primary-link" type="submit" disabled={!code.trim()}>Testni boshlash <span>↗</span></button></form>
   <div className="landing-note"><span className="status-dot"/> Testlar kod orqali ochiladi</div></section>
  <nav className="bottom-glass-nav" aria-label="Asosiy navigatsiya"><Link className="nav-item active" href="/"><span>⌂</span><small>Test</small></Link><Link className="nav-item" href="/profile"><span>◉</span><small>Profil</small></Link><Link className="nav-item" href="/ranking"><span>♜</span><small>Reyting</small></Link></nav></main>;
}