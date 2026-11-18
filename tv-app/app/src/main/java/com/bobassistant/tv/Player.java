package com.bobassistant.tv;

import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioTrack;

import java.util.concurrent.LinkedBlockingQueue;

final class Player {
    interface Done {
        void onPlayed();
    }

    private static final byte[] END = new byte[0];

    private final LinkedBlockingQueue<byte[]> queue = new LinkedBlockingQueue<>();
    private Thread worker;

    synchronized void start(int rate, Done done) {
        stop();
        queue.clear();
        worker = new Thread(() -> play(rate, done), "bob-player");
        worker.start();
    }

    void write(byte[] pcm) {
        queue.offer(pcm);
    }

    void finish() {
        queue.offer(END);
    }

    synchronized void stop() {
        if (worker != null) {
            worker.interrupt();
            worker = null;
        }
    }

    private void play(int rate, Done done) {
        int minimum = AudioTrack.getMinBufferSize(rate, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT);
        AudioTrack track = new AudioTrack.Builder()
                .setAudioAttributes(new AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ASSISTANT)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build())
                .setAudioFormat(new AudioFormat.Builder()
                        .setSampleRate(rate)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .build())
                .setBufferSizeInBytes(Math.max(minimum * 4, rate))
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build();
        int written = 0;
        try {
            track.play();
            while (true) {
                byte[] chunk = queue.take();
                if (chunk == END) {
                    break;
                }
                track.write(chunk, 0, chunk.length);
                written += chunk.length / 2;
            }
            while (track.getPlaybackHeadPosition() < written && track.getPlayState() == AudioTrack.PLAYSTATE_PLAYING) {
                Thread.sleep(30);
            }
        } catch (InterruptedException ignored) {
            Thread.currentThread().interrupt();
        } finally {
            track.stop();
            track.release();
            done.onPlayed();
        }
    }

    static void chime() {
        int rate = 24000;
        int samples = rate * 12 / 100;
        short[] tone = new short[samples];
        for (int i = 0; i < samples; i++) {
            double t = (double) i / rate;
            double envelope = Math.min(1.0, Math.min(t / 0.01, (0.12 - t) / 0.04));
            double value = Math.sin(2 * Math.PI * 880 * t) + 0.5 * Math.sin(2 * Math.PI * 1320 * t);
            tone[i] = (short) (envelope * value * 0.25 * Short.MAX_VALUE);
        }
        AudioTrack track = new AudioTrack.Builder()
                .setAudioAttributes(new AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_ASSISTANCE_SONIFICATION)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .build())
                .setAudioFormat(new AudioFormat.Builder()
                        .setSampleRate(rate)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .build())
                .setBufferSizeInBytes(samples * 2)
                .setTransferMode(AudioTrack.MODE_STATIC)
                .build();
        track.write(tone, 0, samples);
        track.setNotificationMarkerPosition(samples);
        track.setPlaybackPositionUpdateListener(new AudioTrack.OnPlaybackPositionUpdateListener() {
            @Override
            public void onMarkerReached(AudioTrack finished) {
                finished.release();
            }

            @Override
            public void onPeriodicNotification(AudioTrack ignored) {
            }
        });
        track.play();
    }
}
