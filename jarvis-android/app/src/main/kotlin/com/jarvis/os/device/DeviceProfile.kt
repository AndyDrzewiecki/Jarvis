package com.jarvis.os.device

enum class DeviceProfile(val profileName: String, val isLauncherMode: Boolean) {
    KITCHEN("kitchen", true),
    GARAGE("garage", true),
    PHONE("phone", false),
    BEDROOM("bedroom", true),
    DEFAULT("default", false);

    companion object {
        fun fromName(name: String): DeviceProfile =
            values().firstOrNull { it.profileName == name } ?: DEFAULT
    }
}
