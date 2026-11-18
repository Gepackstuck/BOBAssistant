package com.bobassistant.tv;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public final class ControlReceiver extends BroadcastReceiver {
    static final String STOP = "com.bobassistant.tv.STOP";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (STOP.equals(intent.getAction())) {
            context.stopService(new Intent(context, VoiceService.class));
        }
    }
}
