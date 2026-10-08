import './style.css';
import Script from 'next/script';

export const metadata={
  title:'NUR O‘QIW ORAYI — Milliy sertifikat',
  description:'Milliy sertifikat mock test'
};

export default function RootLayout({children}){
  return <html lang="uz">
    <body>
      <Script
        src="https://telegram.org/js/telegram-web-app.js"
        strategy="beforeInteractive"
      />
      {children}
    </body>
  </html>
}