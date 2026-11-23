package com.bobassistant.tv;

import android.os.Handler;
import android.os.Looper;

import org.json.JSONException;
import org.json.JSONObject;

import java.util.concurrent.TimeUnit;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;
import okio.ByteString;

final class Link extends WebSocketListener {
    interface Callback {
        void onMessage(JSONObject message);

        void onAudio(byte[] pcm);

        void onConnected(boolean connected);
    }

    private final OkHttpClient client = new OkHttpClient.Builder()
            .pingInterval(15, TimeUnit.SECONDS)
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .build();
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final String url;
    private final String token;
    private final String device;
    private final Callback callback;
    private volatile WebSocket socket;
    private volatile boolean open;
    private volatile boolean stopped;
    private long backoff = 1000;
    private volatile String format;

    Link(String url, String token, String device, Callback callback) {
        this.url = url;
        this.token = token;
        this.device = device;
        this.callback = callback;
    }

    void start() {
        stopped = false;
        connect();
    }

    void stop() {
        stopped = true;
        handler.removeCallbacksAndMessages(null);
        WebSocket current = socket;
        if (current != null) {
            current.close(1000, "bye");
        }
        client.dispatcher().executorService().shutdown();
    }

    boolean isOpen() {
        return open;
    }

    void sendAudio(byte[] pcm, int length) {
        WebSocket current = socket;
        if (open && current != null && current.queueSize() < 256 * 1024) {
            current.send(ByteString.of(pcm, 0, length));
        }
    }

    void setFormat(JSONObject message) {
        format = message.toString();
        WebSocket current = socket;
        if (open && current != null) {
            current.send(format);
        }
    }

    void sendJson(JSONObject message) {
        WebSocket current = socket;
        if (open && current != null) {
            current.send(message.toString());
        }
    }

    private void connect() {
        if (stopped) {
            return;
        }
        socket = client.newWebSocket(new Request.Builder().url(url).build(), this);
    }

    private void retry() {
        open = false;
        callback.onConnected(false);
        if (stopped) {
            return;
        }
        handler.postDelayed(this::connect, backoff);
        backoff = Math.min(backoff * 2, 30000);
    }

    @Override
    public void onOpen(WebSocket webSocket, Response response) {
        try {
            webSocket.send(new JSONObject()
                    .put("type", "hello")
                    .put("device", device)
                    .put("token", token)
                    .put("rate", 16000)
                    .toString());
        } catch (JSONException ignored) {
            return;
        }
        String pending = format;
        if (pending != null) {
            webSocket.send(pending);
        }
        open = true;
        backoff = 1000;
        callback.onConnected(true);
    }

    @Override
    public void onMessage(WebSocket webSocket, String text) {
        try {
            callback.onMessage(new JSONObject(text));
        } catch (JSONException ignored) {
        }
    }

    @Override
    public void onMessage(WebSocket webSocket, ByteString bytes) {
        callback.onAudio(bytes.toByteArray());
    }

    @Override
    public void onClosed(WebSocket webSocket, int code, String reason) {
        if (webSocket == socket) {
            retry();
        }
    }

    @Override
    public void onFailure(WebSocket webSocket, Throwable t, Response response) {
        android.util.Log.w(VoiceService.TAG, "link failed: " + t + (response != null ? " http " + response.code() : ""));
        if (webSocket == socket) {
            retry();
        }
    }
}
