package com.bobassistant.tv;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.media.audiofx.AcousticEchoCanceler;
import android.os.IBinder;
import android.os.PowerManager;
import android.util.Log;

import org.json.JSONException;
import org.json.JSONObject;

public final class VoiceService extends Service implements Link.Callback {
    static final String TAG = "BobTv";
    private static final String CHANNEL = "bob";
    private static final int RATE = 16000;
    private static final int BLOCK = 1280;

    static volatile boolean connected;
    static volatile boolean running;
    static volatile String echoCanceller = "нет";

    private Link link;
    private Overlay overlay;
    private MediaControl media;
    private final Player player = new Player();
    private Thread recorder;
    private volatile boolean recording;

    static void start(Context context) {
        context.startForegroundService(new Intent(context, VoiceService.class));
    }

    @Override
    public void onCreate() {
        super.onCreate();
        overlay = new Overlay(this);
        media = new MediaControl(this);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        startForeground(1, notification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE);
        if (running) {
            return START_STICKY;
        }
        if (!Prefs.configured(this) || checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            Log.w(TAG, "not configured or no microphone permission");
            stopSelf();
            return START_NOT_STICKY;
        }
        running = true;
        link = new Link(Prefs.server(this), Prefs.token(this), Prefs.device(this), this);
        link.start();
        startRecorder();
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        running = false;
        recording = false;
        if (recorder != null) {
            recorder.interrupt();
        }
        if (link != null) {
            link.stop();
        }
        player.stop();
        overlay.destroy();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private Notification notification() {
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel(CHANNEL, getString(R.string.channel_name), NotificationManager.IMPORTANCE_MIN));
        return new Notification.Builder(this, CHANNEL)
                .setContentTitle(getString(R.string.app_name))
                .setContentText(getString(R.string.notification_text))
                .setSmallIcon(android.R.drawable.ic_btn_speak_now)
                .setOngoing(true)
                .build();
    }

    private void startRecorder() {
        recording = true;
        recorder = new Thread(this::record, "bob-mic");
        recorder.start();
    }

    private void record() {
        int minimum = AudioRecord.getMinBufferSize(RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
        AudioRecord record;
        try {
            record = new AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, RATE,
                    AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, Math.max(minimum, BLOCK * 8));
        } catch (SecurityException error) {
            Log.e(TAG, "no microphone", error);
            return;
        }
        AcousticEchoCanceler canceller = null;
        if (AcousticEchoCanceler.isAvailable()) {
            canceller = AcousticEchoCanceler.create(record.getAudioSessionId());
            if (canceller != null) {
                canceller.setEnabled(true);
                echoCanceller = canceller.getEnabled() ? "включено" : "не включилось";
            }
        }
        Log.i(TAG, "echo canceller: " + echoCanceller);
        byte[] buffer = new byte[BLOCK * 2];
        record.startRecording();
        try {
            while (recording) {
                int read = record.read(buffer, 0, buffer.length);
                if (read > 0) {
                    link.sendAudio(buffer, read);
                }
            }
        } finally {
            record.stop();
            record.release();
            if (canceller != null) {
                canceller.release();
            }
        }
    }

    private void wakeScreen() {
        PowerManager power = getSystemService(PowerManager.class);
        if (!power.isInteractive()) {
            Intent intent = new Intent(this, WakeActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(intent);
        }
    }

    @Override
    public void onConnected(boolean state) {
        connected = state;
        Log.i(TAG, state ? "connected" : "disconnected");
    }

    @Override
    public void onMessage(JSONObject message) {
        String type = message.optString("type");
        switch (type) {
            case "state":
                String state = message.optString("state");
                if ("listening".equals(state)) {
                    wakeScreen();
                    media.hold();
                }
                if ("idle".equals(state)) {
                    media.release();
                }
                overlay.show(state, message.optString("text"));
                break;
            case "chime":
                Player.chime();
                break;
            case "audio_start":
                media.hold();
                player.start(message.optInt("rate", 48000), this::played);
                break;
            case "audio_end":
                player.finish();
                break;
            default:
                break;
        }
    }

    private void played() {
        try {
            link.sendJson(new JSONObject().put("type", "played"));
        } catch (JSONException ignored) {
        }
    }

    @Override
    public void onAudio(byte[] pcm) {
        player.write(pcm);
    }
}
