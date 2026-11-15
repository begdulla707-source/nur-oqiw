package uz.nuroqiw.chat;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.loader.api.FabricLoader;
import net.fabricmc.fabric.api.client.message.v1.ClientSendMessageEvents;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayConnectionEvents;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.keybinding.v1.KeyBindingHelper;
import net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback;
import net.fabricmc.fabric.api.client.command.v2.ClientCommandRegistrationCallback;
import static net.fabricmc.fabric.api.client.command.v2.ClientCommandManager.literal;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.option.KeyBinding;
import net.minecraft.client.util.InputUtil;
import net.minecraft.text.Text;
import net.minecraft.text.ClickEvent;
import net.minecraft.util.Formatting;
import org.lwjgl.glfw.GLFW;
import java.util.UUID;

public final class NurChatClient implements ClientModInitializer {
    public static Reporter reporter;
    private static String session="", server="", player="";
    private static boolean pendingConsent=false;
    private static long heartbeat=0;
    private static boolean lastActive=false;
    @Override public void onInitializeClient() {
        reporter=new Reporter(FabricLoader.getInstance().getConfigDir());
        ClientCommandRegistrationCallback.EVENT.register((dispatcher,access) -> dispatcher.register(literal("nurchat")
            .then(literal("stop").executes(context -> { pause();return 1; }))
            .then(literal("settings").executes(context -> { var c=MinecraftClient.getInstance();c.execute(() -> c.setScreen(new NurChatScreen(c.currentScreen)));return 1; }))));
        KeyBinding key=KeyBindingHelper.registerKeyBinding(new KeyBinding("key.nurchat.settings",InputUtil.Type.KEYSYM,GLFW.GLFW_KEY_F8,"category.nurchat"));
        ClientPlayConnectionEvents.JOIN.register((handler,sender,client) -> {
            if (client.isInSingleplayer()) return;
            var entry=client.getCurrentServerEntry(); server=entry==null?"Realms":entry.address;
            player=client.getSession().getUsername(); session=UUID.randomUUID().toString(); heartbeat=System.currentTimeMillis();
            if (reporter.active()) { reporter.event("join",player,server,session,""); notifyPlayer("Nur Chat: chat va buyruqlaringiz Nur bot administratoriga yuborilyapti. F8 — to'xtatish."); }
            else { pendingConsent=true; notifyPlayer(reporter.consented()?"Nur Chat: bot holati avtomatik tekshirilmoqda.":"Nur Chat: bir martalik rozilik oynasi ochiladi. Keyingi kirishlar avtomatik."); }
            if(reporter.consented()) pendingConsent=false;
            lastActive=reporter.active();
        });
        ClientPlayConnectionEvents.DISCONNECT.register((handler,client) -> { if (!session.isBlank()) reporter.event("leave",player,server,session,""); server=""; session=""; pendingConsent=false; });
        ClientSendMessageEvents.CHAT.register(message -> log(message,false));
        ClientSendMessageEvents.COMMAND.register(command -> log(command,true));
        ClientTickEvents.END_CLIENT_TICK.register(client -> {
            boolean active=reporter.active();
            if(active && !lastActive && !session.isBlank()) { session=UUID.randomUUID().toString(); reporter.event("join",player,server,session,""); heartbeat=System.currentTimeMillis(); }
            lastActive=active;
            while(key.wasPressed()) client.setScreen(new NurChatScreen(client.currentScreen));
            if (pendingConsent && client.player!=null && client.currentScreen==null) { pendingConsent=false; client.setScreen(new NurChatScreen(null)); }
            if (reporter.active() && !session.isBlank() && System.currentTimeMillis()-heartbeat>45000) { heartbeat=System.currentTimeMillis(); reporter.event("heartbeat",player,server,session,""); }
        });
        HudRenderCallback.EVENT.register((ctx,tickCounter) -> {
            var client=MinecraftClient.getInstance(); if(client.player==null) return;
            String text="Nur Chat: "+reporter.status+" | F8 — sozlamalar";
            int width=client.textRenderer.getWidth(text); ctx.fill(5,5,width+13,19,0xB0101720); ctx.drawTextWithShadow(client.textRenderer,text,9,8,reporter.active()?0xFF5DE0A8:0xFFADB4C1);
        });
        Runtime.getRuntime().addShutdownHook(new Thread(() -> reporter.close(),"NurChat shutdown"));
    }
    static void notifyPlayer(String text) { var c=MinecraftClient.getInstance(); c.execute(() -> { if(c.player!=null) { var line=Text.literal(text);if(reporter.consented())line.append(Text.literal(" [To'xtatish]").styled(style -> style.withColor(Formatting.RED).withClickEvent(new ClickEvent(ClickEvent.Action.RUN_COMMAND,"/nurchat stop")))); c.player.sendMessage(line,false); } }); }
    private static void log(String raw,boolean command) { if(!reporter.active() || session.isBlank()) return; String text=Privacy.sanitize(raw,command); if(text!=null && !text.isBlank()) reporter.event(command?"command":"chat",player,server,session,text); }
    static void enabledHere() { if(reporter.active() && !session.isBlank()) { session=UUID.randomUUID().toString(); reporter.event("join",player,server,session,""); } lastActive=reporter.active(); notifyPlayer("Nur Chat ulandi. "+reporter.status+". Faol paytda chat va oddiy buyruqlar Nur bot administratoriga yuboriladi. F8 — to'xtatish."); }
    static void pause() { reporter.pause(); notifyPlayer("Nur Chat to'xtatildi. Yangi chat va buyruqlar yuborilmaydi."); }
}
