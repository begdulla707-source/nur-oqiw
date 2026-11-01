import './style.css';
import './navy.css';
import Script from 'next/script';
import TelegramThemeSync from './telegram-theme';

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
      <TelegramThemeSync/>
      {children}
    </body>
  </html>
}