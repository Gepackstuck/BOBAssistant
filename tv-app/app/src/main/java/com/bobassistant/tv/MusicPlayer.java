package com.bobassistant.tv;

import android.content.Context;
import android.media.AudioAttributes;
import android.media.MediaMetadata;
import android.media.MediaPlayer;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.util.Log;

import java.io.IOException;

final class MusicPlayer {
    interface Events {
        void onEvent(String event, int position, boolean playing);
    }

    private final Context context;
    private final Events events;
    private final Handler main = new Handler(Looper.getMainLooper());
    private MediaPlayer player;
    private boolean playing;
    private float volume = 0.8f;
    private final Runnable ticker = this::tick;
    private MediaSession session;

    MusicPlayer(Context context, Events events) {
        this.context = context;
        this.events = events;
    }

    boolean isActive() {
        return player != null;
    }

    void play(String url, float requested, String title, String artist) {
        main.post(() -> start(url, requested, title, artist));
    }

    void pause() {
        main.post(() -> {
            Log.i(VoiceService.TAG, "music pause requested, playing=" + playing);
            if (player != null && playing) {
                player.pause();
                playing = false;
                publish(PlaybackState.STATE_PAUSED);
            }
        });
    }

    void resume() {
        main.post(() -> {
            Log.i(VoiceService.TAG, "music resume requested, playing=" + playing);
            if (player != null && !playing) {
                player.start();
                playing = true;
                publish(PlaybackState.STATE_PLAYING);
            }
        });
    }

    void stop() {
        main.post(this::release);
    }

    void setVolume(float value) {
        main.post(() -> {
            volume = value;
            if (player != null) {
                player.setVolume(volume, volume);
            }
        });
    }

    private void ensureSession() {
        if (session != null) {
            return;
        }
        session = new MediaSession(context, "BobMusic");
        session.setCallback(new MediaSession.Callback() {
            @Override
            public void onPlay() {
                events.onEvent("key:resume", 0, false);
            }

            @Override
            public void onPause() {
                events.onEvent("key:pause", 0, false);
            }

            @Override
            public void onSkipToNext() {
                events.onEvent("key:next", 0, false);
            }

            @Override
            public void onSkipToPrevious() {
                events.onEvent("key:previous", 0, false);
            }

            @Override
            public void onStop() {
                events.onEvent("key:stop", 0, false);
            }
        });
    }

    private void publish(int state) {
        if (session == null) {
            return;
        }
        int position = 0;
        try {
            position = player != null ? player.getCurrentPosition() : 0;
        } catch (IllegalStateException ignored) {
        }
        long actions = PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE | PlaybackState.ACTION_PLAY_PAUSE
                | PlaybackState.ACTION_SKIP_TO_NEXT | PlaybackState.ACTION_SKIP_TO_PREVIOUS | PlaybackState.ACTION_STOP;
        session.setPlaybackState(new PlaybackState.Builder()
                .setActions(actions)
                .setState(state, position, 1f)
                .build());
        session.setActive(state != PlaybackState.STATE_STOPPED);
    }

    private void start(String url, float requested, String title, String artist) {
        release();
        ensureSession();
        session.setMetadata(new MediaMetadata.Builder()
                .putString(MediaMetadata.METADATA_KEY_TITLE, title)
                .putString(MediaMetadata.METADATA_KEY_ARTIST, artist)
                .build());
        volume = requested;
        MediaPlayer created = new MediaPlayer();
        player = created;
        created.setAudioAttributes(new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                .build());
        created.setWakeMode(context, PowerManager.PARTIAL_WAKE_LOCK);
        created.setVolume(volume, volume);
        created.setOnPreparedListener(prepared -> {
            if (player == prepared) {
                prepared.start();
                playing = true;
                publish(PlaybackState.STATE_PLAYING);
                Log.i(VoiceService.TAG, "music started, duration=" + prepared.getDuration());
                main.removeCallbacks(ticker);
                main.postDelayed(ticker, 2000);
            }
        });
        created.setOnCompletionListener(finished -> {
            if (player == finished) {
                playing = false;
                events.onEvent("ended", 0, false);
            }
        });
        created.setOnErrorListener((failed, what, extra) -> {
            Log.w(VoiceService.TAG, "music error " + what + "/" + extra);
            if (player == failed) {
                playing = false;
                events.onEvent("error", 0, false);
            }
            return true;
        });
        try {
            created.setDataSource(url);
            created.prepareAsync();
        } catch (IOException | IllegalStateException error) {
            Log.w(VoiceService.TAG, "music source failed", error);
            events.onEvent("error", 0, false);
        }
    }

    private void tick() {
        if (player == null) {
            return;
        }
        int position = 0;
        try {
            position = player.getCurrentPosition();
        } catch (IllegalStateException ignored) {
        }
        events.onEvent("position", position, playing);
        main.postDelayed(ticker, 2000);
    }

    private void release() {
        publish(PlaybackState.STATE_STOPPED);
        main.removeCallbacks(ticker);
        if (player != null) {
            MediaPlayer old = player;
            player = null;
            playing = false;
            try {
                old.reset();
            } catch (IllegalStateException ignored) {
            }
            old.release();
        }
    }
}
