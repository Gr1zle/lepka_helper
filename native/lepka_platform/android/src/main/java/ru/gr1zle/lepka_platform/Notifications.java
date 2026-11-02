package ru.gr1zle.lepka_platform;

import android.Manifest;
import android.app.Activity;
import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;
import org.json.JSONArray;
import org.json.JSONObject;

/** Inexact local alarms, deliberately independent of the Python runtime. */
public final class Notifications {
    private static final String CHANNEL = "lepka_reminders_v1";
    private static SharedPreferences prefs(Context c) { return c.getSharedPreferences("lepka_notifications", Context.MODE_PRIVATE); }
    private static NotificationManager manager(Context c) { return (NotificationManager)c.getSystemService(Context.NOTIFICATION_SERVICE); }
    private static boolean allowed(Context c) {
        return (Build.VERSION.SDK_INT < 33 || c.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED)
            && manager(c).areNotificationsEnabled();
    }
    private static void channel(Context c) {
        manager(c).createNotificationChannel(new NotificationChannel(CHANNEL, "Напоминания и события", NotificationManager.IMPORTANCE_DEFAULT));
    }
    private static Intent alarm(Context c, String key) {
        return new Intent(c, ReminderReceiver.class).setAction("ru.gr1zle.lepka.REMIND")
            .setData(android.net.Uri.parse("lepka://reminder/"+android.net.Uri.encode(key))).putExtra("key", key);
    }
    private static PendingIntent alarmIntent(Context c, String key) {
        return PendingIntent.getBroadcast(c, 0, alarm(c, key), PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
    }
    private static JSONArray plan(Context c) throws Exception { return new JSONArray(prefs(c).getString("items", "[]")); }
    private static void cancelAlarms(Context c) throws Exception {
        AlarmManager alarms = (AlarmManager)c.getSystemService(Context.ALARM_SERVICE);
        JSONArray items = plan(c);
        for (int i=0;i<items.length();i++) alarms.cancel(alarmIntent(c, items.getJSONObject(i).getString("key")));
    }
    private static void schedule(Context c) throws Exception {
        if (!allowed(c)) return;
        JSONArray items = plan(c); long now = System.currentTimeMillis();
        AlarmManager alarms = (AlarmManager)c.getSystemService(Context.ALARM_SERVICE);
        for (int i=0;i<items.length();i++) {
            JSONObject item=items.getJSONObject(i); String key=item.getString("key");
            if (prefs(c).getBoolean("sent:"+key, false)) continue;
            long at=item.getLong("at");
            if (at < now-86400000L) continue;
            alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, Math.max(at,now+5000), alarmIntent(c,key));
        }
    }
    private static void clear(Context c) throws Exception {
        cancelAlarms(c); prefs(c).edit().clear().commit(); manager(c).cancelAll();
    }
    private static void show(Context c, JSONObject item) throws Exception {
        if (!allowed(c)) return;
        String key=item.getString("key"); SharedPreferences p=prefs(c);
        if (p.getBoolean("sent:"+key,false)) return;
        channel(c);
        Intent click=c.getPackageManager().getLaunchIntentForPackage(c.getPackageName());
        if(click==null) return;
        click.setData(android.net.Uri.parse("lepka://open/"+android.net.Uri.encode(key)))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_SINGLE_TOP)
            .putExtra("lepkaOwner",p.getString("owner",""))
            .putExtra("lepkaRoute",item.optString("route","/notices"));
        // Direct Activity intent avoids prohibited Android 12 notification trampolines.
        PendingIntent tap=PendingIntent.getActivity(c,0,click,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        Notification notification=new Notification.Builder(c,CHANNEL)
            .setSmallIcon(android.R.drawable.ic_popup_reminder)
            .setContentTitle(item.optString("title","Напоминание").substring(0,Math.min(50,item.optString("title","Напоминание").length())))
            .setContentText(item.optString("body", "").substring(0,Math.min(200,item.optString("body", "").length())))
            .setContentIntent(tap).setAutoCancel(true).setVisibility(Notification.VISIBILITY_PRIVATE).build();
        manager(c).notify(key,1,notification);
        // Keep a bounded deduplication ledger across restarts and alarm rescheduling.
        JSONArray sent=new JSONArray(p.getString("sentKeys","[]")); sent.put(key);
        SharedPreferences.Editor edit=p.edit().putBoolean("sent:"+key,true);
        while(sent.length()>500) { String old=sent.getString(0);sent.remove(0);edit.remove("sent:"+old); }
        edit.putString("sentKeys",sent.toString()).commit();
    }
    public static void opened(Context c, Intent intent) {
        try {
            String owner=intent.getStringExtra("lepkaOwner");
            if(owner==null || !owner.equals(prefs(c).getString("owner",""))) return;
            prefs(c).edit().putString("opened",new JSONObject().put("owner",owner).put("route",intent.getStringExtra("lepkaRoute")).toString()).commit();
            intent.removeExtra("lepkaOwner");intent.removeExtra("lepkaRoute");
        } catch(Exception ignored) { }
    }
    public static String call(Context c, Activity activity, String operation, String value) throws Exception {
        if (operation.equals("notifyStatus")) {
            channel(c);
            schedule(c);
            NotificationChannel channel=manager(c).getNotificationChannel(CHANNEL);
            return new JSONObject().put("granted",allowed(c)).put("channelEnabled",channel.getImportance()!=NotificationManager.IMPORTANCE_NONE).toString();
        }
        if (operation.equals("notifyPermission")) {
            if (Build.VERSION.SDK_INT>=33 && activity!=null && c.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)
                activity.requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 2601);
            return "ok";
        }
        if (operation.equals("notifyClear")) { clear(c);return "ok"; }
        if (operation.equals("notifyOpen")) {
            String opened=prefs(c).getString("opened",null);prefs(c).edit().remove("opened").commit();return opened;
        }
        if (operation.equals("notifySync")) {
            if(value==null || value.length()>150000) throw new IllegalArgumentException();
            JSONObject document=new JSONObject(value);JSONArray items=document.getJSONArray("items");String owner=document.getString("owner");
            if(items.length()>100 || owner.length()>64) throw new IllegalArgumentException();
            if(!owner.equals(prefs(c).getString("owner",""))) clear(c);else cancelAlarms(c);
            prefs(c).edit().putString("owner",owner).putString("items",items.toString()).commit();schedule(c);return "ok";
        }
        if (operation.equals("notifyShow")) {
            JSONObject item=new JSONObject(value);
            if(item.getString("owner").equals(prefs(c).getString("owner",""))) show(c,item);
            return "ok";
        }
        if (operation.equals("notifyTest")) {
            JSONObject item=new JSONObject().put("key","test:"+System.currentTimeMillis()).put("title","Помощник по лепке")
                .put("body","Уведомления работают").put("route","/notices");show(c,item);return "ok";
        }
        throw new IllegalArgumentException();
    }
    public static final class ReminderReceiver extends BroadcastReceiver {
        @Override public void onReceive(Context c, Intent intent) {
            try {
                if(Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction()) || Intent.ACTION_MY_PACKAGE_REPLACED.equals(intent.getAction()) || Intent.ACTION_TIME_CHANGED.equals(intent.getAction()) || Intent.ACTION_TIMEZONE_CHANGED.equals(intent.getAction())) { schedule(c);return; }
                String key=intent.getStringExtra("key");JSONArray items=plan(c);
                for(int i=0;i<items.length();i++) { JSONObject item=items.getJSONObject(i);if(item.getString("key").equals(key)) { show(c,item);break; } }
            } catch(Exception failure) { android.util.Log.w("LepkaNotifications","Reminder unavailable"); }
        }
    }
}
