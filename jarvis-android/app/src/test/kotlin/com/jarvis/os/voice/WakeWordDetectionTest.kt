package com.jarvis.os.voice

import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

/**
 * Pure-logic tests for WakeWordService detection routines.
 *
 * We test the detection helpers in isolation (no Android runtime needed).
 * The service is not instantiated — we call the detection logic directly via
 * a thin test harness that mirrors WakeWordService's internal logic.
 */
class WakeWordDetectionTest {

    // Mirrors WakeWordService logic without requiring Android context
    private val wakePhrases = WakeWordService.WAKE_PHRASES

    private fun extractCommand(text: String, phrase: String): String {
        val idx = text.indexOf(phrase)
        if (idx < 0) return ""
        return text.substring(idx + phrase.length).trimStart(',', ' ', '.').trim()
    }

    private fun detectWakeWord(candidates: List<String>): Pair<Boolean, String> {
        for (candidate in candidates) {
            val lower = candidate.lowercase()
            for (phrase in wakePhrases) {
                if (lower.contains(phrase)) {
                    return true to extractCommand(lower, phrase)
                }
            }
        }
        return false to ""
    }

    // ── Wake phrase detection ─────────────────────────────────────────────────

    @Test
    fun `detects hey jarvis with command`() {
        val (detected, cmd) = detectWakeWord(listOf("hey jarvis what's the weather"))
        assertTrue(detected)
        assertEquals("what's the weather", cmd)
    }

    @Test
    fun `detects ok jarvis with command`() {
        val (detected, cmd) = detectWakeWord(listOf("ok jarvis set a timer"))
        assertTrue(detected)
        assertEquals("set a timer", cmd)
    }

    @Test
    fun `detects bare jarvis with command`() {
        val (detected, cmd) = detectWakeWord(listOf("jarvis turn off the lights"))
        assertTrue(detected)
        assertEquals("turn off the lights", cmd)
    }

    @Test
    fun `detects hey jarvis alone with empty command`() {
        val (detected, cmd) = detectWakeWord(listOf("hey jarvis"))
        assertTrue(detected)
        assertEquals("", cmd)
    }

    @Test
    fun `detection is case-insensitive`() {
        val (detected, _) = detectWakeWord(listOf("HEY JARVIS HELLO"))
        assertTrue(detected)
    }

    @Test
    fun `no detection on unrelated speech`() {
        val (detected, _) = detectWakeWord(listOf("the weather is fine today"))
        assertFalse(detected)
    }

    @Test
    fun `no detection on empty list`() {
        val (detected, _) = detectWakeWord(emptyList())
        assertFalse(detected)
    }

    @Test
    fun `no detection on empty string`() {
        val (detected, _) = detectWakeWord(listOf(""))
        assertFalse(detected)
    }

    @Test
    fun `uses first matching candidate`() {
        val (detected, cmd) = detectWakeWord(
            listOf("unrelated speech", "hey jarvis check finance")
        )
        assertTrue(detected)
        assertEquals("check finance", cmd)
    }

    // ── extractCommand ────────────────────────────────────────────────────────

    @Test
    fun `extractCommand strips phrase from start`() {
        assertEquals("hello world", extractCommand("hey jarvis hello world", "hey jarvis"))
    }

    @Test
    fun `extractCommand strips leading comma and space`() {
        assertEquals("hello", extractCommand("hey jarvis, hello", "hey jarvis"))
    }

    @Test
    fun `extractCommand returns empty when phrase is entire input`() {
        assertEquals("", extractCommand("hey jarvis", "hey jarvis"))
    }

    @Test
    fun `extractCommand returns empty when phrase not found`() {
        assertEquals("", extractCommand("something else", "hey jarvis"))
    }

    @Test
    fun `extractCommand handles phrase mid-sentence`() {
        // Partial result might include surrounding noise
        assertEquals("turn on lights", extractCommand("uhh hey jarvis turn on lights", "hey jarvis"))
    }

    // ── WAKE_PHRASES set ──────────────────────────────────────────────────────

    @Test
    fun `WAKE_PHRASES contains hey jarvis`() {
        assertTrue("hey jarvis" in wakePhrases)
    }

    @Test
    fun `WAKE_PHRASES contains ok jarvis`() {
        assertTrue("ok jarvis" in wakePhrases)
    }

    @Test
    fun `WAKE_PHRASES contains bare jarvis`() {
        assertTrue("jarvis" in wakePhrases)
    }

    @Test
    fun `WAKE_PHRASES are all lowercase`() {
        wakePhrases.forEach { phrase ->
            assertEquals("Phrase should be lowercase: '$phrase'", phrase, phrase.lowercase())
        }
    }
}
