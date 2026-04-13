package com.jarvis.os.device

import android.app.admin.DeviceAdminReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Minimal Device Admin receiver required for DevicePolicyManager lock task support.
 *
 * To enroll as device owner (enables kiosk mode):
 *   adb shell dpm set-device-owner com.jarvis.os/.device.DeviceAdminReceiver
 *
 * Referenced in AndroidManifest.xml with the device_admin.xml policy resource.
 */
class DeviceAdminReceiver : DeviceAdminReceiver() {

    companion object {
        private const val TAG = "JarvisDeviceAdmin"
    }

    override fun onEnabled(context: Context, intent: Intent) {
        Log.i(TAG, "Device admin enabled — kiosk mode available.")
    }

    override fun onDisabled(context: Context, intent: Intent) {
        Log.i(TAG, "Device admin disabled.")
    }
}
