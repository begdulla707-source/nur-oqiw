package uz.nuroqiw.chat;

import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.Screen;
import net.minecraft.client.gui.screen.ConfirmScreen;
import net.minecraft.client.gui.widget.ButtonWidget;
import net.minecraft.client.gui.widget.TextFieldWidget;
import net.minecraft.text.Text;

public final class NurChatScreen extends Screen {
    private final Screen parent;
    private TextFieldWidget code;
    private String message="";
    private boolean pairing=false;
    public NurChatScreen(Screen parent) { super(Text.literal("Nur Chat — chat sozlamalari")); this.parent=parent; }
    @Override protected void init() {
        int x=width/2-150, y=height/2-10;
        code=new TextFieldWidget(textRenderer,x,y,300,20,Text.literal("Botdan olingan ulash kodi")); code.setMaxLength(10); code.setPlaceholder(Text.literal("Botdagi 10 belgili ulash kodi")); addDrawableChild(code);
        addDrawableChild(ButtonWidget.builder(Text.literal(NurChatClient.reporter.paired()?"Rozilik berish va yoqish":"Ulash va rozilik berish"),button -> {
            if(pairing) return;
            client.setScreen(new ConfirmScreen(accepted -> {
                if(!accepted) { client.setScreen(this); return; }
                if(NurChatClient.reporter.paired()) { NurChatClient.reporter.enable(); NurChatClient.enabledHere(); close(); return; }
                String value=code.getText().strip();
                if(value.length()!=10) { message="Nur botdan 10 belgili kod oling."; client.setScreen(this); return; }
                pairing=true; message="Botga ulanmoqda..."; client.setScreen(this);
                NurChatClient.reporter.pair(value,client.getSession().getUsername()).thenAccept(result -> client.execute(() -> { pairing=false; message=result; if(result.equals("OK")) { NurChatClient.enabledHere(); close(); } }));
            },Text.literal("Chat hisoboti uchun rozilik"),Text.literal("O'yin nomingiz, server manzili, kirish/chiqish vaqti, siz yuborgan chat va buyruqlar Nur Telegram botining administratoriga yuboriladi. /login va /register kabi maxfiy buyruqlar olinmaydi. F8 orqali istalgan payt to'xtatasiz. Rozimisiz?"),Text.literal("Ha, roziman"),Text.literal("Bekor qilish")));
        }).dimensions(x,y+28,300,20).build());
        addDrawableChild(ButtonWidget.builder(Text.literal("Hisobotni to'xtatish"),b -> { NurChatClient.pause(); message="To'xtatildi. Yangi xabarlar yuborilmaydi."; }).dimensions(x,y+55,300,20).build());
        addDrawableChild(ButtonWidget.builder(Text.literal("Yopish"),b -> close()).dimensions(x,y+82,300,20).build());
    }
    @Override public void render(DrawContext ctx,int mouseX,int mouseY,float delta) {
        renderBackground(ctx,mouseX,mouseY,delta); super.render(ctx,mouseX,mouseY,delta);
        int y=height/2-100;
        ctx.drawCenteredTextWithShadow(textRenderer,title,width/2,y,0xFFFFFF);
        ctx.drawCenteredTextWithShadow(textRenderer,"Qabul qiluvchi: Nur bot administratori",width/2,y+22,0x5DE0A8);
        ctx.drawCenteredTextWithShadow(textRenderer,"O'zingiz yuborgan chat / buyruqlar va server tarixi.",width/2,y+40,0xCDD4E0);
        ctx.drawCenteredTextWithShadow(textRenderer,"Faqat rozilikdan keyin. F8 — sozlash / to'xtatish.",width/2,y+56,0xCDD4E0);
        ctx.drawCenteredTextWithShadow(textRenderer,"Holat: "+NurChatClient.reporter.status,width/2,y+72,0xADB4C1);
        if(!message.isBlank()) ctx.drawCenteredTextWithShadow(textRenderer,message,width/2,height/2+112,0xFFD080);
    }
    @Override public void close() { client.setScreen(parent); }
    @Override public boolean shouldPause() { return false; }
}
