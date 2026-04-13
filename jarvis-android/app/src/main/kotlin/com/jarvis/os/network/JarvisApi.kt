package com.jarvis.os.network

import com.google.gson.annotations.SerializedName
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query
import java.util.concurrent.TimeUnit

data class ChatRequest(val message: String)

data class ChatResponse(
    val success: Boolean,
    val text: String,
    val adapter: String,
    val data: Map<String, Any> = emptyMap(),
)

data class DeviceRegisterRequest(
    @SerializedName("device_id") val deviceId: String,
    val profile: String,
    @SerializedName("display_name") val displayName: String,
)

data class OsVersionResponse(
    @SerializedName("version_code") val versionCode: Int,
    @SerializedName("version_name") val versionName: String,
    @SerializedName("release_notes") val releaseNotes: String = "",
)

data class NotebookSaveRequest(
    val title: String = "",
    val content: String,
    val category: String = "notes",
    val tags: List<String> = emptyList(),
    @SerializedName("device_id") val deviceId: String = "",
)

interface JarvisApiService {
    @POST("api/chat")
    suspend fun chat(@Body request: ChatRequest): ChatResponse

    @POST("api/devices/register")
    suspend fun registerDevice(@Body request: DeviceRegisterRequest): Map<String, Any>

    @GET("api/os/version")
    suspend fun getOsVersion(): OsVersionResponse

    @POST("api/notebook")
    suspend fun saveToNotebook(@Body item: NotebookSaveRequest): Map<String, Any>

    @GET("api/notebook")
    suspend fun getNotebook(
        @Query("q") query: String? = null,
        @Query("category") category: String? = null,
    ): Map<String, Any>
}

object JarvisApiClient {
    private var retrofit: Retrofit? = null

    fun build(serverIp: String): JarvisApiService {
        val baseUrl = if (serverIp.startsWith("http")) serverIp else "http://$serverIp"
        val normalizedUrl = if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/"

        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        }
        val client = OkHttpClient.Builder()
            .addInterceptor(logging)
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .build()

        retrofit = Retrofit.Builder()
            .baseUrl(normalizedUrl)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()

        return retrofit!!.create(JarvisApiService::class.java)
    }
}
