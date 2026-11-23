package com.bobassistant.helper;

import android.media.AudioFormat;
import android.media.AudioRecord;

public final class Probe {
    public static void main(String[] args) throws Exception {
        int[] sources = args.length > 0 ? new int[]{Integer.parseInt(args[0])} : new int[]{1997, 8};
        for (int source : sources) {
            try {
                AudioFormat format = new AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(16000)
                        .setChannelMask(AudioFormat.CHANNEL_IN_MONO)
                        .build();
                AudioRecord.Builder builder = new AudioRecord.Builder();
                AudioRecord.Builder.class.getMethod("setContext", android.content.Context.class).invoke(builder, Shell.get());
                if (source >= 1000) {
                    android.media.AudioAttributes.Builder attributes = new android.media.AudioAttributes.Builder();
                    android.media.AudioAttributes.Builder.class.getMethod("setInternalCapturePreset", int.class).invoke(attributes, source);
                    AudioRecord.Builder.class.getMethod("setAudioAttributes", android.media.AudioAttributes.class).invoke(builder, attributes.build());
                } else {
                    builder.setAudioSource(source);
                }
                AudioRecord record = builder.setAudioFormat(format).setBufferSizeInBytes(16000 * 2).build();
                System.out.println("source " + source + ": state=" + record.getRecordingState() + " init=" + record.getState());
                record.startRecording();
                short[] buffer = new short[1600];
                long total = 0;
                int peak = 0;
                double sum = 0;
                long end = System.currentTimeMillis() + 4000;
                while (System.currentTimeMillis() < end) {
                    int read = record.read(buffer, 0, buffer.length);
                    for (int i = 0; i < read; i++) {
                        peak = Math.max(peak, Math.abs(buffer[i]));
                        sum += (double) buffer[i] * buffer[i];
                    }
                    total += Math.max(read, 0);
                }
                System.out.println("source " + source + ": samples=" + total + " peak=" + peak + " rms=" + Math.round(Math.sqrt(sum / Math.max(total, 1))));
                record.stop();
                record.release();
            } catch (Throwable error) {
                System.out.println("source " + source + ": FAIL " + error);
                Throwable cause = error.getCause();
                if (cause != null) {
                    System.out.println("  cause: " + cause);
                }
            }
        }
        System.exit(0);
    }
}
