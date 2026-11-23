package com.bobassistant.helper;

import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioRecord;

import java.io.FileOutputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public final class Capture {
    static final int RATE = 16000;
    static final int BLOCK = 1280;

    static AudioRecord open(int source, int encoding) throws Exception {
        AudioFormat format = new AudioFormat.Builder().setEncoding(encoding).setSampleRate(RATE).setChannelMask(AudioFormat.CHANNEL_IN_MONO).build();
        AudioRecord.Builder builder = new AudioRecord.Builder();
        AudioRecord.Builder.class.getMethod("setContext", android.content.Context.class).invoke(builder, Shell.get());
        if (source >= 1000) {
            AudioAttributes.Builder attributes = new AudioAttributes.Builder();
            AudioAttributes.Builder.class.getMethod("setInternalCapturePreset", int.class).invoke(attributes, source);
            AudioRecord.Builder.class.getMethod("setAudioAttributes", AudioAttributes.class).invoke(builder, attributes.build());
        } else {
            builder.setAudioSource(source);
        }
        return builder.setAudioFormat(format).setBufferSizeInBytes(BLOCK * 16).build();
    }

    static Thread worker(String name, int source, boolean floats, String path, long end, long[] started) {
        return new Thread(() -> {
            try (FileOutputStream out = new FileOutputStream(path)) {
                AudioRecord record = open(source, floats ? AudioFormat.ENCODING_PCM_FLOAT : AudioFormat.ENCODING_PCM_16BIT);
                float[] floatBuffer = new float[BLOCK];
                short[] shortBuffer = new short[BLOCK];
                ByteBuffer bytes = ByteBuffer.allocate(BLOCK * 4).order(ByteOrder.LITTLE_ENDIAN);
                record.startRecording();
                started[0] = System.nanoTime();
                while (System.currentTimeMillis() < end) {
                    bytes.clear();
                    int read;
                    if (floats) {
                        read = record.read(floatBuffer, 0, BLOCK, AudioRecord.READ_BLOCKING);
                        for (int i = 0; i < read; i++) {
                            bytes.putFloat(floatBuffer[i]);
                        }
                    } else {
                        read = record.read(shortBuffer, 0, BLOCK, AudioRecord.READ_BLOCKING);
                        for (int i = 0; i < read; i++) {
                            bytes.putFloat(shortBuffer[i] / 32768f);
                        }
                    }
                    if (read <= 0) {
                        break;
                    }
                    out.write(bytes.array(), 0, read * 4);
                }
                record.stop();
                record.release();
            } catch (Throwable error) {
                System.out.println(name + ": FAIL " + error + (error.getCause() != null ? " / " + error.getCause() : ""));
            }
        }, name);
    }

    public static void main(String[] args) throws Exception {
        int seconds = Integer.parseInt(args[0]);
        String prefix = args[1];
        long end = System.currentTimeMillis() + seconds * 1000L;
        long[] micStart = new long[1];
        long[] refStart = new long[1];
        Thread mic = worker("mic", 6, true, prefix + "-mic.f32", end, micStart);
        Thread ref = worker("ref", 1997, false, prefix + "-ref.f32", end, refStart);
        mic.start();
        ref.start();
        mic.join();
        ref.join();
        System.out.println("mic start - ref start, ms: " + (micStart[0] - refStart[0]) / 1e6);
        System.exit(0);
    }
}
