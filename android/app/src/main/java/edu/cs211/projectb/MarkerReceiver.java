package edu.cs211.projectb;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

public final class MarkerReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        long eventTime = SystemClock.elapsedRealtimeNanos();
        PendingResult result = goAsync();
        new Thread(() -> {
            String message;
            HttpURLConnection connection = null;
            try {
                JSONObject body = new JSONObject()
                        .put("label", intent.getStringExtra("label"))
                        .put("boottime_ns", eventTime);
                connection = connect(intent.getStringExtra("url"), intent.getStringExtra("token"));
                connection.setRequestMethod("POST");
                connection.setRequestProperty("Content-Type", "application/json");
                connection.setDoOutput(true);
                try (var stream = connection.getOutputStream()) {
                    stream.write(body.toString().getBytes(StandardCharsets.UTF_8));
                }
                check(connection);
                message = "Task marker saved.";
            } catch (Exception error) {
                message = "Marker failed: " + error.getMessage();
            } finally {
                if (connection != null) connection.disconnect();
                result.finish();
            }
            String notice = message;
            new Handler(Looper.getMainLooper()).post(() ->
                    Toast.makeText(context, notice, Toast.LENGTH_SHORT).show());
        }).start();
    }

    private static HttpURLConnection connect(String url, String token) throws IOException {
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        connection.setConnectTimeout(4000);
        connection.setReadTimeout(5000);
        connection.setInstanceFollowRedirects(false);
        connection.setRequestProperty("Authorization", "Bearer " + token);
        return connection;
    }

    private static void check(HttpURLConnection connection) throws IOException {
        int code = connection.getResponseCode();
        if (code < 200 || code >= 300) throw new IOException("Backend returned HTTP " + code);
    }

    static void download(Context context, String url, String token, Uri destination) throws IOException {
        HttpURLConnection connection = connect(url, token);
        try {
            check(connection);
            try (var in = connection.getInputStream();
                 var out = context.getContentResolver().openOutputStream(destination)) {
                if (out == null) throw new IOException("Could not open selected file.");
                byte[] buffer = new byte[65536];
                int count;
                while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count);
            }
        } finally {
            connection.disconnect();
        }
    }
}
