package uz.nuroqiw.chat;

public final class PrivacyTest {
    public static void main(String[] args) {
        for(String command:new String[]{"login mypassword", "/register secret secret", "AUTHME:LOGIN secret", "l secret", "nurchat ABC1234567", "changepassword old new"})
            if(Privacy.sanitize(command,true)!=null) throw new AssertionError("Secret command retained: "+command);
        if(Privacy.sanitize("/login password",false)!=null) throw new AssertionError("Chat route leaked login");
        if(!"/promo TEST123".equals(Privacy.sanitize("promo TEST123",true))) throw new AssertionError("Promo lost");
        if(!"Salom hammaga".equals(Privacy.sanitize("Salom hammaga",false))) throw new AssertionError("Chat changed");
        String result=Privacy.sanitize("parol: test-password token=sk-123456789012345678901234",false);
        if(result.contains("test-password")||result.contains("sk-123")) throw new AssertionError("Credential leak");
        if(Privacy.sanitize("x".repeat(2000),false).length()>1024) throw new AssertionError("Length limit");
        System.out.println("PASS: Java chat privacy, command exclusions, credential masking and length limit");
    }
}
