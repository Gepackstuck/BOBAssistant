package com.bobassistant.tv;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.util.TypedValue;
import android.view.Gravity;
import android.widget.TextView;

public final class MainActivity extends Activity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView status;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Intent intent = getIntent();
        if (intent.getBooleanExtra("stop", false)) {
            stopService(new Intent(this, VoiceService.class));
            finish();
            return;
        }
        Prefs.save(this, intent.getStringExtra("server"), intent.getStringExtra("token"), intent.getStringExtra("device"));
        if (intent.hasExtra("gain")) {
            Prefs.saveGain(this, intent.getFloatExtra("gain", 60f));
        }
        status = new TextView(this);
        status.setTextColor(Color.WHITE);
        status.setBackgroundColor(Color.rgb(18, 18, 24));
        status.setTextSize(TypedValue.COMPLEX_UNIT_SP, 22);
        status.setGravity(Gravity.CENTER);
        status.setPadding(80, 80, 80, 80);
        setContentView(status);
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 1);
        } else if (Prefs.configured(this)) {
            if (intent.getBooleanExtra("probe", false)) {
                startForegroundService(new Intent(this, VoiceService.class).putExtra("probe", true));
            } else {
                VoiceService.start(this);
            }
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        if (Prefs.configured(this) && checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            VoiceService.start(this);
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        refresh();
    }

    @Override
    protected void onPause() {
        handler.removeCallbacksAndMessages(null);
        super.onPause();
    }

    private void refresh() {
        String server = Prefs.server(this);
        StringBuilder text = new StringBuilder(getString(R.string.app_name)).append("\n\n");
        if (!Prefs.configured(this)) {
            text.append(getString(R.string.status_not_configured));
        } else {
            text.append(getString(VoiceService.connected ? R.string.status_connected : R.string.status_disconnected, server));
        }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            text.append("\n").append(getString(R.string.status_no_mic));
        }
        if (!Settings.canDrawOverlays(this)) {
            text.append("\n").append(getString(R.string.status_no_overlay));
        }
        text.append("\nЭхоподавление: ").append(VoiceService.echoCanceller);
        text.append("\nМикрофон: ").append(VoiceService.micSetup);
        status.setText(text);
        handler.postDelayed(this::refresh, 1000);
    }
}
