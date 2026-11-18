package com.bobassistant.tv;

import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.media.AudioManager;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

final class TvControl {
    private final Context context;
    private final AudioManager audio;

    TvControl(Context context) {
        this.context = context;
        this.audio = context.getSystemService(AudioManager.class);
    }

    JSONObject state() throws JSONException {
        int max = Math.max(1, audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC));
        int current = audio.getStreamVolume(AudioManager.STREAM_MUSIC);
        return new JSONObject().put("type", "tv_state").put("volume", current).put("max", max)
                .put("percent", Math.round(current * 100f / max)).put("muted", audio.isStreamMute(AudioManager.STREAM_MUSIC));
    }

    JSONObject apps() throws JSONException {
        PackageManager packages = context.getPackageManager();
        JSONArray list = new JSONArray();
        Set<String> seen = new HashSet<>();
        for (String category : new String[]{Intent.CATEGORY_LEANBACK_LAUNCHER, Intent.CATEGORY_LAUNCHER}) {
            List<ResolveInfo> found = packages.queryIntentActivities(new Intent(Intent.ACTION_MAIN).addCategory(category), 0);
            for (ResolveInfo info : found) {
                String name = info.activityInfo.packageName;
                if (seen.add(name)) {
                    list.put(new JSONObject().put("package", name).put("label", info.loadLabel(packages).toString()));
                }
            }
        }
        return new JSONObject().put("type", "apps").put("apps", list);
    }

    JSONObject handle(JSONObject message) throws JSONException {
        String action = message.optString("action");
        int flags = AudioManager.FLAG_SHOW_UI;
        switch (action) {
            case "volume_up":
                audio.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_RAISE, flags);
                break;
            case "volume_down":
                audio.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_LOWER, flags);
                break;
            case "volume_set":
                int max = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC);
                int percent = Math.max(0, Math.min(100, message.optInt("percent", 20)));
                audio.setStreamVolume(AudioManager.STREAM_MUSIC, Math.round(percent * max / 100f), flags);
                break;
            case "mute":
                audio.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_MUTE, flags);
                break;
            case "unmute":
                audio.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_UNMUTE, flags);
                break;
            case "launch":
                launch(message.optString("package"));
                break;
            case "home":
                context.startActivity(new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                break;
            case "apps":
                return apps();
            default:
                break;
        }
        return state();
    }

    private void launch(String name) {
        PackageManager packages = context.getPackageManager();
        Intent intent = packages.getLeanbackLaunchIntentForPackage(name);
        if (intent == null) {
            intent = packages.getLaunchIntentForPackage(name);
        }
        if (intent != null) {
            context.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        }
    }
}
