package com.jarvis.os.chat

import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import com.jarvis.os.network.ChatResponse
import com.jarvis.os.network.JarvisApiService
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class ChatRepositoryTest {

    private lateinit var api: JarvisApiService
    private lateinit var repository: ChatRepository

    @Before
    fun setUp() {
        api = mockk()
        repository = ChatRepository(serverIp = "192.168.111.28:8000", api = api)
    }

    @Test
    fun `sendMessage returns success with jarvis message`() = runTest {
        coEvery { api.chat(any()) } returns ChatResponse(
            success = true,
            text = "It will be 72°F and sunny.",
            adapter = "weather",
        )

        val result = repository.sendMessage("What's the weather?")

        assertTrue(result.isSuccess)
        val msg = result.getOrThrow()
        assertEquals(MessageRole.JARVIS, msg.role)
        assertEquals("It will be 72°F and sunny.", msg.text)
        assertEquals("weather", msg.adapter)
    }

    @Test
    fun `sendMessage trims input before sending to API`() = runTest {
        coEvery { api.chat(any()) } returns ChatResponse(success = true, text = "ok", adapter = "core")

        repository.sendMessage("  hello  ")

        coVerify {
            api.chat(match { it.message == "hello" })
        }
    }

    @Test
    fun `sendMessage wraps network exception as failure`() = runTest {
        coEvery { api.chat(any()) } throws RuntimeException("Connection refused")

        val result = repository.sendMessage("ping")

        assertTrue(result.isFailure)
        assertTrue(result.exceptionOrNull()!!.message!!.contains("Connection refused"))
    }

    @Test
    fun `sendMessage result message has non-blank id`() = runTest {
        coEvery { api.chat(any()) } returns ChatResponse(success = true, text = "hello", adapter = "core")

        val result = repository.sendMessage("hi")

        assertTrue(result.getOrThrow().id.isNotBlank())
    }
}
