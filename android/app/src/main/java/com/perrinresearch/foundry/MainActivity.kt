package com.perrinresearch.foundry

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.perrinresearch.foundry.data.*
import com.perrinresearch.foundry.ui.theme.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { FoundryApp() }
    }
}

private val kanbanCols = listOf(
    "backlog" to "Backlog",
    "doing" to "Doing",
    "testing" to "Testing",
    "done" to "Done",
)

@Composable
fun FoundryApp() {
    val api = remember { FoundryApi() }
    var token by remember { mutableStateOf<String?>(null) }
    var tab by remember { mutableIntStateOf(0) }
    var projects by remember { mutableStateOf<List<Project>>(emptyList()) }
    var selected by remember { mutableStateOf<Project?>(null) }
    var tasks by remember { mutableStateOf<List<Task>>(emptyList()) }
    var prompts by remember { mutableStateOf<List<AgentPrompt>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    MaterialTheme(colorScheme = darkColorScheme(background = Bg, surface = BgElevated, primary = Ember)) {
        Surface(modifier = Modifier.fillMaxSize(), color = Bg) {
            if (token == null) {
                LoginScreen(
                    onLogin = { email, pass ->
                        scope.launch {
                            try {
                                val t = withContext(Dispatchers.IO) { api.login(email, pass) }
                                api.setToken(t)
                                token = t
                                projects = withContext(Dispatchers.IO) { api.listProjects() }
                                error = null
                            } catch (e: Exception) {
                                error = e.message
                            }
                        }
                    },
                    error = error,
                )
            } else {
                Column(Modifier.fillMaxSize()) {
                    Row(
                        Modifier.fillMaxWidth().background(BgElevated).padding(12.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Text("Perrin//Research", color = TextPrimary, fontWeight = FontWeight.Bold)
                        TextButton(onClick = { token = null; selected = null }) {
                            Text("Sign out", color = TextMuted)
                        }
                    }
                    TabRow(selectedTabIndex = tab, containerColor = BgElevated, contentColor = Ember) {
                        Tab(selected = tab == 0, onClick = {
                            tab = 0; selected = null
                            scope.launch { projects = withContext(Dispatchers.IO) { api.listProjects() } }
                        }) { Text("Projects") }
                        Tab(selected = tab == 1, onClick = {
                            tab = 1
                            scope.launch { prompts = withContext(Dispatchers.IO) { api.listPrompts() } }
                        }) { Text("Agents") }
                    }
                    when {
                        tab == 1 -> AgentQueueScreen(prompts, onRefresh = {
                            scope.launch { prompts = withContext(Dispatchers.IO) { api.listPrompts() } }
                        }, onStatus = { id, status ->
                            scope.launch {
                                withContext(Dispatchers.IO) { api.updatePromptStatus(id, status) }
                                prompts = withContext(Dispatchers.IO) { api.listPrompts() }
                            }
                        })
                        selected != null -> ProjectDetailScreen(
                            project = selected!!,
                            tasks = tasks,
                            onBack = { selected = null },
                            onMoveTask = { taskId, status ->
                                scope.launch {
                                    withContext(Dispatchers.IO) { api.updateTaskStatus(taskId, status) }
                                    tasks = withContext(Dispatchers.IO) { api.listTasks(selected!!.id) }
                                }
                            },
                        )
                        else -> ProjectListScreen(projects, onSelect = { p ->
                            selected = p
                            scope.launch { tasks = withContext(Dispatchers.IO) { api.listTasks(p.id) } }
                        })
                    }
                }
            }
        }
    }
}

@Composable
fun LoginScreen(onLogin: (String, String) -> Unit, error: String?) {
    var email by remember { mutableStateOf("scott@perrinresearch.com") }
    var password by remember { mutableStateOf("") }
    var passwordVisible by remember { mutableStateOf(false) }
    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text("INTERNAL · FOUNDRY", color = Ember, fontFamily = FontFamily.Monospace, fontSize = 12.sp)
        Text("Perrin//Research", color = TextPrimary, fontSize = 28.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(16.dp))
        OutlinedTextField(
            value = email,
            onValueChange = { email = it },
            label = { Text("Email") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text("Password") },
            visualTransformation = if (passwordVisible) VisualTransformation.None else PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            trailingIcon = {
                IconButton(onClick = { passwordVisible = !passwordVisible }) {
                    Icon(
                        imageVector = if (passwordVisible) Icons.Filled.Visibility else Icons.Filled.VisibilityOff,
                        contentDescription = if (passwordVisible) "Hide password" else "Show password",
                        tint = TextMuted
                    )
                }
            },
            modifier = Modifier.fillMaxWidth()
        )
        error?.let { Text(it, color = Ember, modifier = Modifier.padding(top = 8.dp)) }
        Spacer(Modifier.height(16.dp))
        Button(onClick = { onLogin(email, password) }, colors = ButtonDefaults.buttonColors(containerColor = Ember)) {
            Text("Sign in", color = Bg)
        }
    }
}

@Composable
fun ProjectListScreen(projects: List<Project>, onSelect: (Project) -> Unit) {
    LazyColumn(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        items(projects) { p ->
            Card(
                Modifier.fillMaxWidth().clickable { onSelect(p) },
                colors = CardDefaults.cardColors(containerColor = BgElevated),
            ) {
                Column(Modifier.padding(16.dp)) {
                    Text(p.ref, color = Ember, fontFamily = FontFamily.Monospace, fontSize = 12.sp)
                    Text(p.name, color = TextPrimary, fontWeight = FontWeight.Bold)
                    Text("${p.stage} · ${p.form}", color = TextMuted, fontSize = 12.sp)
                }
            }
        }
    }
}

@Composable
fun ProjectDetailScreen(project: Project, tasks: List<Task>, onBack: () -> Unit, onMoveTask: (Int, String) -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
        TextButton(onClick = onBack) { Text("← Projects", color = Ember) }
        Text(project.ref, color = Ember, fontFamily = FontFamily.Monospace, fontSize = 12.sp)
        Text(project.name, color = TextPrimary, fontSize = 22.sp, fontWeight = FontWeight.Bold)
        Text(project.hypothesis, color = TextMuted, modifier = Modifier.padding(vertical = 8.dp))
        kanbanCols.forEach { (status, label) ->
            Text(label.uppercase(), color = TextMuted, fontFamily = FontFamily.Monospace, fontSize = 11.sp, modifier = Modifier.padding(top = 12.dp))
            tasks.filter { it.status == status }.forEach { t ->
                Card(
                    Modifier.fillMaxWidth().padding(vertical = 4.dp),
                    colors = CardDefaults.cardColors(containerColor = BgRaised),
                ) {
                    Column(Modifier.padding(12.dp)) {
                        Text(t.title, color = TextPrimary)
                        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            kanbanCols.forEach { (s, l) ->
                                if (s != status) {
                                    TextButton(onClick = { onMoveTask(t.id, s) }) {
                                        Text(l, fontSize = 10.sp, color = Ember)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun AgentQueueScreen(prompts: List<AgentPrompt>, onRefresh: () -> Unit, onStatus: (Int, String) -> Unit) {
    LaunchedEffect(Unit) { onRefresh() }
    val queue = prompts.filter { it.status == "pending" || it.status == "in_progress" }
    LazyColumn(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        items(queue) { pr ->
            Card(
                Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = BgElevated),
            ) {
                Column(Modifier.padding(16.dp)) {
                    Text("${pr.projectRef ?: "—"} · ${pr.taskTitle ?: "Task"} · ${pr.status}", color = TextMuted, fontSize = 11.sp, fontFamily = FontFamily.Monospace)
                    Text(pr.title, color = TextPrimary, fontWeight = FontWeight.Bold)
                    Text(pr.promptText, color = TextMuted, fontSize = 13.sp, modifier = Modifier.padding(vertical = 8.dp))
                    if (pr.status == "pending") {
                        Button(onClick = { onStatus(pr.id, "in_progress") }, colors = ButtonDefaults.buttonColors(containerColor = Ember)) {
                            Text("Claim", color = Bg)
                        }
                    }
                    if (pr.status == "in_progress") {
                        Button(onClick = { onStatus(pr.id, "completed") }, colors = ButtonDefaults.buttonColors(containerColor = Color.Transparent)) {
                            Text("Complete", color = Ember)
                        }
                    }
                }
            }
        }
    }
}
