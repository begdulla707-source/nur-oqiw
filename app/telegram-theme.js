'use client';
import {useEffect} from 'react';
export default function TelegramThemeSync(){
 useEffect(()=>{
  let cancelled=false,attempts=0,handle;
  function apply(){
   if(cancelled)return;
   const tg=window.Telegram?.WebApp;
   if(!tg){if(attempts++<14)handle=setTimeout(apply,100);return}
   try{
    tg.setHeaderColor?.('#151f2b');
    tg.setBackgroundColor?.('#070b14');
    tg.setBottomBarColor?.('#0a101c');
    tg.ready?.();
   }catch{/* older Telegram clients keep their built-in colors */}
  }
  apply();
  return()=>{cancelled=true;clearTimeout(handle)};
 },[]);
 return null;
}
