package com.bobassistant.tv;

import android.animation.ObjectAnimator;
import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.PixelFormat;
import android.graphics.RadialGradient;
import android.graphics.Rect;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.text.SpannableString;
import android.text.TextUtils;
import android.text.style.ForegroundColorSpan;
import android.util.DisplayMetrics;
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
    private static final String PLATE = "plate";
    private static final String CORNER = "corner";
    private static final int[] TIMER = {Color.rgb(111, 168, 255), Color.rgb(181, 124, 255), Color.rgb(255, 127, 182)};
    private static final float CORNER_WIDTH_SHARE = 0.95f;
    private static final float CORNER_HEIGHT_SHARE = 0.72f;
    private static final float CORNER_LEFT_DP = 56f;
    private static final float CORNER_BOTTOM_DP = 30f;

    private final Context context;
    private final WindowManager windows;
    private final Handler main = new Handler(Looper.getMainLooper());
    private FrameLayout root;
    private FrameLayout pill;
    private IndicatorView indicator;
    private TextView small;
    private TextView big;
    private View timer;
    private View timerTrack;
    private View timerFill;
    private ObjectAnimator timerAnimation;
    private ValueAnimator fill;
    private String builtStyle = PLATE;
    private String shownRequest = "";
    private String phase = "idle";
    private boolean attached;
    private final Runnable failsafe = () -> render("idle", "", "", true, "dark", builtStyle, 0f);

    Overlay(Context context) {
        this.context = context;
        this.windows = context.getSystemService(WindowManager.class);
    }

    void show(String phase, String request, String answer, boolean voice, String theme, String style, float window) {
        main.post(() -> render(phase, request, answer, voice, theme, style, window));
    }

    void destroy() {
        main.post(this::detach);
    }

    private float dp(float value) {
        return TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value, context.getResources().getDisplayMetrics());
    }

    private boolean corner() {
        return CORNER.equals(builtStyle);
    }

    private int cornerWidth() {
        return (int) (context.getResources().getDisplayMetrics().widthPixels * CORNER_WIDTH_SHARE);
    }

    private int cornerHeight() {
        DisplayMetrics metrics = context.getResources().getDisplayMetrics();
        return (int) (metrics.heightPixels * CORNER_HEIGHT_SHARE);
    }

    private TextView text(float sp, boolean strong, int maxWidthDp, boolean shadow) {
        TextView view = new TextView(context);
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        view.setTypeface(strong ? Typeface.create(Typeface.DEFAULT, 600, false) : Typeface.DEFAULT);
        view.setLineSpacing(0, strong ? 1.1f : 1f);
        view.setMaxWidth((int) dp(maxWidthDp));
        view.setEllipsize(TextUtils.TruncateAt.END);
        view.setIncludeFontPadding(false);
        if (shadow) {
            view.setShadowLayer(dp(8), 0, dp(1), Color.argb(200, 0, 0, 0));
        }
        return view;
    }

    private GradientDrawable rounded(int color) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(color);
        shape.setCornerRadius(dp(2));
        return shape;
    }

    private View timerView(int trackColor) {
        FrameLayout bar = new FrameLayout(context);
        timerTrack = new View(context);
        timerFill = new View(context);
        GradientDrawable fillShape = new GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT, TIMER);
        fillShape.setCornerRadius(dp(2));
        timerFill.setBackground(fillShape);
        timerTrack.setBackground(rounded(trackColor));
        bar.addView(timerTrack, new FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        bar.addView(timerFill, new FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        return bar;
    }

    private void buildPlate() {
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
        small = text(15, false, 430, false);
        small.setMaxLines(1);
        big = text(24, true, 430, false);
        big.setMaxLines(5);
        LinearLayout.LayoutParams bigParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        bigParams.topMargin = (int) dp(4);
        column.addView(small);
        column.addView(big, bigParams);
        row.addView(column);

        timer = timerView(Color.argb(26, 255, 255, 255));
        LinearLayout content = new LinearLayout(context);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setClipToPadding(false);
        content.setClipChildren(false);
        content.addView(row, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT));
        LinearLayout.LayoutParams timerParams = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, (int) dp(3));
        timerParams.setMargins((int) dp(26), (int) dp(-11), (int) dp(26), (int) dp(8));
        timer.setVisibility(View.GONE);
        content.addView(timer, timerParams);
        pill.addView(content);

        root = new FrameLayout(context);
        root.setPadding(0, (int) dp(40), 0, (int) dp(40));
        root.setClipToPadding(false);
        root.setClipChildren(false);
        root.addView(pill, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL));
        root.setAlpha(0f);
    }

    private static final float SCRIM_PLATEAU = 0.52f;
    private static final int SCRIM_STEPS = 16;
    private static final int[] SCRIM_COLORS = new int[SCRIM_STEPS + 1];
    private static final float[] SCRIM_STOPS = new float[SCRIM_STEPS + 1];

    static {
        for (int i = 0; i <= SCRIM_STEPS; i++) {
            float position = SCRIM_PLATEAU + (1f - SCRIM_PLATEAU) * i / SCRIM_STEPS;
            float t = (float) i / SCRIM_STEPS;
            float eased = 1f - (3f * t * t - 2f * t * t * t);
            SCRIM_STOPS[i] = position;
            SCRIM_COLORS[i] = Color.argb(Math.round(255 * eased), 0, 0, 0);
        }
        SCRIM_STOPS[0] = SCRIM_PLATEAU;
    }

    private static final class Scrim extends Drawable {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);

        @Override
        public void draw(Canvas canvas) {
            Rect bounds = getBounds();
            float width = bounds.width();
            float height = bounds.height();
            if (width <= 0 || height <= 0) {
                return;
            }
            paint.setShader(new RadialGradient(0, 0, width, SCRIM_COLORS, SCRIM_STOPS, Shader.TileMode.CLAMP));
            canvas.save();
            canvas.translate(bounds.left, bounds.bottom);
            canvas.scale(1f, height / width);
            canvas.drawRect(0, -width, width, 0, paint);
            canvas.restore();
        }

        @Override
        public void setAlpha(int alpha) {
        }

        @Override
        public void setColorFilter(android.graphics.ColorFilter filter) {
        }

        @Override
        public int getOpacity() {
            return PixelFormat.TRANSLUCENT;
        }
    }

    private Drawable scrim() {
        return new Scrim();
    }

    private void buildCorner() {
        LinearLayout row = new LinearLayout(context);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.BOTTOM);
        row.setClipChildren(false);
        row.setClipToPadding(false);

        indicator = new IndicatorView(context);
        int size = (int) dp(64);
        LinearLayout.LayoutParams indicatorParams = new LinearLayout.LayoutParams(size, size);
        indicatorParams.setMargins((int) dp(-8), 0, (int) dp(8), (int) dp(-14));
        row.addView(indicator, indicatorParams);

        LinearLayout column = new LinearLayout(context);
        column.setOrientation(LinearLayout.VERTICAL);
        small = text(17, false, 560, true);
        small.setMaxLines(1);
        big = text(30, true, 560, true);
        big.setMaxLines(5);
        LinearLayout.LayoutParams bigParams = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        bigParams.topMargin = (int) dp(6);
        column.addView(small);
        column.addView(big, bigParams);
        row.addView(column);

        timer = timerView(Color.argb(60, 255, 255, 255));
        LinearLayout content = new LinearLayout(context);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setClipChildren(false);
        content.setClipToPadding(false);
        content.addView(row, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT));
        LinearLayout.LayoutParams timerParams = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, (int) dp(3));
        timerParams.setMargins((int) dp(64), (int) dp(14), 0, 0);
        timer.setVisibility(View.INVISIBLE);
        content.addView(timer, timerParams);

        root = new FrameLayout(context);
        root.setClipChildren(false);
        root.setClipToPadding(false);
        root.setBackground(scrim());
        FrameLayout.LayoutParams contentParams = new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT, FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM | Gravity.START);
        contentParams.leftMargin = (int) dp(CORNER_LEFT_DP);
        contentParams.bottomMargin = (int) dp(CORNER_BOTTOM_DP);
        root.addView(content, contentParams);
        root.setAlpha(0f);
    }

    private void build() {
        if (corner()) {
            buildCorner();
        } else {
            buildPlate();
        }
    }

    private void attach() {
        if (attached || !Settings.canDrawOverlays(context)) {
            return;
        }
        if (root == null) {
            build();
        }
        WindowManager.LayoutParams params;
        if (corner()) {
            params = new WindowManager.LayoutParams(
                    cornerWidth(), cornerHeight(), WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                    PixelFormat.TRANSLUCENT);
            params.gravity = Gravity.BOTTOM | Gravity.START;
        } else {
            params = new WindowManager.LayoutParams(
                    WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.WRAP_CONTENT,
                    WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                    PixelFormat.TRANSLUCENT);
            params.gravity = Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL;
            params.y = (int) dp(8);
        }
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

    private void applyPlateTheme(boolean light) {
        GradientDrawable card = new GradientDrawable();
        card.setCornerRadius(dp(32));
        card.setColor(light ? Color.argb(230, 255, 255, 255) : Color.argb(235, 18, 19, 24));
        card.setStroke((int) dp(1), light ? Color.argb(15, 0, 0, 0) : Color.argb(20, 255, 255, 255));
        pill.setBackground(card);
        timerTrack.setBackground(rounded(light ? Color.argb(20, 0, 0, 0) : Color.argb(26, 255, 255, 255)));
    }

    private void render(String next, String request, String answer, boolean voice, String theme, String style, float window) {
        main.removeCallbacks(failsafe);
        if (!"idle".equals(next)) {
            main.postDelayed(failsafe, 30000);
        }
        String wanted = CORNER.equals(style) ? CORNER : PLATE;
        if (!wanted.equals(builtStyle)) {
            detach();
            root = null;
            builtStyle = wanted;
        }
        if ("idle".equals(next)) {
            phase = "idle";
            if (attached) {
                root.animate().alpha(0f).translationY(dp(20)).setDuration(260)
                        .withEndAction(this::detach).start();
            }
            return;
        }
        attach();
        if (!attached) {
            return;
        }
        root.animate().cancel();
        boolean light = !corner() && "light".equals(theme);
        int primary = light ? Color.rgb(21, 22, 27) : Color.WHITE;
        int secondary = light ? Color.argb(128, 20, 22, 30) : Color.argb(corner() ? 220 : 133, 255, 255, 255);
        if (!corner()) {
            applyPlateTheme(light);
        }
        small.setTextColor(secondary);
        boolean listening = "listening".equals(next);
        boolean thinking = "thinking".equals(next);
        boolean speaking = "answer".equals(next) && voice;
        String previousPhase = phase;
        phase = next;

        String smallText = listening ? context.getString(R.string.caption_listening) : request;
        small.setText(smallText);
        small.setVisibility(smallText.isEmpty() ? (corner() ? View.INVISIBLE : View.GONE) : View.VISIBLE);

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
        indicator.setMode(listening ? IndicatorView.BARS
                : (thinking ? IndicatorView.SPIN : (speaking ? IndicatorView.SPEAK : IndicatorView.BREATHE)));
        boolean followup = "followup".equals(next) && window > 0;
        timer.setVisibility(followup ? View.VISIBLE : (corner() ? View.INVISIBLE : View.GONE));
        if (followup) {
            if (!"followup".equals(previousPhase)) {
                startTimer(window);
            }
        } else {
            stopTimer();
        }
        if (root.getAlpha() < 1f) {
            root.setTranslationY(dp(20));
            root.animate().alpha(1f).translationY(0f).setDuration(240)
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
