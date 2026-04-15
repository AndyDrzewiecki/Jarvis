package com.jarvis.os.notification

import org.junit.Assert.*
import org.junit.Test

/**
 * Tests for pure-logic / constant aspects of NotificationHelper.
 *
 * Full notification-posting behavior requires an Android device/emulator
 * and is covered by instrumented tests. These tests guard the channel IDs
 * and constants that other code depends on.
 */
class NotificationHelperTest {

    @Test
    fun `CHANNEL_ALERTS constant is correct`() {
        assertEquals("jarvis_alerts", NotificationHelper.CHANNEL_ALERTS)
    }

    @Test
    fun `CHANNEL_PUSH constant is correct`() {
        assertEquals("jarvis_push", NotificationHelper.CHANNEL_PUSH)
    }

    @Test
    fun `CHANNEL_WAKE constant is correct`() {
        assertEquals("jarvis_wake", NotificationHelper.CHANNEL_WAKE)
    }

    @Test
    fun `all channel IDs are distinct`() {
        val ids = setOf(
            NotificationHelper.CHANNEL_ALERTS,
            NotificationHelper.CHANNEL_PUSH,
            NotificationHelper.CHANNEL_WAKE,
        )
        assertEquals(3, ids.size)
    }

    @Test
    fun `channel IDs contain only safe characters`() {
        // Channel IDs must not contain spaces or special chars that could break Android APIs
        val safePattern = Regex("^[a-z_]+$")
        listOf(
            NotificationHelper.CHANNEL_ALERTS,
            NotificationHelper.CHANNEL_PUSH,
            NotificationHelper.CHANNEL_WAKE,
        ).forEach { id ->
            assertTrue("Channel ID '$id' has unsafe characters", safePattern.matches(id))
        }
    }
}
