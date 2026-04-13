package com.jarvis.os.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.util.Log
import com.jarvis.os.device.DevicePreferences
import com.jarvis.os.voice.TtsPlayer
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first
import okhttp3.*
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Persistent foreground Service that maintains a WebSocket connection to the
 * Jarvis server for push notifications (spoken briefs, alerts).
 *
 * - Reconnects with exponential backoff: 2s → 4s → 8s → max 60s
 * - On {"type":"speak","text":"..."} message: calls TtsPlayer.play()
 * - Foreground notification channel "jarvis_push" keeps service alive on Android 12+
 */
class WebSocketService : Service() {

    companion object {
        private const val TAG = "WebSocketService"
        private const val CHANNEL_ID = "jarvis_push"
        private const val NOTIFICATION_ID = 1001
        private const val BACKOFF_BASE_MS = 2_000L
        private const val BACKOFF_MAX_MS = 60_000L
    }

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)  // keep-alive — no read timeout
        .build()

    private lateinit var devicePrefs: DevicePreferences
    private lateinit var ttsPlayer: TtsPlayer
    private var currentSocket: WebSocket? = null
    private var reconnectDelayMs = BACKOFF_BASE_MS

    override fun onCreate() {
        super.onCreate()
        devicePrefs = DevicePreferences(this)
        ttsPlayer = TtsPlayer()
        createNotificationChannel()
        startForeground(NOTIFICATION_ID, buildNotification("Connecting…"))
        scope.launch { connectLoop() }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        return START_STICKY  // restart if killed
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        super.onDestroy()
        currentSocket?.close(1000, "Service stopped")
        scope.cancel()
    }

    // ── Connection loop with exponential backoff ────────────────────────────────

    private suspend fun connectLoop() {
        val serverIp = devicePrefs.serverIp.first()
        val deviceName = devicePrefs.deviceName.first()
        val deviceId = deviceName.lowercase().replace(" ", "-")

        while (scope.isActive) {
            val url = "ws://$serverIp/api/ws?device_id=$deviceId"
            Log.d(TAG, "Connecting to $url")
            val connected = connectOnce(url, serverIp)
            if (connected) {
                reconnectDelayMs = BACKOFF_BASE_MS  // reset on success
            } else {
                Log.w(TAG, "WebSocket disconnected. Retrying in ${reconnectDelayMs}ms.")
                updateNotification("Reconnecting…")
                delay(reconnectDelayMs)
                reconnectDelayMs = minOf(reconnectDelayMs * 2, BACKOFF_MAX_MS)
            }
        }
    }

    /**
     * Open one WebSocket connection. Suspends until disconnected.
     * Returns true if the connection was established (even if later dropped).
     */
    private suspend fun connectOnce(url: String, serverIp: String): Boolean {
        val connected = CompletableDeferred<Boolean>()
        val disconnected = CompletableDeferred<Unit>()

        val request = Request.Builder().url(url).build()
        val listener = object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                currentSocket = webSocket
                updateNotification("Connected")
                connected.complete(true)
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                handleMessage(text, serverIp)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.w(TAG, "WebSocket failure: ${t.message}")
                if (!connected.isCompleted) connected.complete(false)
                disconnected.complete(Unit)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.d(TAG, "WebSocket closed: $code $reason")
                disconnected.complete(Unit)
            }
        }

        client.newWebSocket(request, listener)

        return try {
            val wasConnected = connected.await()
            if (wasConnected) disconnected.await()
            wasConnected
        } catch (e: Exception) {
            false
        }
    }

    private fun handleMessage(text: String, serverIp: String) {
        try {
            val json = JSONObject(text)
            when (json.optString("type")) {
                "speak" -> {
                    val speakText = json.optString("text")
                    if (speakText.isNotBlank()) {
                        ttsPlayer.play(serverIp, speakText, cacheDir)
                    }
                }
                else -> Log.d(TAG, "Unknown WS message type: $text")
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to parse WS message: $text")
        }
    }

    // ── Notification helpers ───────────────────────────────────────────────────

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Jarvis Push",
            NotificationManager.IMPORTANCE_LOW,
        ).apply { description = "Jarvis real-time push notifications" }
        getSystemService(NotificationManager::class.java)?.createNotificationChannel(channel)
    }

    private fun buildNotification(status: String): Notification =
        Notification.Builder(this, CHANNEL_ID)
            .setContentTitle("Jarvis")
            .setContentText("Jarvis — $status")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setOngoing(true)
            .build()

    private fun updateNotification(status: String) {
        val nm = getSystemService(NotificationManager::class.java)
        nm?.notify(NOTIFICATION_ID, buildNotification(status))
    }
}
