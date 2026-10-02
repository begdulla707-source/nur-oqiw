'use client';
import Link from 'next/link';
import {useEffect,useState} from 'react';
export default function Home(){const [ready,setReady]=useState(false);useEffect(()=>{const t=setTimeout(()=>setReady(true),80);return()=>clearTimeout(t)},[]);return <main className={`landing ${ready?'show':''}`}><section className="landing-card"><div className="brand-mark">N</div><small>NUR O‘QIW ORAYI</small><h1>Milliy sertifikat test tizimi</h1><p>Ro‘yxatdan o‘ting va belgilangan vaqtda testni boshlang.</p><Link className="primary-link" href="/test">Test sahifasini ochish</Link></section></main>}