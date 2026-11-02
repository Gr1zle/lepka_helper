package ru.gr1zle.lepka_platform;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import io.flutter.embedding.engine.plugins.FlutterPlugin;
import io.flutter.plugin.common.MethodChannel;
import io.flutter.embedding.engine.plugins.activity.ActivityAware;
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding;

public final class LepkaPlatformPlugin implements FlutterPlugin, ActivityAware, io.flutter.plugin.common.PluginRegistry.NewIntentListener {
    private static final String ALIAS = "ru.gr1zle.lepka.session.v1";
    private MethodChannel channel;
    private SharedPreferences preferences;
    private Context context;
    private android.app.Activity activity;
    private ActivityPluginBinding activityBinding;
    @Override public boolean onNewIntent(android.content.Intent intent) { Notifications.opened(context,intent); return false; }
    @Override public void onAttachedToActivity(ActivityPluginBinding binding) {
        activityBinding=binding;activity=binding.getActivity();binding.addOnNewIntentListener(this);
        Notifications.opened(context,activity.getIntent());
    }
    @Override public void onDetachedFromActivity() {
        if(activityBinding!=null)activityBinding.removeOnNewIntentListener(this);
        activityBinding=null;activity=null;
    }
    @Override public void onDetachedFromActivityForConfigChanges() { onDetachedFromActivity(); }
    @Override public void onReattachedToActivityForConfigChanges(ActivityPluginBinding binding) { onAttachedToActivity(binding); }

    private SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (store.containsAlias(ALIAS)) return (SecretKey) store.getKey(ALIAS, null);
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(ALIAS,
            KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setRandomizedEncryptionRequired(true).build());
        return generator.generateKey();
    }

    @Override public void onAttachedToEngine(FlutterPluginBinding binding) {
        context=binding.getApplicationContext();
        preferences = binding.getApplicationContext().getSharedPreferences("lepka_protected_session", Context.MODE_PRIVATE);
        channel = new MethodChannel(binding.getBinaryMessenger(), "ru.gr1zle.lepka/protected_session");
        channel.setMethodCallHandler((call, result) -> {
            try {
                if (call.method.startsWith("notify")) {
                    result.success(Notifications.call(context, activity, call.method, call.argument("value")));
                } else if (call.method.equals("write")) {
                    String value = call.argument("value");
                    if (value == null || value.length() > 8192) throw new IllegalArgumentException();
                    Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
                    cipher.init(Cipher.ENCRYPT_MODE, key());
                    String encrypted = Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP) + ":" +
                        Base64.encodeToString(cipher.doFinal(value.getBytes(java.nio.charset.StandardCharsets.UTF_8)), Base64.NO_WRAP);
                    if (!preferences.edit().putString("record", encrypted).commit()) throw new IllegalStateException();
                    result.success("ok");
                } else if (call.method.equals("read")) {
                    String record = preferences.getString("record", null);
                    if (record == null) { result.success(null); return; }
                    String[] parts = record.split(":", 2);
                    if (parts.length != 2) throw new IllegalArgumentException();
                    Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
                    cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)));
                    result.success(new String(cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)), java.nio.charset.StandardCharsets.UTF_8));
                } else if (call.method.equals("delete")) {
                    if (!preferences.edit().remove("record").commit()) throw new IllegalStateException();
                    KeyStore store = KeyStore.getInstance("AndroidKeyStore"); store.load(null);
                    if (store.containsAlias(ALIAS)) store.deleteEntry(ALIAS);
                    result.success("ok");
                } else result.notImplemented();
            } catch (Exception failure) {
                result.error("protected_session_unavailable", "Protected session storage unavailable", null);
            }
        });
    }
    @Override public void onDetachedFromEngine(FlutterPluginBinding binding) {
        channel.setMethodCallHandler(null);
    }
}
