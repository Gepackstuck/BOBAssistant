package com.bobassistant.tv;

import android.app.Activity;
import android.os.Bundle;

public final class WakeActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (getIntent().getBooleanExtra("start_service", false)) {
            VoiceService.start(this);
        } else {
            setShowWhenLocked(true);
            setTurnScreenOn(true);
        }
        finish();
    }
}
