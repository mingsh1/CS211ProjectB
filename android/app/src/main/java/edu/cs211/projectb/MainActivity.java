package edu.cs211.projectb;

import android.Manifest;
import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.ViewGroup;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.Toast;

import java.net.URI;
import org.json.JSONArray;
import org.json.JSONObject;

public final class MainActivity extends Activity {
    private static final int NOTIFICATION_ID = 211;
    private static final String CHANNEL = "experiment_alerts_v2";
    private String origin;
    private WebView web;
    private String notificationRun = "";
    private String exportPath;
    private String exportToken;
    private String exportOrigin;

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (savedInstanceState != null && savedInstanceState.getString("origin") != null) {
            exportPath = savedInstanceState.getString("exportPath");
            exportToken = savedInstanceState.getString("exportToken");
            exportOrigin = savedInstanceState.getString("exportOrigin");
            open(savedInstanceState.getString("origin"));
        } else {
            showConnect();
        }
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        if (web != null) state.putString("origin", origin);
        state.putString("exportPath", exportPath);
        state.putString("exportToken", exportToken);
        state.putString("exportOrigin", exportOrigin);
        super.onSaveInstanceState(state);
    }

    @Override protected void onDestroy() {
        if (web != null) {
            web.removeJavascriptInterface("ProjectB");
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }

    private void showConnect() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(24, 32, 24, 16);
        EditText address = new EditText(this);
        address.setSingleLine();
        address.setHint("http://192.168.1.10:8765");
        address.setText(getPreferences(MODE_PRIVATE).getString("origin", ""));
        Button connect = new Button(this);
        connect.setText("Open laptop backend");
        layout.addView(address);
        layout.addView(connect);
        setContentView(layout);
        connect.setOnClickListener(view -> {
            try {
                URI url = URI.create(address.getText().toString().trim());
                if (!("http".equals(url.getScheme()) || "https".equals(url.getScheme()))
                        || url.getHost() == null || url.getUserInfo() != null
                        || url.getQuery() != null || url.getFragment() != null
                        || !url.getPath().matches("/?")) {
                    throw new IllegalArgumentException();
                }
                open(url.getScheme() + "://" + url.getRawAuthority());
            } catch (IllegalArgumentException error) {
                toast("Enter the laptop address, including http:// and the port.");
            }
        });
    }

    private void open(String address) {
        origin = address;
        configureNotificationChannel();
        getPreferences(MODE_PRIVATE).edit().putString("origin", address).apply();
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 10);
        }
        web = new WebView(this);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setAllowFileAccess(false);
        web.getSettings().setAllowContentAccess(false);
        web.addJavascriptInterface(new Bridge(), "ProjectB");
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                return !url.equals(origin + "/");
            }
        });
        web.setLayoutParams(new ViewGroup.LayoutParams(-1, -1));
        setContentView(web);
        web.loadUrl(origin + "/");
    }

    @Override public void onBackPressed() {
        if (web == null) {
            super.onBackPressed();
            return;
        }
        web.removeJavascriptInterface("ProjectB");
        web.destroy();
        web = null;
        showConnect();
    }

    private void toast(String message) {
        runOnUiThread(() -> Toast.makeText(this, message, Toast.LENGTH_LONG).show());
    }

    private final class Bridge {
        @JavascriptInterface public boolean floatingMarkersEnabled() {
            return android.provider.Settings.canDrawOverlays(MainActivity.this);
        }

        @JavascriptInterface public void floatingMarkerSettings() {
            runOnUiThread(() -> {
                try {
                    startActivity(new Intent(android.provider.Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                            android.net.Uri.parse("package:" + getPackageName())));
                } catch (Exception error) {
                    toast("Open Android app settings and enable Display over other apps for Project B.");
                }
            });
        }

        @JavascriptInterface public String appLabels() {
            JSONArray labels = new JSONArray();
            PackageManager manager = getPackageManager();
            Intent launcher = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
            for (android.content.pm.ResolveInfo info : manager.queryIntentActivities(launcher, 0)) {
                try {
                    labels.put(new JSONObject()
                            .put("package", info.activityInfo.packageName)
                            .put("name", info.loadLabel(manager).toString()));
                } catch (Exception ignored) { /* Keep other visible apps usable. */ }
            }
            return labels.toString();
        }

        @JavascriptInterface public String loadState(String key) {
            if (!key.matches("token|run|device_label|conditions")) return "";
            return getPreferences(MODE_PRIVATE).getString(origin + "/" + key, "");
        }

        @JavascriptInterface public void saveState(String key, String value) {
            if (key.matches("token|run|device_label|conditions") && value.length() <= 2048) {
                getPreferences(MODE_PRIVATE).edit().putString(origin + "/" + key, value).apply();
            }
        }

        @JavascriptInterface public long boottimeNs() {
            return SystemClock.elapsedRealtimeNanos();
        }

        @JavascriptInterface public void recording(String run, String workload, String token, int duration) {
            if (run.isEmpty() || run.matches("[0-9a-f]{32}")) {
                runOnUiThread(() -> notification(run, workload, token, duration));
            }
        }

        @JavascriptInterface public void exportFile(String path, String token) {
            if (!path.matches("runs/[0-9a-f]{32}/(metadata|summary|transactions|edges|timeline|resources|resources_summary)\\.(json|csv)")
                    && !path.matches("runs/[0-9a-f]{32}/capture\\.pftrace")
                    && !path.equals("evaluation.json")) return;
            runOnUiThread(() -> {
                exportPath = path;
                exportToken = token;
                exportOrigin = origin;
                Intent picker = new Intent(Intent.ACTION_CREATE_DOCUMENT)
                        .setType("application/octet-stream")
                        .addCategory(Intent.CATEGORY_OPENABLE)
                        .putExtra(Intent.EXTRA_TITLE, path.substring(path.lastIndexOf('/') + 1));
                startActivityForResult(picker, 11);
            });
        }
    }

    private void configureNotificationChannel() {
        // A new channel is required: Android keeps the old channel's LOW importance.
        NotificationChannel channel = new NotificationChannel(CHANNEL,
                "Experiment marker alerts", NotificationManager.IMPORTANCE_HIGH);
        channel.setDescription("Recording alerts and task-marker action buttons");
        channel.enableVibration(true);
        getSystemService(NotificationManager.class).createNotificationChannel(channel);
    }

    private void notification(String run, String workload, String token, int duration) {
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (run.isEmpty()) {
            stopService(new Intent(this, FloatingMarkersService.class));
            manager.cancel(NOTIFICATION_ID);
            notificationRun = "";
            return;
        }
        if (android.provider.Settings.canDrawOverlays(this)) {
            try {
                if (!FloatingMarkersService.runningFor(run)) {
                    startForegroundService(new Intent(this, FloatingMarkersService.class)
                            .putExtra("run", run).putExtra("workload", workload)
                            .putExtra("origin", origin).putExtra("token", token).putExtra("duration", duration));
                }
                manager.cancel(NOTIFICATION_ID);
                notificationRun = "";
                return;
            } catch (RuntimeException error) {
                // Background-start restrictions: preserve notification action fallback.
            }
        }
        if (run.equals(notificationRun) || !manager.areNotificationsEnabled()) return;
        String[] labels;
        switch (workload) {
            case "W0": labels = new String[]{"idle_start", "idle_end", "unexpected_activity"}; break;
            case "W1": labels = new String[]{"prompt_submitted", "confirmation", "browser_launched"}; break;
            case "W2": labels = new String[]{"voice_start", "voice_end", "response_complete"}; break;
            default: return;
        }
        configureNotificationChannel();
        Notification.Builder builder = new Notification.Builder(this, CHANNEL)
                .setSmallIcon(android.R.drawable.ic_menu_recent_history)
                .setContentTitle("Project B experiment active")
                .setContentText("Recording started. Expand for task-marker buttons.")
                .setStyle(new Notification.BigTextStyle().bigText(
                        "Use the buttons below when each event happens. Browser launched also detects the browser package."))
                .setOnlyAlertOnce(true)
                .setTimeoutAfter(1000L * Math.max(5, Math.min(180, duration)))
                .setOngoing(true);
        for (int i = 0; i < labels.length; i++) {
            Intent intent = new Intent(this, MarkerReceiver.class)
                    .putExtra("url", origin + "/api/runs/" + run + "/markers")
                    .putExtra("token", token)
                    .putExtra("label", labels[i]);
            PendingIntent pending = PendingIntent.getBroadcast(this, i, intent,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            builder.addAction(new Notification.Action.Builder(null, labels[i].replace('_', ' '), pending).build());
        }
        manager.notify(NOTIFICATION_ID, builder.build());
        notificationRun = run;
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != 11 || result != RESULT_OK || data == null || exportPath == null) return;
        String url = exportOrigin + "/api/" + exportPath;
        String token = exportToken;
        new Thread(() -> {
            try {
                MarkerReceiver.download(this, url, token, data.getData());
                toast("Export saved.");
            } catch (Exception error) {
                toast("Export failed: " + error.getMessage());
            }
        }).start();
    }
}
