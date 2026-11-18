package com.bobassistant.tv;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.RadialGradient;
import android.graphics.RectF;
import android.graphics.Shader;
import android.graphics.SweepGradient;
import android.os.SystemClock;
import android.view.View;
import android.view.animation.LinearInterpolator;

final class IndicatorView extends View {
    static final int BARS = 0;
    static final int SPIN = 1;
    static final int BREATHE = 2;

    private static final int[] ACCENT = {
            Color.rgb(111, 168, 255), Color.rgb(181, 124, 255), Color.rgb(255, 127, 182),
            Color.rgb(255, 179, 111), Color.rgb(111, 168, 255)};
    private static final float[] BAR_HEIGHTS = {10, 20, 13, 24, 11};

    private final Paint orb = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint glow = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint bar = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF rect = new RectF();
    private final ValueAnimator ticker = ValueAnimator.ofFloat(0f, 1f);
    private int mode = BREATHE;

    IndicatorView(Context context) {
        super(context);
        ticker.setDuration(1000);
        ticker.setRepeatCount(ValueAnimator.INFINITE);
        ticker.setInterpolator(new LinearInterpolator());
        ticker.addUpdateListener(animation -> invalidate());
    }

    void setMode(int next) {
        mode = next;
        invalidate();
    }

    @Override
    protected void onAttachedToWindow() {
        super.onAttachedToWindow();
        ticker.start();
    }

    @Override
    protected void onDetachedFromWindow() {
        ticker.cancel();
        super.onDetachedFromWindow();
    }

    @Override
    protected void onDraw(Canvas canvas) {
        float cx = getWidth() / 2f;
        float cy = getHeight() / 2f;
        float size = Math.min(getWidth(), getHeight()) / 1.8f;
        float t = (SystemClock.uptimeMillis() % 600000L) / 1000f;
        if (mode == BARS) {
            drawBars(canvas, cx, cy, size, t);
            return;
        }
        float scale = 1f;
        float angle = 0f;
        if (mode == BREATHE) {
            scale = 1.07f + 0.07f * (float) Math.sin(2 * Math.PI * t / 3f - Math.PI / 2);
        } else {
            angle = -360f * ((t / 1.4f) % 1f);
        }
        float radius = size / 2f * scale;
        float reach = Math.min(getWidth(), getHeight()) / 2f;
        glow.setShader(new RadialGradient(cx, cy, reach,
                new int[]{Color.argb((int) (150 * scale / 1.14f), 181, 124, 255), Color.argb(70, 181, 124, 255), Color.argb(0, 181, 124, 255)},
                new float[]{0.45f, 0.7f, 1f}, Shader.TileMode.CLAMP));
        canvas.drawCircle(cx, cy, reach, glow);
        canvas.save();
        canvas.rotate(angle - 90f, cx, cy);
        SweepGradient sweep = new SweepGradient(cx, cy, ACCENT, new float[]{0f, 0.25f, 0.5f, 0.75f, 1f});
        orb.setShader(sweep);
        canvas.drawCircle(cx, cy, radius, orb);
        canvas.restore();
    }

    private void drawBars(Canvas canvas, float cx, float cy, float size, float t) {
        float unit = size / 26f;
        float width = 3.5f * unit;
        float gap = 3f * unit;
        float total = BAR_HEIGHTS.length * width + (BAR_HEIGHTS.length - 1) * gap;
        for (int i = 0; i < BAR_HEIGHTS.length; i++) {
            double wave = 0.5 + 0.5 * Math.sin(2 * Math.PI * (t / 0.9f) - i * 0.9);
            float height = BAR_HEIGHTS[i] * unit * (0.4f + 0.6f * (float) wave);
            float left = cx - total / 2f + i * (width + gap);
            bar.setShader(new LinearGradient(0, cy - height / 2f, 0, cy + height / 2f,
                    Color.rgb(139, 182, 255), Color.rgb(197, 139, 255), Shader.TileMode.CLAMP));
            rect.set(left, cy - height / 2f, left + width, cy + height / 2f);
            canvas.drawRoundRect(rect, width / 2f, width / 2f, bar);
        }
    }
}
