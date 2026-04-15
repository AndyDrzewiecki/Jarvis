package com.jarvis.os.notification

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import com.jarvis.os.MainActivity

/**
 * Central notification helper for the Jarvis app.
 *
 * Three channels:
 *  - CHANNEL_ALERTS  (high importance) — blackboard alerts from specialists
 *  - CHANNEL_PUSH    (low importance)  — WebSocket service status
 *  - CHANNEL_WAKE    (min importance)  — wake-word service persistent notification
 */
object NotificationHelper {

    const val CHANNEL_ALERTS = "jarvis_alerts"
    const val CHANNEL_PUSH = "jarvis_push"
    const val CHANNEL_WAKE = "jarvis_wake"

    /** Create all notification channels. Safe to call multiple times (idempotent). */
    fun createChannels(context: Context) {
        val nm = context.getSystemService(NotificationManager::class.java) ?: return

        nm.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ALERTS,
                "Jarvis Alerts",
                NotificationManager.IMPORTANCE_HIGH,
            ).apply {
                description = "Blackboard alerts from Jarvis specialists"
                enableVibration(true)
            }
        )

        nm.createNotificationChannel(
            NotificationChannel(
                CHANNEL_PUSH,
                "Jarvis Push",
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = "Jarvis real-time push connection status"
            }
        )

        nm.createNotificationChannel(
            NotificationChannel(
                CHANNEL_WAKE,
                "Wake Word Listener",
                NotificationManager.IMPORTANCE_MIN,
            ).apply {
                description = "Always-on wake-word detection service"
                setShowBadge(false)
            }
        )
    }

    /**
     * Post a high-priority alert notification (e.g. specialist blackboard event).
     * Tapping the notification brings the user back to MainActivity.
     */
    fun postAlert(
        context: Context,
        title: String,
        message: String,
        notifId: Int = System.currentTimeMillis().toInt(),
    ) {
        val nm = context.getSystemService(NotificationManager::class.java) ?: return

        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pi = PendingIntent.getActivity(
            context, 0, intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )

        val notif = NotificationCompat.Builder(context, CHANNEL_ALERTS)
            .setContentTitle(title)
            .setContentText(message)
            .setStyle(NotificationCompat.BigTextStyle().bigText(message))
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentIntent(pi)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()

        nm.notify(notifId, notif)
    }

    /**
     * Build a foreground service notification for the WebSocket push service.
     * Uses [Notification.Builder] directly (no compat needed — API 26+).
     */
    fun buildPushServiceNotification(context: Context, status: String): Notification =
        Notification.Builder(context, CHANNEL_PUSH)
            .setContentTitle("Jarvis")
            .setContentText(status)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setOngoing(true)
            .build()

    /**
     * Build a foreground service notification for the wake-word detection service.
     */
    fun buildWakeWordNotification(context: Context): Notification =
        Notification.Builder(context, CHANNEL_WAKE)
            .setContentTitle("Jarvis")
            .setContentText("Listening for \"Hey Jarvis\"…")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setOngoing(true)
            .build()
}
