package com.perrinresearch.foundry.data

import org.json.JSONArray
import org.json.JSONObject

data class Project(
    val id: Int,
    val ref: String,
    val name: String,
    val hypothesis: String,
    val form: String,
    val stage: String,
    val status: String,
    val repoSlug: String = "",
)

data class Task(
    val id: Int,
    val projectId: Int,
    val title: String,
    val description: String,
    val status: String,
    val position: Int,
)

data class AgentPrompt(
    val id: Int,
    val taskId: Int,
    val title: String,
    val promptText: String,
    val status: String,
    val priority: Int,
    val taskTitle: String?,
    val projectRef: String?,
)

fun JSONObject.toProject() = Project(
    id = getInt("id"),
    ref = getString("ref"),
    name = getString("name"),
    hypothesis = getString("hypothesis"),
    form = getString("form"),
    stage = getString("stage"),
    status = getString("status"),
    repoSlug = optString("repo_slug", ""),
)

fun JSONObject.toTask() = Task(
    id = getInt("id"),
    projectId = getInt("project_id"),
    title = getString("title"),
    description = optString("description", ""),
    status = getString("status"),
    position = getInt("position"),
)

fun JSONObject.toAgentPrompt() = AgentPrompt(
    id = getInt("id"),
    taskId = getInt("task_id"),
    title = getString("title"),
    promptText = getString("prompt_text"),
    status = getString("status"),
    priority = getInt("priority"),
    taskTitle = optString("task_title", null),
    projectRef = optString("project_ref", null),
)

fun JSONArray.toProjects(): List<Project> = (0 until length()).map { getJSONObject(it).toProject() }
fun JSONArray.toTasks(): List<Task> = (0 until length()).map { getJSONObject(it).toTask() }
fun JSONArray.toAgentPrompts(): List<AgentPrompt> = (0 until length()).map { getJSONObject(it).toAgentPrompt() }
