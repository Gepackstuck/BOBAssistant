package com.bobassistant.tv;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.text.TextUtils;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.view.animation.DecelerateInterpolator;
import android.widget.LinearLayout;
import android.widget.TextView;

final class Overlay {
    private final Context context;
    private final WindowManager windows;
    private final Handler main = new Handler(Looper.getMainLooper());
    private LinearLayout pill;
    private View dot;
    private TextView label;
    private ValueAnimator pulse;
    private boolean attached;

    Overlay(Context context) {
        this.context = context;
        this.windows = context.getSystemService(WindowManager.class);
    }

    void show(String state, String text) {
        main.post(() -> render(state, text));
    }

    void destroy() {
        main.post(this::detach);
    }

    private float dp(float value) {
        return TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value, context.getResources().getDisplayMetrics());
    }

    private void build() {
        pill = new LinearLayout(context);
        pill.setOrientation(LinearLayout.HORIZONTAL);
        pill.setGravity(Gravity.CENTER_VERTICAL);
        int padH = (int) dp(26);
        int padV = (int) dp(16);
        pill.setPadding(padH, padV, padH, padV);
        GradientDrawable glass = new GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM,
                new int[]{Color.argb(205, 52, 54, 66), Color.argb(215, 22, 23, 30)});
        glass.setCornerRadius(dp(34));
        glass.setStroke((int) dp(1.5f), Color.argb(90, 255, 255, 255));
        pill.setBackground(glass);
        pill.setElevation(dp(12));

        dot = new View(context);
        GradientDrawable circle = new GradientDrawable();
        circle.setShape(GradientDrawable.OVAL);
        circle.setColors(new int[]{Color.rgb(255, 214, 64), Color.rgb(255, 150, 40)});
        dot.setBackground(circle);
        int size = (int) dp(18);
        LinearLayout.LayoutParams dotParams = new LinearLayout.LayoutParams(size, size);
        dotParams.rightMargin = (int) dp(16);
        pill.addView(dot, dotParams);

        label = new TextView(context);
        label.setTextColor(Color.WHITE);
        label.setTextSize(TypedValue.COMPLEX_UNIT_SP, 22);
        label.setTypeface(Typeface.create("sans-serif", Typeface.NORMAL));
        label.setMaxLines(4);
        label.setEllipsize(TextUtils.TruncateAt.END);
        label.setMaxWidth((int) dp(760));
        label.setLineSpacing(0, 1.12f);
        pill.addView(label);
        pill.setAlpha(0f);
    }

    private void attach() {
        if (attached || !Settings.canDrawOverlays(context)) {
            return;
        }
        if (pill == null) {
            build();
        }
        WindowManager.LayoutParams params = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT);
        params.gravity = Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL;
        params.y = (int) dp(48);
        windows.addView(pill, params);
        attached = true;
    }

    private void detach() {
        stopPulse();
        if (attached) {
            windows.removeViewImmediate(pill);
            attached = false;
        }
    }

    private void render(String state, String text) {
        main.removeCallbacksAndMessages(null);
        if ("idle".equals(state)) {
            if (attached) {
                pill.animate().alpha(0f).translationY(dp(20)).setDuration(260)
                        .withEndAction(this::detach).start();
            }
            return;
        }
        attach();
        if (!attached) {
            return;
        }
        switch (state) {
            case "listening":
                label.setText(R.string.state_listening);
                label.setAlpha(0.85f);
                startPulse(1.0f);
                break;
            case "followup":
                label.setText(R.string.state_followup);
                label.setAlpha(0.6f);
                startPulse(0.6f);
                break;
            case "heard":
                label.setText("«" + text + "»");
                label.setAlpha(0.75f);
                startPulse(0.4f);
                break;
            default:
                label.setText(text);
                label.setAlpha(1f);
                stopPulse();
                dot.setScaleX(1f);
                dot.setScaleY(1f);
                break;
        }
        if (pill.getAlpha() < 1f) {
            pill.setTranslationY(dp(20));
            pill.animate().alpha(1f).translationY(0f).setDuration(220)
                    .setInterpolator(new DecelerateInterpolator()).start();
        }
    }

    private void startPulse(float strength) {
        stopPulse();
        pulse = ValueAnimator.ofFloat(0f, 1f);
        pulse.setDuration(900);
        pulse.setRepeatCount(ValueAnimator.INFINITE);
        pulse.setRepeatMode(ValueAnimator.REVERSE);
        pulse.addUpdateListener(animation -> {
            float scale = 1f + 0.35f * strength * (float) animation.getAnimatedValue();
            dot.setScaleX(scale);
            dot.setScaleY(scale);
        });
        pulse.start();
    }

    private void stopPulse() {
        if (pulse != null) {
            pulse.cancel();
            pulse = null;
        }
    }
}
