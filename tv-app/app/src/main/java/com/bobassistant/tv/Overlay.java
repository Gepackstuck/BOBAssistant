package com.bobassistant.tv;

import android.animation.ObjectAnimator;
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
import android.view.animation.LinearInterpolator;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

final class Overlay {
    private static final int[] TIMER = {Color.rgb(111, 168, 255), Color.rgb(181, 124, 255), Color.rgb(255, 127, 182)};

    private final Context context;
    private final WindowManager windows;
    private final Handler main = new Handler(Looper.getMainLooper());
    private FrameLayout root;
    private FrameLayout pill;
    private IndicatorView indicator;
    private TextView small;
    private TextView big;
    private FrameLayout timer;
    private View timerTrack;
    private View timerFill;
    private ObjectAnimator timerAnimation;
    private ValueAnimator fill;
    private String shownRequest = "";
    private String phase = "idle";
    private boolean attached;
    private final Runnable failsafe = () -> render("idle", "", "", "dark", 0f);

    Overlay(Context context) {
        this.context = context;
        this.windows = context.getSystemService(WindowManager.class);
    }

    void show(String phase, String request, String answer, boolean voice, String theme, float window) {
        main.post(() -> render(phase, request, answer, theme, window));
    }

    void destroy() {
        main.post(this::detach);
    }

    private float dp(float value) {
        return TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value, context.getResources().getDisplayMetrics());
    }

    private TextView text(float sp, boolean strong) {
        TextView view = new TextView(context);
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        view.setTypeface(strong ? Typeface.create(Typeface.DEFAULT, 600, false) : Typeface.DEFAULT);
        view.setLineSpacing(0, strong ? 1.1f : 1f);
        view.setMaxWidth((int) dp(430));
        view.setEllipsize(TextUtils.TruncateAt.END);
        view.setIncludeFontPadding(false);
        return view;
    }

    private void build() {
        pill = new FrameLayout(context);
        pill.setElevation(dp(18));
        pill.setClipToPadding(false);
        pill.setClipChildren(false);

        LinearLayout row = new LinearLayout(context);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.BOTTOM);
        row.setPadding((int) dp(26), (int) dp(18), (int) dp(26), (int) dp(20));
        row.setClipToPadding(false);
        row.setClipChildren(false);
        indicator = new IndicatorView(context);
        int size = (int) dp(54);
        LinearLayout.LayoutParams indicatorParams = new LinearLayout.LayoutParams(size, size);
        indicatorParams.setMargins((int) dp(-10), (int) dp(-10), (int) dp(2), (int) dp(-11));
        row.addView(indicator, indicatorParams);

        LinearLayout column = new LinearLayout(context);
        column.setOrientation(LinearLayout.VERTICAL);
        small = text(15, false);
        small.setMaxLines(1);
        big = text(24, true);
        big.setMaxLines(5);
        LinearLayout.LayoutParams bigParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        bigParams.topMargin = (int) dp(4);
        column.addView(small);
        column.addView(big, bigParams);
        row.addView(column);
        pill.addView(row);

        timer = new FrameLayout(context);
        timerTrack = new View(context);
        timerFill = new View(context);
        GradientDrawable fillShape = new GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT, TIMER);
        fillShape.setCornerRadius(dp(2));
        timerFill.setBackground(fillShape);
        timer.addView(timerTrack, new FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        timer.addView(timerFill, new FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        FrameLayout.LayoutParams timerParams = new FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, (int) dp(3), Gravity.BOTTOM);
        timerParams.setMargins((int) dp(26), 0, (int) dp(26), (int) dp(8));
        timer.setVisibility(View.GONE);
        pill.addView(timer, timerParams);

        pill.setAlpha(0f);
        root = new FrameLayout(context);
        root.setPadding(0, (int) dp(40), 0, (int) dp(40));
        root.setClipToPadding(false);
        root.setClipChildren(false);
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
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT);
        params.gravity = Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL;
        params.y = (int) dp(8);
        windows.addView(root, params);
        attached = true;
    }

    private void detach() {
        stopTimer();
        if (fill != null) {
            fill.cancel();
        }
        if (attached) {
            windows.removeViewImmediate(root);
            attached = false;
        }
        shownRequest = "";
        phase = "idle";
    }

    private void applyTheme(boolean light) {
        GradientDrawable card = new GradientDrawable();
        card.setCornerRadius(dp(32));
        card.setColor(light ? Color.argb(230, 255, 255, 255) : Color.argb(235, 18, 19, 24));
        card.setStroke((int) dp(1), light ? Color.argb(15, 0, 0, 0) : Color.argb(20, 255, 255, 255));
        pill.setBackground(card);
        timerTrack.setBackground(rounded(light ? Color.argb(20, 0, 0, 0) : Color.argb(26, 255, 255, 255)));
        small.setTextColor(light ? Color.argb(128, 20, 22, 30) : Color.argb(133, 255, 255, 255));
    }

    private GradientDrawable rounded(int color) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(color);
        shape.setCornerRadius(dp(2));
        return shape;
    }

    private void render(String next, String request, String answer, String theme, float window) {
        main.removeCallbacks(failsafe);
        if (!"idle".equals(next)) {
            main.postDelayed(failsafe, 30000);
        }
        if ("idle".equals(next)) {
            phase = "idle";
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
        boolean light = "light".equals(theme);
        applyTheme(light);
        int primary = light ? Color.rgb(21, 22, 27) : Color.WHITE;
        int secondary = light ? Color.argb(128, 20, 22, 30) : Color.argb(133, 255, 255, 255);
        boolean listening = "listening".equals(next);
        boolean thinking = "thinking".equals(next);
        String previousPhase = phase;
        phase = next;

        String smallText = listening ? context.getString(R.string.caption_listening) : request;
        small.setText(smallText);
        small.setVisibility(smallText.isEmpty() ? View.GONE : View.VISIBLE);

        if (listening) {
            if (request.isEmpty()) {
                setBig(context.getString(R.string.state_speak), "", primary);
                big.setTextColor(secondary);
            } else {
                setBig(request, shownRequest, primary);
                big.setTextColor(primary);
            }
            shownRequest = request;
        } else {
            if (fill != null) {
                fill.cancel();
            }
            big.setText(thinking ? context.getString(R.string.state_thinking) : answer);
            big.setTextColor(thinking ? secondary : primary);
        }
        indicator.setMode(listening ? IndicatorView.BARS : (thinking ? IndicatorView.SPIN : IndicatorView.BREATHE));
        boolean followup = "followup".equals(next) && window > 0;
        timer.setVisibility(followup ? View.VISIBLE : View.GONE);
        if (followup) {
            if (!"followup".equals(previousPhase)) {
                startTimer(window);
            }
        } else {
            stopTimer();
        }
        if (pill.getAlpha() < 1f) {
            pill.setTranslationY(dp(20));
            pill.animate().alpha(1f).translationY(0f).setDuration(220)
                    .setInterpolator(new DecelerateInterpolator()).start();
        }
    }

    private void startTimer(float seconds) {
        stopTimer();
        timerFill.setPivotX(0f);
        timerFill.setScaleX(1f);
        timerAnimation = ObjectAnimator.ofFloat(timerFill, View.SCALE_X, 1f, 0f);
        timerAnimation.setDuration((long) (seconds * 1000));
        timerAnimation.setInterpolator(new LinearInterpolator());
        timerAnimation.start();
    }

    private void stopTimer() {
        if (timerAnimation != null) {
            timerAnimation.cancel();
            timerAnimation = null;
        }
    }

    private void setBig(String text, String previous, int primary) {
        if (fill != null) {
            fill.cancel();
        }
        if (previous.isEmpty() || !text.startsWith(previous) || text.length() == previous.length()) {
            big.setText(text);
            return;
        }
        int split = previous.length();
        int red = Color.red(primary);
        int green = Color.green(primary);
        int blue = Color.blue(primary);
        fill = ValueAnimator.ofInt(0, 255);
        fill.setDuration(260);
        fill.addUpdateListener(animation -> {
            SpannableString spanned = new SpannableString(text);
            spanned.setSpan(new ForegroundColorSpan(Color.argb((int) animation.getAnimatedValue(), red, green, blue)),
                    split, text.length(), SpannableString.SPAN_EXCLUSIVE_EXCLUSIVE);
            big.setText(spanned);
        });
        fill.start();
    }
}
