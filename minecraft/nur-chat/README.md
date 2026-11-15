# Nur Chat — Minecraft 1.21.1 / Fabric

O‘yinchi roziligi bilan o‘zining yuborgan chatlari, oddiy buyruqlari, server
manzili va kirish/chiqish vaqtini Nur Telegram botining administratoriga yuboradi.
Fabric API tayyor jar ichiga qo‘shilgan. Java 21 va Fabric Loader 0.16.14 yoki
yangirog‘i kerak. Minecraft versiyasi aynan 1.21.1.

## O‘rnatish va ulash

1. `NurChat-1.21.1.jar` faylini Minecraft `mods` papkasiga qo‘ying.
2. Nur botida **Admin → Chat sozlamalari → Modni ulash kodi** ni bosing.
3. Minecraft ichida **F8** ni bosing. Kodni kiriting, **Ulash va rozilik berish**
   tugmasini bosing va kimga nimalar yuborilishini o‘qib tasdiqlang.
4. Serverga kirgandan keyin botga o‘yinchi, server manzili va vaqt yuboriladi.
   O‘yinchining yangi chatlari va maxfiy bo‘lmagan buyruqlari keyingi xabarlarda
   keladi. F8 orqali to‘xtatish mumkin. Faol holat ekranda doim ko‘rsatiladi.

Bot tokenini jar yoki konfiguratsiyaga kiritish kerak emas. Qurilmaning alohida
ulanish kaliti Minecraft `config/nur-chat.json` faylida saqlanadi. Bu faylni
tarqatmang. Admin botdan qurilmani uzishi mumkin; qayta ulash uchun yangi kod va
o‘yinchining qayta roziligi kerak bo‘ladi.

## Nimalar olinmaydi

- Mod o‘rnatilishidan yoki rozilik berilishidan oldingi tarix.
- Boshqa o‘yinchilarning yozishmalari va klaviaturada terilib, yuborilmagan matn.
- `/login`, `/register`, `/changepassword`, OTP va hisobni ulashga oid buyruqlar.
- Aniqlanadigan parol/token yozuvlari matndan yashiriladi.
- Singleplayer dunyolari qayd etilmaydi.

`/promo`, `/ban`, `/mute` kabi maxfiy bo‘lmagan buyruqlar qayd etiladi. Ma’lumot
uzatish HTTPS orqali o‘yin oqimidan alohida bajariladi. Internet bo‘lmasa, eng
ko‘pi 1000 ta hodisa vaqtincha navbatda saqlanadi. Navbat to‘lsa hisobot to‘xtaydi
va F8 orqali qayta yoqish talab etiladi; cheksiz tarix va uzluksiz tarmoq va’da
qilinmaydi. O‘yinchi to‘xtatganda yuborilmagan navbat o‘chiriladi.

Jar ichidagi Minecraft/Fabric API ilgaklari odatiy chat va buyruq yuborish
hodisalarini qayd etadi; boshqa modlar yozishmalarni boshqacha yo‘l bilan
yuborsa, ularning maxsus xatti-harakati alohida sinov talab qiladi.

## Yig‘ish

JDK 21 va Gradle 8.10.2 bilan `gradle build`.
`build/libs/NurChat-1.21.1-1.0.0.jar` — tarqatiladigan mod.

## Tekshirish

`PrivacyTest` mustaqil Java tekshiruvi; botning API, rozilik, avtorizatsiya,
takror so‘rovlar, maxfiy ma’lumotlarni yashirish, tarix va xabar yuborish
tekshiruvlari `tests/test_minecraft_chat.py` faylida.
