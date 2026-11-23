package com.bobassistant.helper;

import android.media.AudioFormat;
import android.media.AudioRecord;

import java.io.BufferedOutputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public final class Stream {
    static final int BLOCK = Capture.BLOCK;
    static final int QUEUE = 24;

    static void pump(AudioRecord record, boolean floats, BlockingQueue<float[]> queue) {
        float[] floatBuffer = new float[BLOCK];
        short[] shortBuffer = new short[BLOCK];
        record.startRecording();
        while (true) {
            float[] block = new float[BLOCK];
            int read;
            if (floats) {
                read = record.read(floatBuffer, 0, BLOCK, AudioRecord.READ_BLOCKING);
                System.arraycopy(floatBuffer, 0, block, 0, Math.max(read, 0));
            } else {
                read = record.read(shortBuffer, 0, BLOCK, AudioRecord.READ_BLOCKING);
                for (int i = 0; i < read; i++) {
                    block[i] = shortBuffer[i] / 32768f;
                }
            }
            if (read <= 0) {
                return;
            }
            if (!queue.offer(block)) {
                queue.poll();
                queue.offer(block);
            }
        }
    }

    static Thread capture(String name, int source, boolean floats, BlockingQueue<float[]> queue) {
        Thread thread = new Thread(() -> {
            try {
                pump(Capture.open(source, floats ? AudioFormat.ENCODING_PCM_FLOAT : AudioFormat.ENCODING_PCM_16BIT), floats, queue);
            } catch (Throwable error) {
                System.out.println(name + ": FAIL " + error + (error.getCause() != null ? " / " + error.getCause() : ""));
            }
            System.exit(3);
        }, name);
        thread.start();
        return thread;
    }

    static void send(String host, int port, String token, BlockingQueue<float[]> mic, BlockingQueue<float[]> ref) throws Exception {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(host, port), 5000);
            socket.setTcpNoDelay(true);
            OutputStream out = new BufferedOutputStream(socket.getOutputStream(), 1 << 16);
            out.write(("{\"token\":\"" + token + "\",\"device\":\"tv\",\"rate\":16000}\n").getBytes("UTF-8"));
            mic.clear();
            ref.clear();
            ByteBuffer frame = ByteBuffer.allocate(4 + BLOCK * 8).order(ByteOrder.LITTLE_ENDIAN);
            while (true) {
                float[] m = mic.take();
                float[] r = ref.take();
                frame.clear();
                frame.putInt(BLOCK * 8);
                for (float value : m) {
                    frame.putFloat(value);
                }
                for (float value : r) {
                    frame.putFloat(value);
                }
                out.write(frame.array(), 0, frame.position());
                out.flush();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        String host = args[0];
        int port = Integer.parseInt(args[1]);
        String token = args[2];
        BlockingQueue<float[]> mic = new ArrayBlockingQueue<>(QUEUE);
        BlockingQueue<float[]> ref = new ArrayBlockingQueue<>(QUEUE);
        capture("mic", 6, true, mic);
        capture("ref", 1997, false, ref);
        while (true) {
            try {
                send(host, port, token, mic, ref);
            } catch (Throwable error) {
                Thread.sleep(3000);
            }
        }
    }
}
