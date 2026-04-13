package com.jarvis.os.device

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "jarvis_prefs")

class DevicePreferences(private val context: Context) {

    companion object {
        val SERVER_IP = stringPreferencesKey("server_ip")
        val DEVICE_NAME = stringPreferencesKey("device_name")
        val DEVICE_PROFILE = stringPreferencesKey("device_profile")
        const val DEFAULT_SERVER_IP = "192.168.1.100:8000"
    }

    val serverIp: Flow<String> = context.dataStore.data
        .map { it[SERVER_IP] ?: DEFAULT_SERVER_IP }

    val deviceName: Flow<String> = context.dataStore.data
        .map { it[DEVICE_NAME] ?: android.os.Build.MODEL }

    val deviceProfile: Flow<String> = context.dataStore.data
        .map { it[DEVICE_PROFILE] ?: DeviceProfile.DEFAULT.profileName }

    suspend fun saveServerIp(ip: String) {
        context.dataStore.edit { it[SERVER_IP] = ip }
    }

    suspend fun saveDeviceName(name: String) {
        context.dataStore.edit { it[DEVICE_NAME] = name }
    }

    suspend fun saveDeviceProfile(profile: String) {
        context.dataStore.edit { it[DEVICE_PROFILE] = profile }
    }
}
