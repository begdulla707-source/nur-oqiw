package uz.nuroqiw.chat;

import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;

public final class Privacy {
    private Privacy() {}
    private static final Set<String> SECRET_COMMANDS = Set.of("login", "l", "register", "reg", "r", "changepassword", "changepass", "password", "passwd", "pass", "auth", "authenticate", "2fa", "otp", "totp", "pin", "email", "recovery", "recover", "premium", "link", "linkaccount", "verify", "nurchat");
    private static final Pattern LABELED = Pattern.compile("(?i)((?:password|passwd|parol|token|secret|api[_-]?key|authorization|пароль|bearer)\\s*[:= ]\\s*)\\S+");
    private static final Pattern TOKEN = Pattern.compile("(?:\\d{6,12}:[A-Za-z0-9_-]{25,}|(?:ghp_|github_pat_|sk-)[A-Za-z0-9_-]{15,}|eyJ[A-Za-z0-9_-]{12,}\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+|[A-Za-z0-9_-]{40,})");
    public static String sanitize(String raw, boolean command) {
        String s = raw == null ? "" : raw.strip();
        if (command || s.startsWith("/")) {
            String[] a = s.replaceFirst("^/", "").split("\\s+", 2);
            String root = a[0].toLowerCase(Locale.ROOT);
            root = root.substring(root.lastIndexOf(':') + 1);
            if (SECRET_COMMANDS.contains(root)) return null;
            if (!s.startsWith("/")) s = "/" + s;
        }
        s = LABELED.matcher(s).replaceAll("$1[yashirildi]");
        s = TOKEN.matcher(s).replaceAll("[yashirildi]");
        return s.substring(0, Math.min(1024, s.length()));
    }
}
