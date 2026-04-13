package com.jarvis.os.device

import android.app.Activity
import android.app.ActivityManager
import android.content.Context
import android.util.Log

/**
 * Manages kiosk (lock task) mode for tablet deployments.
 *
 * Requires the device to be enrolled as a Device Owner via ADB or MDM:
 *   adb shell dpm set-device-owner com.jarvis.os/.device.DeviceAdminReceiver
 *
 * Gracefully no-ops (logs warning) if device admin is not yet enrolled —
 * the app will never crash due to missing permissions.
 */
class KioskManager(private val activity: Activity) {

    companion object {
        private const val TAG = "KioskManager"
    }

    /**
     * Enter lock task (kiosk) mode. Home button and recents are suppressed.
     * No-ops with a warning if the device is not enrolled as Device Owner.
     */
    fun enterKioskMode() {
        try {
            activity.startLockTask()
            Log.i(TAG, "Kiosk mode entered.")
        } catch (e: SecurityException) {
            Log.w(TAG, "Cannot enter kiosk mode — device admin not enrolled: ${e.message}")
        } catch (e: Exception) {
            Log.w(TAG, "enterKioskMode failed: ${e.message}")
        }
    }

    /**
     * Exit lock task mode. Safe to call even if not currently in kiosk mode.
     */
    fun exitKioskMode() {
        try {
            activity.stopLockTask()
            Log.i(TAG, "Kiosk mode exited.")
        } catch (e: Exception) {
            Log.w(TAG, "exitKioskMode failed: ${e.message}")
        }
    }

    /**
     * Returns true if the device is currently in lock task (kiosk) mode.
     */
    fun isInKioskMode(): Boolean {
        return try {
            val am = activity.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
            am.lockTaskModeState != ActivityManager.LOCK_TASK_MODE_NONE
        } catch (e: Exception) {
            false
        }
    }
}
