package com.bobassistant.tv;

import android.content.Context;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioManager;
import android.os.SystemClock;
import android.view.KeyEvent;

final class MediaControl {
    private final AudioManager audio;
    private final AudioFocusRequest focus;
    private boolean pausedByUs;

    MediaControl(Context context) {
        audio = context.getSystemService(AudioManager.class);
        focus = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
                .setAudioAttributes(new AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ASSISTANT)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build())
                .build();
    }

    void hold() {
        if (pausedByUs) {
            return;
        }
        if (audio.isMusicActive()) {
            press(KeyEvent.KEYCODE_MEDIA_PAUSE);
            pausedByUs = true;
        }
        audio.requestAudioFocus(focus);
    }

    void release() {
        audio.abandonAudioFocusRequest(focus);
        if (pausedByUs) {
            pausedByUs = false;
            press(KeyEvent.KEYCODE_MEDIA_PLAY);
        }
    }

    private void press(int code) {
        long now = SystemClock.uptimeMillis();
        audio.dispatchMediaKeyEvent(new KeyEvent(now, now, KeyEvent.ACTION_DOWN, code, 0));
        audio.dispatchMediaKeyEvent(new KeyEvent(now, now, KeyEvent.ACTION_UP, code, 0));
    }
}
