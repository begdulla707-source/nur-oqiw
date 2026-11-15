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
        public String installKey = UUID.randomUUID().toString()+UUID.randomUUID().toString();
        public boolean enabled = false;
    }
    private final Path file, outbox;
    public final Config config;
    private final Deque<JsonObject> queue = new ArrayDeque<>();
    private final ScheduledExecutorService executor = Executors.newSingleThreadScheduledExecutor(r -> { Thread t = new Thread(r, "NurChat network"); t.setDaemon(true); return t; });
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(8)).followRedirects(HttpClient.Redirect.NEVER).build();
    public volatile String status = "O'chirilgan";
    private String enrollment="";
    private volatile boolean remoteAllowed=false;
    private long lastStatus=0;
    private long consentGeneration=0;
    private String control="";
    private long retryAt = 0;
    private int failures = 0;
    public Reporter(Path directory) {
        file = directory.resolve("nur-chat.json"); outbox = directory.resolve("nur-chat-outbox.json");
        Config loaded;
        try { loaded = GSON.fromJson(Files.readString(file), Config.class); if (loaded == null) loaded = new Config(); }
        catch (Exception e) { loaded = new Config(); }
        config = loaded;
        if(config.installKey==null || config.installKey.length()<32) config.installKey=UUID.randomUUID().toString()+UUID.randomUUID().toString();
        try(var in=Reporter.class.getResourceAsStream("/nurchat-enrollment.json")) {
            if(in!=null) enrollment=JsonParser.parseString(new String(in.readAllBytes(),StandardCharsets.UTF_8)).getAsJsonObject().get("enrollment").getAsString();
        } catch(Exception ignored) {}
        if (config.token == null || config.deviceId == null || config.consentAt == null) { config.enabled = false; config.token = ""; config.deviceId = ""; config.consentAt = ""; }
        if (consented()) {
            try { JsonObject saved=JsonParser.parseString(Files.readString(outbox)).getAsJsonObject();control=saved.get("control").getAsString();JsonArray arr=saved.getAsJsonArray("events");for(JsonElement e:arr)if(queue.size()<1000)queue.add(e.getAsJsonObject()); } catch(Exception ignored) {}
            status = "Ulangan";
        } else { try { Files.deleteIfExists(outbox); } catch (Exception ignored) {} }
        save(); // Keep the first launch date locally even before pairing.
        executor.scheduleWithFixedDelay(this::sync, 1, 1, TimeUnit.SECONDS);
    }
    public synchronized boolean consented() { return config.enabled && !config.token.isBlank() && !config.consentAt.isBlank(); }
    public synchronized boolean active() { return consented() && remoteAllowed; }
    public boolean hasAutoEnrollment() { return !enrollment.isBlank(); }
    public synchronized boolean paired() { return !config.token.isBlank(); }
    private void privateFile(Path p) { try { Files.setPosixFilePermissions(p, PosixFilePermissions.fromString("rw-------")); } catch (Exception ignored) {} }
    public synchronized void save() {
        try { Files.createDirectories(file.getParent()); Path temp=file.resolveSibling(file.getFileName()+".tmp"); Files.writeString(temp,GSON.toJson(config),StandardCharsets.UTF_8); privateFile(temp); Files.move(temp,file,StandardCopyOption.REPLACE_EXISTING); privateFile(file); }
        catch (Exception e) { status="Sozlamani saqlashda xato"; }
    }
    private synchronized void saveQueue() {
        try { if(queue.isEmpty()){Files.deleteIfExists(outbox);return;}JsonObject saved=new JsonObject();saved.addProperty("control",control);saved.add("events",GSON.toJsonTree(queue));Files.writeString(outbox,GSON.toJson(saved),StandardCharsets.UTF_8);privateFile(outbox); } catch(Exception ignored) {}
    }
    public synchronized void pause() { consentGeneration++; config.enabled=false; remoteAllowed=false; queue.clear(); saveQueue(); save(); status="To'xtatilgan"; }
    public synchronized void enable() { if (!paired()) return; consentGeneration++; config.consentAt=Instant.now().toString(); config.enabled=true; lastStatus=0; save(); status="Bot holati tekshirilmoqda"; }
    public CompletableFuture<String> autoPair(String player) { return pairInternal("",player,true); }
    public CompletableFuture<String> pair(String code, String player) {
        return pairInternal(code,player,false);
    }
    private CompletableFuture<String> pairInternal(String code,String player,boolean automatic) {
        final long generation; synchronized(this) { generation=consentGeneration; }
        return CompletableFuture.supplyAsync(() -> {
            try {
                JsonObject body=new JsonObject(); body.addProperty("code",code.strip().toUpperCase(Locale.ROOT)); body.addProperty("player",player); body.addProperty("installed_at",config.installedAt); body.addProperty("consent",true);
                if(automatic) { body.addProperty("enrollment",enrollment); body.addProperty("install_key",config.installKey); }
                HttpRequest req=HttpRequest.newBuilder(URI.create(BASE+(automatic?"/auto-pair":"/pair"))).timeout(Duration.ofSeconds(12)).header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofString(body.toString())).build();
                HttpResponse<String> res=http.send(req,HttpResponse.BodyHandlers.ofString());
                if (res.statusCode()!=200) return automatic?"Bu modning bir kishilik ulanishi band yoki bekor qilingan.":"Kod xato yoki muddati tugagan. Botdan yangi kod oling.";
                JsonObject data=JsonParser.parseString(res.body()).getAsJsonObject();
                synchronized(this) { if(generation!=consentGeneration) return "Ulash to'xtatildi."; config.deviceId=data.get("device_id").getAsString(); config.token=data.get("token").getAsString(); config.consentAt=Instant.now().toString(); config.enabled=true; remoteAllowed=!data.has("reporting") || data.get("reporting").getAsBoolean();control=data.has("control")?data.get("control").getAsString():""; lastStatus=System.currentTimeMillis(); save(); status=remoteAllowed?"Botga yuborilyapti":"Admin tomonidan to'xtatilgan"; }
                return "OK";
            } catch (Exception e) { return "Botga ulanish bo'lmadi. Internetni tekshiring."; }
        },executor);
    }
    private void sync() {
        if(consented() && System.currentTimeMillis()-lastStatus>=10000) refreshStatus();
        flush();
    }
    private void refreshStatus() {
        lastStatus=System.currentTimeMillis();
        try {
            String token; synchronized(this) { token=config.token; }
            HttpRequest req=HttpRequest.newBuilder(URI.create(BASE+"/status")).timeout(Duration.ofSeconds(8)).header("Authorization","Bearer "+token).GET().build();
            HttpResponse<String> res=http.send(req,HttpResponse.BodyHandlers.ofString());
            synchronized(this) {
                if(res.statusCode()==401 || res.statusCode()==403) { pause();config.token="";save();status="Ulanish bekor qilingan";return; }
                if(res.statusCode()!=200) return;
                if(!consented()) return;
                JsonObject response=JsonParser.parseString(res.body()).getAsJsonObject();
                remoteAllowed=response.get("reporting").getAsBoolean();
                String next=response.has("control")?response.get("control").getAsString():"";
                if(!control.isBlank() && !control.equals(next)) { queue.clear();saveQueue(); }
                control=next;
                if(!remoteAllowed) { queue.clear();saveQueue(); }
                status=remoteAllowed?"Botga yuborilyapti":"Admin tomonidan to'xtatilgan";
            }
        } catch(Exception ignored) { if(consented()) status="Bot aloqasi kutilmoqda"; }
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
            String token; synchronized(this) { token=config.token;body.addProperty("control",control); }
            HttpRequest req=HttpRequest.newBuilder(URI.create(BASE+"/events")).timeout(Duration.ofSeconds(12)).header("Content-Type","application/json").header("Authorization","Bearer "+token).POST(HttpRequest.BodyPublishers.ofString(body.toString())).build();
            HttpResponse<String> res=http.send(req,HttpResponse.BodyHandlers.ofString());
            synchronized(this) {
                if (res.statusCode()==401 || res.statusCode()==403) { pause(); config.token=""; save(); status="Bot ulanishni bekor qildi"; return; }
                if (res.statusCode()!=200) throw new IllegalStateException("HTTP "+res.statusCode());
                JsonObject reply=JsonParser.parseString(res.body()).getAsJsonObject();
                if(reply.has("control") && !control.equals(reply.get("control").getAsString())) { control=reply.get("control").getAsString();remoteAllowed=reply.get("reporting").getAsBoolean();queue.clear();saveQueue();status=remoteAllowed?"Bot boshqaruvi yangilandi":"Admin tomonidan to'xtatilgan";return; }
                if(reply.has("reporting") && !reply.get("reporting").getAsBoolean()) { remoteAllowed=false;queue.clear();saveQueue();status="Admin tomonidan to'xtatilgan";return; }
                for(JsonObject e:batch) queue.remove(e); saveQueue(); failures=0; retryAt=0; if(active()) status="Botga yuborilyapti";
            }
        } catch (Exception e) { synchronized(this) { failures++; retryAt=System.currentTimeMillis()+Math.min(60000L,2000L*(1L<<Math.min(failures,5))); if(active()) status="Internet kutilmoqda (navbat: "+queue.size()+")"; } }
    }
    public void close() { executor.shutdown(); }
}
