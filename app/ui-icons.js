// Crisp outline icons for the compact Telegram Mini App navigation.
export default function TabIcon({name,size=23}){
 const common={width:size,height:size,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth:2.15,strokeLinecap:'round',strokeLinejoin:'round','aria-hidden':true};
 if(name==='test')return <svg {...common}><rect x="5.2" y="3" width="13.6" height="18" rx="2.8"/><path d="M8.7 8h6.6M8.7 12.3h6.6M8.7 16.6h3.9"/></svg>;
 if(name==='profile')return <svg {...common}><circle cx="12" cy="8" r="3.5"/><path d="M4.3 20c.2-4 3-6.2 7.7-6.2s7.5 2.2 7.7 6.2"/></svg>;
 if(name==='ranking')return <svg {...common}><path d="M4 19.7v-7.4h4.3v7.4M10 19.7V5.5h4.3v14.2M16 19.7v-10h4.3v10M3.2 20.3h17.6"/></svg>;
 if(name==='admin')return <svg {...common}><path d="M4 6h16M4 12h16M4 18h16"/><circle cx="9" cy="6" r="2.1" fill="#0a101c"/><circle cx="16" cy="12" r="2.1" fill="#0a101c"/><circle cx="10.5" cy="18" r="2.1" fill="#0a101c"/></svg>;
 if(name==='arrow-right')return <svg {...common} strokeWidth="2.7"><path d="M3 12h17M13 5l7 7-7 7"/></svg>;
 return null;
}
