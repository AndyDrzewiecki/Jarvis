package com.jarvis.os.updater

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.util.Log
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.net.URL

class OtaUpdater(private val context: Context) {
    private val tag = "OtaUpdater"

    /**
     * Check server for a newer APK version and install if available.
     * currentVersionCode: BuildConfig.VERSION_CODE
     * serverIp: e.g. "192.168.1.100:8000"
     */
    suspend fun checkAndUpdate(serverIp: String, currentVersionCode: Int) {
        withContext(Dispatchers.IO) {
            try {
                val base = if (serverIp.startsWith("http")) serverIp else "http://$serverIp"
                val versionUrl = "$base/api/os/version"

                val json = URL(versionUrl).readText()
                val versionCode = extractVersionCode(json)

                if (versionCode > currentVersionCode) {
                    Log.i(tag, "New version available: $versionCode (current: $currentVersionCode)")
                    downloadAndInstall(base)
                } else {
                    Log.d(tag, "Already up to date (version $currentVersionCode)")
                }
            } catch (e: Exception) {
                Log.w(tag, "OTA check failed: ${e.message}")
            }
        }
    }

    private fun extractVersionCode(json: String): Int {
        val match = Regex(""""version_code"\s*:\s*(\d+)""").find(json)
        return match?.groupValues?.get(1)?.toIntOrNull() ?: 0
    }

    private fun downloadAndInstall(baseUrl: String) {
        val apkFile = File(context.cacheDir, "jarvis-update.apk")
        try {
            URL("$baseUrl/api/os/apk").openStream().use { input ->
                FileOutputStream(apkFile).use { output ->
                    input.copyTo(output)
                }
            }
            installApk(apkFile)
        } catch (e: Exception) {
            Log.e(tag, "APK download failed: ${e.message}")
            apkFile.delete()
        }
    }

    private fun installApk(apkFile: File) {
        val uri: Uri = FileProvider.getUriForFile(
            context,
            "${context.packageName}.provider",
            apkFile,
        )
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION
        }
        context.startActivity(intent)
    }
}
