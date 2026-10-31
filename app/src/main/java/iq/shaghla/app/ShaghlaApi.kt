package iq.shaghla.app

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class ApiApplication(val id: Int, val jobId: Int, val status: String)

data class ApiJob(
    val id: Int,
    val title: String,
    val description: String,
    val category: String,
    val governorate: String,
    val area: String,
    val wageIqd: Int,
    val workType: String
)

class ShaghlaApi(private val baseUrl: String, private val token: String? = null) {
    private suspend fun request(path: String, method: String = "GET", body: JSONObject? = null): String =
        withContext(Dispatchers.IO) {
            val root = baseUrl.trim().removeSuffix("/")
            require(root.startsWith("https://") || root.startsWith("http://10.0.2.2")) {
                "أدخل رابط الخادم الصحيح الذي يبدأ بـ https://"
            }
            val connection = (URL(root + path).openConnection() as HttpURLConnection).apply {
                requestMethod = method
                connectTimeout = 12000
                readTimeout = 12000
                setRequestProperty("Accept", "application/json")
                token?.let { setRequestProperty("Authorization", "Bearer $it") }
                if (body != null) {
                    doOutput = true
                    setRequestProperty("Content-Type", "application/json; charset=utf-8")
                }
            }
            try {
                if (body != null) connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
                val code = connection.responseCode
                val stream = if (code in 200..299) connection.inputStream else connection.errorStream
                val response = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
                if (code !in 200..299) {
                    val message = runCatching { JSONObject(response).optString("detail") }.getOrNull()
                    throw IllegalStateException(message?.takeIf { it.isNotBlank() } ?: "خطأ اتصال ($code)")
                }
                response
            } finally {
                connection.disconnect()
            }
        }

    suspend fun googleLogin(idToken: String, role: String): Pair<String, JSONObject> {
        val json = JSONObject(request("/auth/google", "POST",
            JSONObject().put("credential", idToken).put("role", role)))
        return json.getString("access_token") to json.getJSONObject("user")
    }

    suspend fun requestOtp(phone: String, role: String) {
        request("/auth/request-otp", "POST", JSONObject().put("phone", phone).put("role", role))
    }

    suspend fun verifyOtp(phone: String, code: String): Pair<String, JSONObject> {
        val json = JSONObject(request("/auth/verify-otp", "POST", JSONObject().put("phone", phone).put("code", code)))
        return json.getString("access_token") to json.getJSONObject("user")
    }

    suspend fun jobs(query: String = ""): List<ApiJob> {
        val suffix = if (query.isBlank()) "" else "?q=" + java.net.URLEncoder.encode(query, "UTF-8")
        val array = JSONArray(request("/jobs$suffix"))
        return (0 until array.length()).map { index ->
            val item = array.getJSONObject(index)
            ApiJob(
                item.getInt("id"), item.optString("title"), item.optString("description"),
                item.optString("category"), item.optString("governorate"), item.optString("area"),
                item.optInt("wage_iqd"), item.optString("work_type")
            )
        }
    }

    suspend fun myJobs(): List<ApiJob> {
        val array = JSONArray(request("/employer/jobs"))
        return (0 until array.length()).map { index ->
            val item = array.getJSONObject(index)
            ApiJob(item.getInt("id"), item.optString("title"), item.optString("description"),
                item.optString("category"), item.optString("governorate"), item.optString("area"),
                item.optInt("wage_iqd"), item.optString("work_type"))
        }
    }

    suspend fun myApplications(): List<ApiApplication> {
        val array = JSONArray(request("/worker/applications"))
        return (0 until array.length()).map { index ->
            val item = array.getJSONObject(index)
            ApiApplication(item.getInt("id"), item.getInt("job_id"), item.optString("status"))
        }
    }

    suspend fun applicants(jobId: Int): List<ApiApplication> {
        val array = JSONArray(request("/employer/jobs/$jobId/applications"))
        return (0 until array.length()).map { index ->
            val item = array.getJSONObject(index)
            ApiApplication(item.getInt("id"), item.getInt("worker_id"), item.optString("status"))
        }
    }

    suspend fun setApplicationStatus(applicationId: Int, status: String) {
        request("/employer/applications/$applicationId/status", "PATCH",
            JSONObject().put("status", status))
    }

    suspend fun apply(jobId: Int) {
        request("/jobs/$jobId/apply", "POST", JSONObject())
    }

    suspend fun createJob(title: String, description: String, category: String, governorate: String,
                          area: String, wage: Int, workType: String) {
        val body = JSONObject()
            .put("title", title).put("description", description).put("category", category)
            .put("governorate", governorate).put("area", area).put("wage_iqd", wage)
            .put("work_type", workType).put("positions", 1)
        request("/jobs", "POST", body)
    }
}
