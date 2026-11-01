import {NextResponse} from 'next/server';
export const runtime='nodejs';
export const dynamic='force-dynamic';
const BACKEND='https://nur-oqiw-bot.mcweb.uz/telegram/webhook';
export async function GET(){
  return NextResponse.json({ok:true,relay:'telegram-webhook',backend:'mcweb'});
}
export async function POST(request){
  const secret=request.headers.get('x-telegram-bot-api-secret-token');
  if(!secret)return NextResponse.json({ok:false},{status:403});
  try{
    const body=await request.arrayBuffer();
    const response=await fetch(BACKEND,{
      method:'POST',
      headers:{
        'Content-Type':'application/json',
        'X-Telegram-Bot-Api-Secret-Token':secret
      },
      body,
      cache:'no-store',
      signal:AbortSignal.timeout(8500)
    });
    return new Response(await response.text(),{
      status:response.status,
      headers:{'Content-Type':'application/json','Cache-Control':'no-store'}
    });
  }catch{
    return NextResponse.json({ok:false,error:'backend_unavailable'},{status:503});
  }
}
