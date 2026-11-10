package edu.cs211.projectb;

import android.app.*;
import android.content.*;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.drawable.GradientDrawable;
import android.os.*;
import android.provider.Settings;
import android.view.*;
import android.widget.*;
import org.json.JSONObject;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** User-enabled, recording-only overlay; independent of WebView background timers. */
public final class FloatingMarkersService extends Service {
    private static volatile String activeRun = "";
    private static final int NOTICE = 212;
    private static final String CHANNEL = "floating_marker_service";
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private WindowManager windows;
    private WindowManager.LayoutParams position;
    private LinearLayout bubble, panel;
    private TextView status;
    private String run = "", origin, token;
    private long deadline;
    private boolean destroyed, checking;

    public static boolean runningFor(String id) { return id.equals(activeRun); }
    @Override public IBinder onBind(Intent intent) { return null; }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null || !Settings.canDrawOverlays(this)) { stopSelf(); return START_NOT_STICKY; }
        String id = intent.getStringExtra("run");
        if (id == null || !id.matches("[0-9a-f]{32}")) { stopSelf(); return START_NOT_STICKY; }
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel(CHANNEL, "Floating experiment controls",
                NotificationManager.IMPORTANCE_LOW));
        PendingIntent open = PendingIntent.getActivity(this, 212, new Intent(this, MainActivity.class),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        startForeground(NOTICE, new Notification.Builder(this, CHANNEL)
                .setSmallIcon(android.R.drawable.ic_menu_recent_history)
                .setContentTitle("Project B floating markers")
                .setContentText("Tap the right-side dot for task markers")
                .setContentIntent(open).setOngoing(true).setOnlyAlertOnce(true).build());
        if (id.equals(run)) return START_NOT_STICKY;
        run = id; activeRun = id;
        origin = intent.getStringExtra("origin"); token = intent.getStringExtra("token");
        deadline = SystemClock.elapsedRealtime() + 1000L * (Math.max(5, Math.min(180,
                intent.getIntExtra("duration", 90))) + 15);
        removeBubble();
        try { showBubble(intent.getStringExtra("workload")); }
        catch (RuntimeException error) {
            Toast.makeText(this, "Could not show floating controls. Check overlay permission.", Toast.LENGTH_LONG).show();
            stopSelf(); return START_NOT_STICKY;
        }
        main.removeCallbacks(tick); main.post(tick);
        return START_NOT_STICKY;
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private GradientDrawable background(int color, int radius) {
        GradientDrawable shape = new GradientDrawable(); shape.setColor(color); shape.setCornerRadius(dp(radius));
        return shape;
    }
    private void showBubble(String workload) {
        windows = getSystemService(WindowManager.class);
        bubble = new LinearLayout(this); bubble.setOrientation(LinearLayout.VERTICAL);
        bubble.setGravity(Gravity.RIGHT); bubble.setPadding(dp(4), dp(4), dp(4), dp(4));
        TextView dot = new TextView(this);
        dot.setText("●"); dot.setTextColor(Color.LTGRAY); dot.setTextSize(28); dot.setGravity(Gravity.CENTER);
        dot.setBackground(background(0xE6222222, 28)); dot.setElevation(dp(5));
        dot.setContentDescription("Project B: expand or collapse task markers; drag to move");
        bubble.addView(dot, new LinearLayout.LayoutParams(dp(56), dp(56)));
        panel = new LinearLayout(this); panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(10), dp(8), dp(10), dp(8)); panel.setBackground(background(0xF5222222, 16));
        status = new TextView(this); status.setText("Recording · " + workload); status.setTextColor(Color.WHITE);
        panel.addView(status);
        String[] labels;
        if ("W0".equals(workload)) labels = new String[]{"idle_start", "idle_end", "unexpected_activity"};
        else if ("W1".equals(workload)) labels = new String[]{"prompt_submitted", "confirmation", "browser_launched"};
        else if ("W2".equals(workload)) labels = new String[]{"voice_start", "voice_end", "response_complete"};
        else throw new IllegalArgumentException("Unknown workload");
        for (String label : labels) {
            Button button = new Button(this); button.setText(label.replace('_', ' ')); button.setAllCaps(false);
            button.setOnClickListener(view -> {
                sendBroadcast(new Intent(this, MarkerReceiver.class)
                        .putExtra("url", origin + "/api/runs/" + run + "/markers")
                        .putExtra("token", token).putExtra("label", label));
                panel.setVisibility(View.GONE); // Never take focus away from the Agent/browser.
            });
            panel.addView(button, new LinearLayout.LayoutParams(-1, dp(48)));
        }
        bubble.addView(panel, new LinearLayout.LayoutParams(dp(220), -2)); panel.setVisibility(View.GONE);
        position = new WindowManager.LayoutParams(-2, -2, WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE, PixelFormat.TRANSLUCENT);
        position.gravity = Gravity.TOP | Gravity.RIGHT;
        position.x = dp(12); position.y = getResources().getDisplayMetrics().heightPixels / 3;
        dot.setOnClickListener(view -> {
            panel.setVisibility(panel.getVisibility() == View.VISIBLE ? View.GONE : View.VISIBLE);
            clampPosition(); windows.updateViewLayout(bubble, position);
        });
        dot.setOnTouchListener(new View.OnTouchListener() {
            float downX, downY; int oldX, oldY; boolean moved;
            @Override public boolean onTouch(View view, android.view.MotionEvent event) {
                if (event.getAction() == MotionEvent.ACTION_DOWN) {
                    downX = event.getRawX(); downY = event.getRawY(); oldX = position.x; oldY = position.y; moved = false;
                    return true;
                }
                if (event.getAction() == MotionEvent.ACTION_MOVE) {
                    float dx = event.getRawX() - downX, dy = event.getRawY() - downY;
                    if (Math.abs(dx) + Math.abs(dy) > dp(8)) moved = true;
                    if (moved) { position.x = oldX - (int) dx; position.y = oldY + (int) dy;
                        clampPosition(); windows.updateViewLayout(bubble, position); }
                    return true;
                }
                if (event.getAction() == MotionEvent.ACTION_UP) { if (!moved) view.performClick(); return true; }
                return true;
            }
        });
        windows.addView(bubble, position);
    }

    private void clampPosition() {
        int width = getResources().getDisplayMetrics().widthPixels;
        int height = getResources().getDisplayMetrics().heightPixels;
        boolean expanded = panel.getVisibility() == View.VISIBLE;
        position.x = Math.max(0, Math.min(position.x, width - dp(expanded ? 232 : 64)));
        position.y = Math.max(0, Math.min(position.y, height - dp(expanded ? 290 : 110)));
    }

    private final Runnable tick = new Runnable() {
        @Override public void run() {
            if (destroyed) return;
            if (!Settings.canDrawOverlays(FloatingMarkersService.this) || SystemClock.elapsedRealtime() >= deadline) {
                stopSelf(); return;
            }
            if (!checking) {
                checking = true;
                final String expected = run, endpoint = origin + "/api/runs/" + run, auth = token;
                network.execute(() -> {
                    String state = null;
                    HttpURLConnection connection = null;
                    try {
                        connection = (HttpURLConnection) new URL(endpoint).openConnection();
                        connection.setConnectTimeout(3000); connection.setReadTimeout(3000);
                        connection.setInstanceFollowRedirects(false);
                        connection.setRequestProperty("Authorization", "Bearer " + auth);
                        int code = connection.getResponseCode();
                        if (code == 401 || code == 404) state = "failed";
                        else if (code == 200) {
                            try (var input = connection.getInputStream()) {
                                java.io.ByteArrayOutputStream bytes = new java.io.ByteArrayOutputStream();
                                byte[] buffer = new byte[8192]; int count;
                                while ((count = input.read(buffer)) != -1) bytes.write(buffer, 0, count);
                                state = new JSONObject(bytes.toString("UTF-8")).getString("status");
                            }
                        }
                    } catch (Exception ignored) { /* Retry; show loss of connection instead of inventing state. */ }
                    finally { if (connection != null) connection.disconnect(); }
                    final String result = state;
                    main.post(() -> {
                        checking = false;
                        if (destroyed || !run.equals(expected)) return;
                        if (result != null && !"recording".equals(result)) { stopSelf(); return; }
                        status.setText(result == null ? "Connection unavailable · retrying" : "Recording · tap an event");
                        for (int i = 1; i < panel.getChildCount(); i++) panel.getChildAt(i).setEnabled(result != null);
                    });
                });
            }
            main.postDelayed(this, 2000);
        }
    };

    private void removeBubble() {
        if (bubble != null && windows != null) {
            try { windows.removeView(bubble); } catch (IllegalArgumentException ignored) { }
            bubble = null;
        }
    }
    @Override public void onConfigurationChanged(android.content.res.Configuration config) {
        super.onConfigurationChanged(config);
        if (bubble != null) { clampPosition(); windows.updateViewLayout(bubble, position); }
    }
    @Override public void onDestroy() {
        destroyed = true; if (run.equals(activeRun)) activeRun = "";
        main.removeCallbacksAndMessages(null); network.shutdownNow(); removeBubble();
        stopForeground(STOP_FOREGROUND_REMOVE); super.onDestroy();
    }
}
