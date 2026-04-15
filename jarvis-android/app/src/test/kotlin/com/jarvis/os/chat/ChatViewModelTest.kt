package com.jarvis.os.chat

import androidx.arch.core.executor.testing.InstantTaskExecutorRule
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.*
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class ChatViewModelTest {

    @get:Rule
    val instantExecutorRule = InstantTaskExecutorRule()

    private val testDispatcher = StandardTestDispatcher()
    private lateinit var repository: ChatRepository
    private lateinit var viewModel: ChatViewModel

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        repository = mockk()
        viewModel = ChatViewModel(repository)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    // ── Initial state ─────────────────────────────────────────────────────────

    @Test
    fun `initial state has empty messages and no loading`() {
        val state = viewModel.uiState.value
        assertTrue(state.messages.isEmpty())
        assertFalse(state.isLoading)
        assertNull(state.error)
    }

    // ── sendMessage ───────────────────────────────────────────────────────────

    @Test
    fun `sendMessage appends user message immediately`() {
        val response = ChatMessage(role = MessageRole.JARVIS, text = "Hello Sir")
        coEvery { repository.sendMessage(any()) } returns Result.success(response)

        viewModel.sendMessage("Hello")

        val messages = viewModel.uiState.value.messages
        assertEquals(1, messages.size)
        assertEquals(MessageRole.USER, messages[0].role)
        assertEquals("Hello", messages[0].text)
    }

    @Test
    fun `sendMessage sets isLoading true while awaiting response`() {
        val response = ChatMessage(role = MessageRole.JARVIS, text = "response")
        coEvery { repository.sendMessage(any()) } returns Result.success(response)

        viewModel.sendMessage("Hello")

        assertTrue(viewModel.uiState.value.isLoading)
    }

    @Test
    fun `sendMessage appends jarvis response after success`() = runTest {
        val response = ChatMessage(role = MessageRole.JARVIS, text = "42", adapter = "finance")
        coEvery { repository.sendMessage("What is the answer?") } returns Result.success(response)

        viewModel.sendMessage("What is the answer?")
        advanceUntilIdle()

        val messages = viewModel.uiState.value.messages
        assertEquals(2, messages.size)
        assertEquals(MessageRole.JARVIS, messages[1].role)
        assertEquals("42", messages[1].text)
        assertEquals("finance", messages[1].adapter)
    }

    @Test
    fun `sendMessage clears loading after success`() = runTest {
        val response = ChatMessage(role = MessageRole.JARVIS, text = "ok")
        coEvery { repository.sendMessage(any()) } returns Result.success(response)

        viewModel.sendMessage("ping")
        advanceUntilIdle()

        assertFalse(viewModel.uiState.value.isLoading)
    }

    @Test
    fun `sendMessage sets error on repository failure`() = runTest {
        coEvery { repository.sendMessage(any()) } returns Result.failure(RuntimeException("timeout"))

        viewModel.sendMessage("ping")
        advanceUntilIdle()

        val state = viewModel.uiState.value
        assertFalse(state.isLoading)
        assertNotNull(state.error)
        assertTrue(state.error!!.contains("timeout"))
    }

    @Test
    fun `sendMessage trims whitespace before sending`() = runTest {
        val response = ChatMessage(role = MessageRole.JARVIS, text = "ok")
        coEvery { repository.sendMessage("hello") } returns Result.success(response)

        viewModel.sendMessage("  hello  ")
        advanceUntilIdle()

        coVerify { repository.sendMessage("hello") }
        assertEquals("hello", viewModel.uiState.value.messages[0].text)
    }

    @Test
    fun `sendMessage ignores blank input`() = runTest {
        viewModel.sendMessage("   ")
        advanceUntilIdle()

        assertTrue(viewModel.uiState.value.messages.isEmpty())
        coVerify(exactly = 0) { repository.sendMessage(any()) }
    }

    @Test
    fun `multiple messages accumulate in order`() = runTest {
        coEvery { repository.sendMessage("one") } returns Result.success(
            ChatMessage(role = MessageRole.JARVIS, text = "resp-1")
        )
        coEvery { repository.sendMessage("two") } returns Result.success(
            ChatMessage(role = MessageRole.JARVIS, text = "resp-2")
        )

        viewModel.sendMessage("one")
        advanceUntilIdle()
        viewModel.sendMessage("two")
        advanceUntilIdle()

        val msgs = viewModel.uiState.value.messages
        assertEquals(4, msgs.size)
        assertEquals("one", msgs[0].text)
        assertEquals("resp-1", msgs[1].text)
        assertEquals("two", msgs[2].text)
        assertEquals("resp-2", msgs[3].text)
    }

    // ── injectPushMessage ─────────────────────────────────────────────────────

    @Test
    fun `injectPushMessage appends jarvis message without calling repository`() = runTest {
        viewModel.injectPushMessage("Alert: rain expected", "weather")
        advanceUntilIdle()

        val msgs = viewModel.uiState.value.messages
        assertEquals(1, msgs.size)
        assertEquals(MessageRole.JARVIS, msgs[0].role)
        assertEquals("Alert: rain expected", msgs[0].text)
        assertEquals("weather", msgs[0].adapter)
        coVerify(exactly = 0) { repository.sendMessage(any()) }
    }

    // ── clearError ────────────────────────────────────────────────────────────

    @Test
    fun `clearError removes error from state`() = runTest {
        coEvery { repository.sendMessage(any()) } returns Result.failure(RuntimeException("err"))

        viewModel.sendMessage("ping")
        advanceUntilIdle()

        assertNotNull(viewModel.uiState.value.error)
        viewModel.clearError()
        assertNull(viewModel.uiState.value.error)
    }

    // ── clearHistory ──────────────────────────────────────────────────────────

    @Test
    fun `clearHistory empties the message list`() = runTest {
        val response = ChatMessage(role = MessageRole.JARVIS, text = "ok")
        coEvery { repository.sendMessage(any()) } returns Result.success(response)

        viewModel.sendMessage("hello")
        advanceUntilIdle()

        viewModel.clearHistory()
        assertTrue(viewModel.uiState.value.messages.isEmpty())
    }
}
