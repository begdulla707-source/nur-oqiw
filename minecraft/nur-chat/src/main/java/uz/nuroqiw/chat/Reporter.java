package uz.nuroqiw.chat;

import com.google.gson.*;
import java.net.URI;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;

public final class Reporter {
    public static final String BASE = "https://nur-oqiw-bot.mcweb.uz/api/minecraft-chat";
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
    public static final class Config {
        public String deviceId = "", token = "", installedAt = Instant.now().toString();
        public String consentAt = "";
        public boolean enabled = false;
    }
    private final Path file, outbox;
    public final Config config;
    private final Deque<JsonObject> queue = new ArrayDeque<>();
    private final ScheduledExecutorService executor = Executors.newSingleThreadScheduledExecutor(r -> { Thread t = new Thread(r, "NurChat network"); t.setDaemon(true); return t; });
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(8)).followRedirects(HttpClient.Redirect.NEVER).build();
    public volatile String status = "O'chirilgan";
    private long retryAt = 0;
    private int failures = 0;
    public Reporter(Path directory) {
        file = directory.resolve("nur-chat.json"); outbox = directory.resolve("nur-chat-outbox.json");
        Config loaded;
        try { loaded = GSON.fromJson(Files.readString(file), Config.class); if (loaded == null) loaded = new Config(); }
        catch (Exception e) { loaded = new Config(); }
        config = loaded;
        if (config.token == null || config.deviceId == null || config.consentAt == null) { config.enabled = false; config.token = ""; config.deviceId = ""; config.consentAt = ""; }
        if (active()) {
            try { JsonArray arr = JsonParser.parseString(Files.readString(outbox)).getAsJsonArray(); for (JsonElement e : arr) if (queue.size() < 1000) queue.add(e.getAsJsonObject()); } catch (Exception ignored) {}
            status = "Ulangan";
        } else { try { Files.deleteIfExists(outbox); } catch (Exception ignored) {} }
        save(); // Keep the first launch date locally even before pairing.
        executor.scheduleWithFixedDelay(this::flush, 1, 1, TimeUnit.SECONDS);
    }
    public synchronized boolean active() { return config.enabled && !config.token.isBlank() && !config.consentAt.isBlank(); }
    public synchronized boolean paired() { return !config.token.isBlank(); }
    private void privateFile(Path p) { try { Files.setPosixFilePermissions(p, PosixFilePermissions.fromString("rw-------")); } catch (Exception ignored) {} }
    public synchronized void save() {
        try { Files.createDirectories(file.getParent()); Path temp=file.resolveSibling(file.getFileName()+".tmp"); Files.writeString(temp,GSON.toJson(config),StandardCharsets.UTF_8); privateFile(temp); Files.move(temp,file,StandardCopyOption.REPLACE_EXISTING); privateFile(file); }
        catch (Exception e) { status="Sozlamani saqlashda xato"; }
    }
    private synchronized void saveQueue() {
        try { if (queue.isEmpty()) { Files.deleteIfExists(outbox); return; } Files.writeString(outbox,GSON.toJson(queue),StandardCharsets.UTF_8); privateFile(outbox); } catch (Exception ignored) {}
    }
    public synchronized void pause() { config.enabled=false; queue.clear(); saveQueue(); save(); status="To'xtatilgan"; }
    public synchronized void enable() { if (!paired()) return; config.consentAt=Instant.now().toString(); config.enabled=true; save(); status="Ulangan"; }
    public CompletableFuture<String> pair(String code, String player) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                JsonObject body=new JsonObject(); body.addProperty("code",code.strip().toUpperCase(Locale.ROOT)); body.addProperty("player",player); body.addProperty("installed_at",config.installedAt); body.addProperty("consent",true);
                HttpRequest req=HttpRequest.newBuilder(URI.create(BASE+"/pair")).timeout(Duration.ofSeconds(12)).header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofString(body.toString())).build();
                HttpResponse<String> res=http.send(req,HttpResponse.BodyHandlers.ofString());
                if (res.statusCode()!=200) return "Kod xato yoki muddati tugagan. Botdan yangi kod oling.";
                JsonObject data=JsonParser.parseString(res.body()).getAsJsonObject();
                synchronized(this) { config.deviceId=data.get("device_id").getAsString(); config.token=data.get("token").getAsString(); config.consentAt=Instant.now().toString(); config.enabled=true; save(); status="Ulangan"; }
                return "OK";
            } catch (Exception e) { return "Botga ulanish bo'lmadi. Internetni tekshiring."; }
        },executor);
    }
    public synchronized void event(String kind,String player,String server,String session,String content) {
        if (!active() || server.isBlank()) return;
        if (queue.size() >= 1000) { config.enabled=false; status="Navbat to'ldi: F8 orqali qayta yoqing"; queue.clear(); saveQueue(); save(); return; }
        JsonObject e=new JsonObject(); e.addProperty("id",UUID.randomUUID().toString()); e.addProperty("kind",kind); e.addProperty("player",player); e.addProperty("server",server); e.addProperty("session",session); e.addProperty("at",Instant.now().toString()); e.addProperty("text",content); queue.addLast(e);
        saveQueue();
    }
    private void flush() {
        List<JsonObject> batch;
        synchronized(this) { if (!active() || queue.isEmpty() || System.currentTimeMillis()<retryAt) return; batch=queue.stream().limit(24).toList(); }
        try {
            JsonObject body=new JsonObject(); body.add("events",GSON.toJsonTree(batch));
            String token; synchronized(this) { token=config.token; }
            HttpRequest req=HttpRequest.newBuilder(URI.create(BASE+"/events")).timeout(Duration.ofSeconds(12)).header("Content-Type","application/json").header("Authorization","Bearer "+token).POST(HttpRequest.BodyPublishers.ofString(body.toString())).build();
            HttpResponse<String> res=http.send(req,HttpResponse.BodyHandlers.ofString());
            synchronized(this) {
                if (res.statusCode()==401 || res.statusCode()==403) { pause(); config.token=""; save(); status="Bot ulanishni bekor qildi"; return; }
                if (res.statusCode()!=200) throw new IllegalStateException("HTTP "+res.statusCode());
                for(JsonObject e:batch) queue.remove(e); saveQueue(); failures=0; retryAt=0; if(active()) status="Botga yuborilyapti";
            }
        } catch (Exception e) { synchronized(this) { failures++; retryAt=System.currentTimeMillis()+Math.min(60000L,2000L*(1L<<Math.min(failures,5))); if(active()) status="Internet kutilmoqda (navbat: "+queue.size()+")"; } }
    }
    public void close() { executor.shutdown(); }
}
