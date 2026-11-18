package com.bobassistant.tv;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

public final class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (!Prefs.configured(context)) {
            return;
        }
        try {
            VoiceService.start(context);
        } catch (RuntimeException error) {
            Log.w(VoiceService.TAG, "direct start refused, starting through an activity", error);
            context.startActivity(new Intent(context, WakeActivity.class)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    .putExtra("start_service", true));
        }
    }
}
