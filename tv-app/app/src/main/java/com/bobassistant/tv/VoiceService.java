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
    static volatile String micSetup = "";
    private static final int[] SOURCES = {6, 1, 9, 5, 7, 0};

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
        boolean probe = intent != null && intent.getBooleanExtra("probe", false);
        if (running) {
            if (probe) {
                new Thread(this::probe, "bob-probe").start();
            }
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
        if (probe) {
            new Thread(this::probe, "bob-probe").start();
        } else {
            startRecorder();
        }
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

    private static int channelMask(int channels) {
        return channels == 2 ? AudioFormat.CHANNEL_IN_STEREO : AudioFormat.CHANNEL_IN_MONO;
    }

    private AudioRecord open(int source, int channels) {
        int mask = channelMask(channels);
        int minimum = AudioRecord.getMinBufferSize(RATE, mask, AudioFormat.ENCODING_PCM_FLOAT);
        try {
            AudioRecord record = new AudioRecord(source, RATE, mask, AudioFormat.ENCODING_PCM_FLOAT, Math.max(minimum, BLOCK * 8 * channels * 4));
            if (record.getState() != AudioRecord.STATE_INITIALIZED) {
                record.release();
                return null;
            }
            return record;
        } catch (SecurityException | IllegalArgumentException error) {
            Log.e(TAG, "cannot open source " + source, error);
            return null;
        }
    }

    private void probe() {
        recording = false;
        if (recorder != null) {
            try {
                recorder.join(2000);
            } catch (InterruptedException ignored) {
                return;
            }
        }
        int bestSource = Prefs.source(this);
        int bestChannels = Prefs.channels(this);
        float bestPeak = 0;
        float[] buffer = new float[BLOCK * 2];
        for (int source : SOURCES) {
            for (int channels = 1; channels <= 2; channels++) {
                AudioRecord record = open(source, channels);
                if (record == null) {
                    Log.i(TAG, "probe source=" + source + " channels=" + channels + " unavailable");
                    continue;
                }
                record.startRecording();
                float peak = 0;
                long end = System.currentTimeMillis() + 1500;
                while (System.currentTimeMillis() < end) {
                    int read = record.read(buffer, 0, buffer.length, AudioRecord.READ_BLOCKING);
                    for (int i = 0; i < read; i++) {
                        peak = Math.max(peak, Math.abs(buffer[i]));
                    }
                }
                record.stop();
                record.release();
                Log.i(TAG, "probe source=" + source + " channels=" + channels + " peak=" + peak);
                if (peak > bestPeak) {
                    bestPeak = peak;
                    bestSource = source;
                    bestChannels = channels;
                }
            }
        }
        Prefs.saveMic(this, bestSource, bestChannels);
        Log.i(TAG, "probe chose source=" + bestSource + " channels=" + bestChannels + " peak=" + bestPeak);
        startRecorder();
    }

    private void record() {
        int channels = Prefs.channels(this);
        AudioRecord record = open(Prefs.source(this), channels);
        if (record == null) {
            return;
        }
        micSetup = "источник " + Prefs.source(this) + ", каналов " + channels;
        AcousticEchoCanceler canceller = null;
        if (AcousticEchoCanceler.isAvailable()) {
            canceller = AcousticEchoCanceler.create(record.getAudioSessionId());
            if (canceller != null) {
                canceller.setEnabled(true);
                echoCanceller = canceller.getEnabled() ? "включено" : "не включилось";
            }
        }
        Log.i(TAG, "echo canceller: " + echoCanceller);
        float[] frames = new float[BLOCK * channels];
        byte[] out = new byte[BLOCK * 2];
        float gain = Prefs.gain(this);
        micSetup += ", усиление " + Math.round(gain);
        record.startRecording();
        try {
            while (recording) {
                int read = record.read(frames, 0, frames.length, AudioRecord.READ_BLOCKING);
                if (read < 0) {
                    Log.e(TAG, "read failed " + read);
                    break;
                }
                int samples = read / channels;
                for (int i = 0; i < samples; i++) {
                    float mixed = channels == 2 ? (frames[2 * i] + frames[2 * i + 1]) / 2f : frames[i];
                    int value = Math.round(Math.max(-1f, Math.min(1f, mixed * gain)) * 32767f);
                    out[2 * i] = (byte) value;
                    out[2 * i + 1] = (byte) (value >> 8);
                }
                if (samples > 0) {
                    link.sendAudio(out, samples * 2);
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
