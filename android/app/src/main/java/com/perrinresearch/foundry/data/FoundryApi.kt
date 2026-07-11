package com.perrinresearch.foundry.data

import com.perrinresearch.foundry.BuildConfig
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

class FoundryApi(private var token: String? = null) {
    private val client = OkHttpClient()
    private val json = "application/json".toMediaType()
    private val base = BuildConfig.API_BASE_URL.trimEnd('/')

    fun setToken(t: String?) { token = t }

    private fun request(path: String, method: String = "GET", body: JSONObject? = null): String {
        val builder = Request.Builder().url("$base$path")
        token?.let { builder.addHeader("Authorization", "Bearer $it") }
        when (method) {
            "POST", "PATCH" -> builder.method(method, (body?.toString() ?: "{}").toRequestBody(json))
            "DELETE" -> builder.delete()
            else -> builder.get()
        }
        client.newCall(builder.build()).execute().use { res ->
            if (!res.isSuccessful) throw ApiException(res.code, res.body?.string() ?: res.message)
            return res.body?.string() ?: ""
        }
    }

    fun login(email: String, password: String): String {
        val body = JSONObject().put("email", email).put("password", password)
        val raw = request("/api/auth/login", "POST", body)
        return JSONObject(raw).getString("access_token")
    }

    fun listProjects(): List<Project> =
        org.json.JSONArray(request("/api/projects")).toProjects()

    fun getProject(id: Int): Project =
        JSONObject(request("/api/projects/$id")).toProject()

    fun listTasks(projectId: Int): List<Task> =
        org.json.JSONArray(request("/api/projects/$projectId/tasks")).toTasks()

    fun createTask(projectId: Int, title: String, status: String = "backlog"): Task {
        val body = JSONObject().put("title", title).put("status", status)
        return JSONObject(request("/api/projects/$projectId/tasks", "POST", body)).toTask()
    }

    fun updateTaskStatus(taskId: Int, status: String): Task {
        val body = JSONObject().put("status", status)
        return JSONObject(request("/api/tasks/$taskId", "PATCH", body)).toTask()
    }

    fun listPrompts(): List<AgentPrompt> =
        org.json.JSONArray(request("/api/agent-prompts")).toAgentPrompts()

    fun createPrompt(taskId: Int, title: String, text: String): AgentPrompt {
        val body = JSONObject().put("task_id", taskId).put("title", title).put("prompt_text", text)
        return JSONObject(request("/api/agent-prompts", "POST", body)).toAgentPrompt()
    }

    fun updatePromptStatus(id: Int, status: String, notes: String = ""): AgentPrompt {
        val body = JSONObject().put("status", status)
        if (notes.isNotEmpty()) body.put("result_notes", notes)
        return JSONObject(request("/api/agent-prompts/$id", "PATCH", body)).toAgentPrompt()
    }
}

class ApiException(val code: Int, message: String) : Exception(message)
