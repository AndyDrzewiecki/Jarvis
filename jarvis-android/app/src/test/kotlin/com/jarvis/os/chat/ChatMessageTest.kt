package com.jarvis.os.chat

import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class ChatMessageTest {

    @Test
    fun `user message has correct role flags`() {
        val msg = ChatMessage(role = MessageRole.USER, text = "Hello Jarvis")
        assertTrue(msg.isUser)
        assertFalse(msg.isJarvis)
    }

    @Test
    fun `jarvis message has correct role flags`() {
        val msg = ChatMessage(role = MessageRole.JARVIS, text = "Hello Sir")
        assertFalse(msg.isUser)
        assertTrue(msg.isJarvis)
    }

    @Test
    fun `adapter field defaults to empty string`() {
        val msg = ChatMessage(role = MessageRole.USER, text = "test")
        assertEquals("", msg.adapter)
    }

    @Test
    fun `adapter field is preserved`() {
        val msg = ChatMessage(role = MessageRole.JARVIS, text = "result", adapter = "grocery")
        assertEquals("grocery", msg.adapter)
    }

    @Test
    fun `two messages created in sequence have different default ids`() {
        val a = ChatMessage(role = MessageRole.USER, text = "a")
        val b = ChatMessage(role = MessageRole.USER, text = "b")
        assertNotEquals(a.id, b.id)
    }

    @Test
    fun `explicit id is preserved`() {
        val msg = ChatMessage(id = "fixed-id", role = MessageRole.USER, text = "hi")
        assertEquals("fixed-id", msg.id)
    }

    @Test
    fun `timestamp defaults to approximately now`() {
        val before = Instant.now().minusMillis(100)
        val msg = ChatMessage(role = MessageRole.USER, text = "test")
        val after = Instant.now().plusMillis(100)
        assertTrue(msg.timestamp.isAfter(before))
        assertTrue(msg.timestamp.isBefore(after))
    }

    @Test
    fun `data class equality uses all fields`() {
        val ts = Instant.parse("2026-01-01T00:00:00Z")
        val a = ChatMessage(id = "x", role = MessageRole.USER, text = "hi", adapter = "", timestamp = ts)
        val b = ChatMessage(id = "x", role = MessageRole.USER, text = "hi", adapter = "", timestamp = ts)
        assertEquals(a, b)
    }

    @Test
    fun `copy creates independent message`() {
        val original = ChatMessage(role = MessageRole.USER, text = "hello")
        val copy = original.copy(text = "world")
        assertEquals("hello", original.text)
        assertEquals("world", copy.text)
        assertEquals(original.id, copy.id)
    }
}
