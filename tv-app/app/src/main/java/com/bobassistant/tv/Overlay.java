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
import android.text.SpannableString;
import android.text.TextUtils;
import android.text.style.ForegroundColorSpan;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.view.animation.DecelerateInterpolator;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

final class Overlay {
    private final Context context;
    private final WindowManager windows;
    private final Handler main = new Handler(Looper.getMainLooper());
    private FrameLayout root;
    private LinearLayout pill;
    private View dot;
    private GradientDrawable dotShape;
    private TextView request;
    private View divider;
    private TextView answer;
    private TextView hint;
    private ValueAnimator pulse;
    private ValueAnimator fill;
    private String shownRequest = "";
    private boolean attached;

    Overlay(Context context) {
        this.context = context;
        this.windows = context.getSystemService(WindowManager.class);
    }

    void show(String phase, String requestText, String answerText, boolean voice) {
        main.post(() -> render(phase, requestText, answerText, voice));
    }

    void destroy() {
        main.post(this::detach);
    }

    private float dp(float value) {
        return TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value, context.getResources().getDisplayMetrics());
    }

    private TextView text(float sp, int alpha) {
        TextView view = new TextView(context);
        view.setTextColor(Color.argb(alpha, 255, 255, 255));
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        view.setTypeface(Typeface.create("sans-serif", Typeface.NORMAL));
        view.setLineSpacing(0, 1.12f);
        view.setMaxWidth((int) dp(760));
        view.setEllipsize(TextUtils.TruncateAt.END);
        return view;
    }

    private void build() {
        pill = new LinearLayout(context);
        pill.setOrientation(LinearLayout.VERTICAL);
        int padH = (int) dp(26);
        int padV = (int) dp(16);
        pill.setPadding(padH, padV, padH, padV);
        GradientDrawable glass = new GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM,
                new int[]{Color.argb(245, 52, 54, 66), Color.argb(250, 22, 23, 30)});
        glass.setCornerRadius(dp(30));
        glass.setStroke((int) dp(1.5f), Color.argb(90, 255, 255, 255));
        pill.setBackground(glass);
        pill.setElevation(dp(12));

        LinearLayout row = new LinearLayout(context);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        dot = new View(context);
        dotShape = new GradientDrawable();
        dotShape.setShape(GradientDrawable.OVAL);
        dot.setBackground(dotShape);
        int size = (int) dp(16);
        LinearLayout.LayoutParams dotParams = new LinearLayout.LayoutParams(size, size);
        dotParams.rightMargin = (int) dp(14);
        row.addView(dot, dotParams);
        request = text(20, 255);
        request.setMaxLines(2);
        row.addView(request);
        pill.addView(row);

        divider = new View(context);
        divider.setBackgroundColor(Color.argb(46, 255, 255, 255));
        LinearLayout.LayoutParams line = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, (int) dp(1));
        line.topMargin = (int) dp(12);
        line.bottomMargin = (int) dp(12);
        divider.setVisibility(View.GONE);
        pill.addView(divider, line);

        answer = text(24, 255);
        answer.setMaxLines(5);
        answer.setVisibility(View.GONE);
        pill.addView(answer);

        hint = text(14, 120);
        hint.setText(R.string.state_followup);
        hint.setVisibility(View.GONE);
        LinearLayout.LayoutParams hintParams = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        hintParams.topMargin = (int) dp(8);
        pill.addView(hint, hintParams);
        pill.setAlpha(0f);
        root = new FrameLayout(context);
        root.addView(pill, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL));
    }

    private void attach() {
        if (attached || !Settings.canDrawOverlays(context)) {
            return;
        }
        if (pill == null) {
            build();
        }
        WindowManager.LayoutParams params = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT);
        params.alpha = 0.8f;
        params.gravity = Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL;
        params.y = (int) dp(48);
        windows.addView(root, params);
        attached = true;
    }

    private void detach() {
        stopPulse();
        if (fill != null) {
            fill.cancel();
        }
        if (attached) {
            windows.removeViewImmediate(root);
            attached = false;
        }
        shownRequest = "";
    }

    private void render(String phase, String requestText, String answerText, boolean voice) {
        if ("idle".equals(phase)) {
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
        pill.animate().cancel();
        boolean listening = "listening".equals(phase);
        boolean thinking = "thinking".equals(phase);
        boolean done = "answer".equals(phase) || "followup".equals(phase);

        if (requestText.isEmpty()) {
            if (fill != null) {
                fill.cancel();
            }
            shownRequest = "";
            request.setText(listening ? context.getString(R.string.state_listening) : "");
            request.setAlpha(0.6f);
        } else {
            setRequest(requestText);
            request.setAlpha(done ? 0.66f : 1f);
        }

        boolean showAnswer = done || thinking;
        divider.setVisibility(showAnswer ? View.VISIBLE : View.GONE);
        answer.setVisibility(showAnswer ? View.VISIBLE : View.GONE);
        answer.setText(done ? answerText : context.getString(R.string.state_thinking));
        answer.setAlpha(done ? 1f : 0.5f);
        hint.setVisibility("followup".equals(phase) ? View.VISIBLE : View.GONE);

        int[] colors = "followup".equals(phase)
                ? new int[]{Color.rgb(120, 230, 160), Color.rgb(40, 180, 110)}
                : new int[]{Color.rgb(255, 214, 64), Color.rgb(255, 150, 40)};
        dotShape.setColors(colors);
        if (listening) {
            startPulse(1.0f);
        } else if (thinking) {
            startPulse(0.5f);
        } else {
            stopPulse();
            dot.setScaleX(1f);
            dot.setScaleY(1f);
        }
        if (pill.getAlpha() < 1f) {
            pill.setTranslationY(dp(20));
            pill.animate().alpha(1f).translationY(0f).setDuration(220)
                    .setInterpolator(new DecelerateInterpolator()).start();
        }
    }

    private void setRequest(String text) {
        String previous = shownRequest;
        shownRequest = text;
        if (fill != null) {
            fill.cancel();
        }
        if (previous.isEmpty() || !text.startsWith(previous) || text.length() == previous.length()) {
            request.setText(text);
            return;
        }
        int split = previous.length();
        fill = ValueAnimator.ofInt(0, 255);
        fill.setDuration(260);
        fill.addUpdateListener(animation -> {
            SpannableString spanned = new SpannableString(text);
            spanned.setSpan(new ForegroundColorSpan(Color.argb((int) animation.getAnimatedValue(), 255, 255, 255)),
                    split, text.length(), SpannableString.SPAN_EXCLUSIVE_EXCLUSIVE);
            request.setText(spanned);
        });
        fill.start();
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
