package com.bobassistant.tv;

import android.content.Context;
import android.content.SharedPreferences;

final class Prefs {
    private static final String NAME = "bob";
    private static final String SERVER = "server";
    private static final String TOKEN = "token";
    private static final String DEVICE = "device";
    private static final String SOURCE = "source";
    private static final String CHANNELS = "channels";
    private static final String GAIN = "gain";

    private Prefs() {
    }

    private static SharedPreferences prefs(Context context) {
        return context.getSharedPreferences(NAME, Context.MODE_PRIVATE);
    }

    static String server(Context context) {
        return prefs(context).getString(SERVER, "");
    }

    static String token(Context context) {
        return prefs(context).getString(TOKEN, "");
    }

    static String device(Context context) {
        return prefs(context).getString(DEVICE, "tv");
    }

    static int source(Context context) {
        return prefs(context).getInt(SOURCE, 6);
    }

    static int channels(Context context) {
        return prefs(context).getInt(CHANNELS, 1);
    }

    static float gain(Context context) {
        return prefs(context).getFloat(GAIN, 60f);
    }

    static void saveGain(Context context, float gain) {
        prefs(context).edit().putFloat(GAIN, gain).apply();
    }

    static void saveMic(Context context, int source, int channels) {
        prefs(context).edit().putInt(SOURCE, source).putInt(CHANNELS, channels).apply();
    }

    static boolean configured(Context context) {
        return !server(context).isEmpty() && !token(context).isEmpty();
    }

    static void save(Context context, String server, String token, String device) {
        SharedPreferences.Editor editor = prefs(context).edit();
        if (server != null) {
            editor.putString(SERVER, server);
        }
        if (token != null) {
            editor.putString(TOKEN, token);
        }
        if (device != null) {
            editor.putString(DEVICE, device);
        }
        editor.apply();
    }
}
