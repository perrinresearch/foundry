const API = "";
const TOKEN_KEY = "foundry_token";

const KANBAN_COLS = [
  { id: "backlog", label: "Backlog" },
  { id: "doing", label: "Doing" },
  { id: "testing", label: "Testing" },
  { id: "done", label: "Done" },
];

const PROMPT_STATUSES = [
  { id: "pending", label: "Pending" },
  { id: "in_progress", label: "In progress" },
  { id: "completed", label: "Completed" },
  { id: "cancelled", label: "Cancelled" },
];

const PROJECT_STAGES = [
  { id: "idea", label: "Idea" },
  { id: "prototype", label: "Prototype" },
  { id: "evaluation", label: "Evaluation" },
  { id: "shipped", label: "Shipped" },
];

const PROJECT_STATUSES = [
  { id: "active", label: "Active" },
  { id: "archived", label: "Archived" },
];

const PROJECT_VISIBILITIES = [
  { id: "public", label: "Public (on site)" },
  { id: "private", label: "Private (Foundry only)" },
];

const REPO_SLUG_RE = /^[a-z][a-z0-9-]{1,46}$/;

let state = {
  view: "projects",
  projects: [],
  selectedProject: null,
  tasks: [],
  prompts: [],
  users: [],
  me: null,
};

function token() {
  return localStorage.getItem(TOKEN_KEY);
}

function setToken(t) {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
}

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (token()) headers.Authorization = `Bearer ${token()}`;
  const res = await fetch(`${API}${path}`, { ...opts, headers });
    if (res.status === 401) {
      setToken(null);
      showLogin();
      throw new Error("Unauthorized");
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const detail = err.detail;
      const message = Array.isArray(detail)
        ? detail.map((d) => d.msg || `${d.loc?.slice(-1)[0] || "field"}: ${d.msg || "invalid"}`).join(", ")
        : typeof detail === "string"
          ? detail
          : detail?.message || res.statusText;
      throw new Error(message);
    }
  if (res.status === 204) return null;
  return res.json();
}

function showLogin() {
  document.getElementById("login-view").classList.remove("hidden");
  document.getElementById("app-view").classList.add("hidden");
  state.me = null;
  closeUserMenu();
  updateAdminNav();
}

function showApp() {
  document.getElementById("login-view").classList.add("hidden");
  document.getElementById("app-view").classList.remove("hidden");
}

function updateAdminNav() {
  const usersItem = document.getElementById("menu-users");
  if (!usersItem) return;
  if (state.me?.is_admin) usersItem.classList.remove("hidden");
  else {
    usersItem.classList.add("hidden");
    if (state.view === "users") {
      state.view = "projects";
      document.querySelectorAll(".nav-tabs button").forEach((b) => {
        b.classList.toggle("active", b.dataset.view === "projects");
      });
    }
  }
}

function closeUserMenu() {
  const toggle = document.getElementById("user-menu-toggle");
  const dropdown = document.getElementById("user-menu-dropdown");
  toggle?.setAttribute("aria-expanded", "false");
  dropdown?.classList.add("hidden");
}

function toggleUserMenu() {
  const toggle = document.getElementById("user-menu-toggle");
  const dropdown = document.getElementById("user-menu-dropdown");
  if (!toggle || !dropdown) return;
  const open = toggle.getAttribute("aria-expanded") === "true";
  toggle.setAttribute("aria-expanded", String(!open));
  dropdown.classList.toggle("hidden", open);
}

async function loadMe() {
  state.me = await api("/api/auth/me");
  updateAdminNav();
  return state.me;
}

async function afterLogin() {
  showApp();
  await loadMe();
  if (state.view === "users" && state.me?.is_admin) loadUsers();
  else if (state.view === "agents") loadPrompts();
  else loadProjects();
}

function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
}

async function loadProjects() {
  state.projects = await api("/api/projects");
  state.selectedProject = null;
  render();
}

async function loadProject(id) {
  state.selectedProject = await api(`/api/projects/${id}`);
  state.tasks = await api(`/api/projects/${id}/tasks`);
  state.prompts = await api(`/api/agent-prompts?project_id=${id}`);
  render();
}

async function loadPrompts() {
  const all = await api("/api/agent-prompts");
  state.prompts = queuePrompts(all);
  render();
}

function queuePrompts(prompts) {
  return sortPrompts(
    prompts.filter((p) => p.status === "pending" || p.status === "in_progress")
  );
}

function sortPrompts(prompts) {
  return [...prompts].sort((a, b) => {
    if (b.priority !== a.priority) return b.priority - a.priority;
    return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
  });
}

async function movePromptInQueue(promptId, delta) {
  const sorted = sortPrompts(state.prompts);
  const idx = sorted.findIndex((p) => p.id === promptId);
  const newIdx = idx + delta;
  if (idx < 0 || newIdx < 0 || newIdx >= sorted.length) return;
  [sorted[idx], sorted[newIdx]] = [sorted[newIdx], sorted[idx]];
  state.prompts = queuePrompts(
    await api("/api/agent-prompts/reorder", {
      method: "POST",
      body: JSON.stringify({ ordered_ids: sorted.map((p) => p.id) }),
    })
  );
  render();
}

function renderProjects() {
  const main = document.getElementById("main");
  main.innerHTML = "";
  const toolbar = el("div", "toolbar");
  toolbar.innerHTML = `<p class="overline">Pipeline</p>`;
  const addBtn = el("button", "btn btn-sm", "New project");
  addBtn.onclick = () => showNewProjectForm();
  toolbar.appendChild(addBtn);
  const spacer = el("span", "toolbar-spacer");
  toolbar.appendChild(spacer);
  const publishBtn = el("button", "btn btn-sm", "Publish public site");
  publishBtn.onclick = () => publishPublicSite(publishBtn);
  toolbar.appendChild(publishBtn);
  main.appendChild(toolbar);
  main.appendChild(
    el("p", "field-hint toolbar-hint", "Syncs active portfolio projects and deploys to the public site.")
  );

  const grid = el("div", "project-grid");
  for (const p of state.projects) {
    const card = el("div", "project-card");
    card.innerHTML = `
      <div class="ref mono">${p.ref}</div>
      <h3>${escapeHtml(p.name)}</h3>
      <div class="stage">${p.stage} · ${p.status} · ${p.visibility || "public"} · ${p.form}</div>
      ${p.repo_slug ? `<div class="repo-slug mono">repo: ${escapeHtml(p.repo_slug)}</div>` : ""}
    `;
    card.onclick = () => loadProject(p.id);
    grid.appendChild(card);
  }
  main.appendChild(grid);
}

function renderProjectDetail() {
  const p = state.selectedProject;
  const main = document.getElementById("main");
  main.innerHTML = "";
  const back = el("button", "btn btn-sm secondary", "← All projects");
  back.onclick = loadProjects;
  main.appendChild(back);

  const head = el("div");
  head.innerHTML = `
    <p class="overline mono">${p.ref}</p>
    <h2>${escapeHtml(p.name)}</h2>
    <p class="project-meta mono">${escapeHtml(p.stage)} · ${escapeHtml(p.status)} · ${escapeHtml(p.visibility || "public")} · ${escapeHtml(p.form)}</p>
    ${p.repo_slug ? `<p class="project-meta mono">GitHub: perrinresearch/${escapeHtml(p.repo_slug)}</p>` : ""}
    <p style="color:var(--color-text-muted)">${escapeHtml(p.hypothesis)}</p>
  `;
  main.appendChild(head);

  const toolbar = el("div", "toolbar");
  const editProject = el("button", "btn btn-sm secondary", "Edit project");
  editProject.type = "button";
  editProject.onclick = () => showProjectEditor(p);
  toolbar.appendChild(editProject);
  const addTask = el("button", "btn btn-sm", "+ Task");
  addTask.onclick = () => {
    const title = prompt("Task title");
    if (title) api(`/api/projects/${p.id}/tasks`, { method: "POST", body: JSON.stringify({ title }) }).then(() => loadProject(p.id));
  };
  toolbar.appendChild(addTask);
  main.appendChild(toolbar);

  const board = el("div", "kanban");
  for (const col of KANBAN_COLS) {
    const column = el("div", "kanban-col");
    column.innerHTML = `<h4>${col.label}</h4>`;
    const tasks = state.tasks.filter((t) => t.status === col.id);
    for (const t of tasks) {
      const taskPrompts = state.prompts.filter((pr) => Number(pr.task_id) === Number(t.id));
      const card = el("div", "task-card");
      const titleEl = el("div", "task-title", escapeHtml(t.title));
      card.appendChild(titleEl);
      if (t.description) {
        card.appendChild(el("p", "task-desc", escapeHtml(t.description)));
      }
      if (taskPrompts.length) {
        const promptList = el("ul", "task-prompt-list");
        for (const pr of taskPrompts) {
          const item = el("li", "task-prompt-item");
          const label = el("span", "task-prompt-label");
          label.innerHTML = `<span class="mono">${escapeHtml(pr.status)}</span> ${escapeHtml(pr.title)}`;
          item.appendChild(label);
          const itemActions = el("span", "task-prompt-actions");
          const editPr = el("button", "link-btn", "Edit");
          editPr.type = "button";
          editPr.onclick = () => showPromptEditor(pr);
          const delPr = el("button", "link-btn link-btn-danger", "Delete");
          delPr.type = "button";
          delPr.onclick = () => deletePrompt(pr);
          itemActions.append(editPr, delPr);
          item.appendChild(itemActions);
          promptList.appendChild(item);
        }
        card.appendChild(promptList);
      }
      const actions = el("div", "task-actions");
      const editBtn = el("button", "btn btn-sm secondary task-edit-btn", "Edit");
      editBtn.type = "button";
      editBtn.onclick = () => showTaskEditor(t);
      actions.appendChild(editBtn);
      const promptBtn = el("button", "btn btn-sm secondary task-edit-btn", "+ Prompt");
      promptBtn.type = "button";
      promptBtn.onclick = () => showNewPromptForm(t.id);
      actions.appendChild(promptBtn);
      const sel = document.createElement("select");
      sel.className = "task-status-select";
      for (const c of KANBAN_COLS) {
        const o = document.createElement("option");
        o.value = c.id;
        o.textContent = c.label;
        if (c.id === t.status) o.selected = true;
        sel.appendChild(o);
      }
      sel.onchange = () =>
        api(`/api/tasks/${t.id}`, { method: "PATCH", body: JSON.stringify({ status: sel.value }) }).then(
          () => loadProject(p.id)
        );
      actions.appendChild(sel);
      card.appendChild(actions);
      column.appendChild(card);
    }
    board.appendChild(column);
  }
  main.appendChild(board);
}

function renderAgents() {
  const main = document.getElementById("main");
  main.innerHTML = "";
  const toolbar = el("div", "toolbar");
  toolbar.innerHTML = `<p class="overline">Agent queue</p>`;
  main.appendChild(toolbar);

  const list = el("div", "prompt-list");
  const sorted = sortPrompts(state.prompts);
  sorted.forEach((pr, index) => {
    const card = el("div", "prompt-card");
    const head = el("div", "prompt-card-head");
    const reorder = el("div", "prompt-reorder");
    const upBtn = el("button", "reorder-btn", "↑");
    upBtn.type = "button";
    upBtn.title = "Move up";
    upBtn.disabled = index === 0;
    upBtn.onclick = () => movePromptInQueue(pr.id, -1);
    const downBtn = el("button", "reorder-btn", "↓");
    downBtn.type = "button";
    downBtn.title = "Move down";
    downBtn.disabled = index === sorted.length - 1;
    downBtn.onclick = () => movePromptInQueue(pr.id, 1);
    reorder.append(upBtn, downBtn, el("span", "prompt-rank mono", `#${index + 1}`));
    head.appendChild(reorder);
    const body = el("div", "prompt-card-body");
    body.innerHTML = `
      <div class="meta mono">${escapeHtml(pr.project_ref || "—")} · ${escapeHtml(pr.task_title || "Task")} · ${pr.status}</div>
      <h4>${escapeHtml(pr.title)}</h4>
      <pre>${escapeHtml(pr.prompt_text)}</pre>
    `;
    head.appendChild(body);
    card.appendChild(head);
    const actions = el("div", "prompt-card-actions");
    const editBtn = el("button", "btn btn-sm secondary", "Edit");
    editBtn.type = "button";
    editBtn.onclick = () => showPromptEditor(pr);
    actions.appendChild(editBtn);
    const delBtn = el("button", "btn btn-sm secondary task-delete-btn", "Delete");
    delBtn.type = "button";
    delBtn.onclick = () => deletePrompt(pr);
    actions.appendChild(delBtn);
    if (pr.status === "pending") {
      const claim = el("button", "btn btn-sm", "Mark in progress");
      claim.onclick = () => api(`/api/agent-prompts/${pr.id}`, { method: "PATCH", body: JSON.stringify({ status: "in_progress" }) }).then(reloadPromptViews);
      actions.appendChild(claim);
    }
    if (pr.status === "in_progress") {
      const done = el("button", "btn btn-sm secondary", "Mark complete");
      done.onclick = () => showPromptEditor({ ...pr, _focusNotes: true });
      actions.appendChild(done);
    }
    card.appendChild(actions);
    list.appendChild(card);
  });
  main.appendChild(list);
}

function closeProjectCreator() {
  document.getElementById("project-creator-overlay")?.remove();
}

function showNewProjectForm() {
  closeProjectCreator();
  closeProjectEditor();
  closeTaskEditor();
  closePromptEditor();

  const overlay = el("div", "task-editor-overlay");
  overlay.id = "project-creator-overlay";

  const panel = el("div", "task-editor login-card");
  panel.innerHTML = `
    <p class="overline">New project</p>
    <label for="np-ref">Ref</label>
    <input id="np-ref" type="text" placeholder="PR-007" />
    <p class="field-hint">Uppercase letters, numbers, and hyphens only (e.g. PR-007).</p>
    <label for="np-name">Name</label>
    <input id="np-name" type="text" placeholder="Project name" />
    <label for="np-hyp">Hypothesis</label>
    <textarea id="np-hyp" placeholder="What are you testing?"></textarea>
    <label for="np-form">Form</label>
    <select id="np-form">
      <option value="interactive">Interactive (application)</option>
      <option value="static">Static (writing)</option>
    </select>
    <label for="np-stage">Pipeline stage</label>
    <select id="np-stage"></select>
    <label for="np-visibility">Visibility</label>
    <select id="np-visibility"></select>
    <p class="field-hint">Public projects appear on the site when you publish. Private stay in Foundry only.</p>
    <label for="np-repo">GitHub repo (optional)</label>
    <input id="np-repo" type="text" placeholder="my-project-slug" autocomplete="off" />
    <p class="field-hint">Lowercase slug for local WSL provision (e.g. restore79). Blank = no GitHub repo.</p>
    <div class="task-editor-buttons">
      <button type="button" class="btn" id="np-save">Create</button>
      <button type="button" class="btn btn-sm secondary" id="np-cancel">Cancel</button>
    </div>
    <p id="np-error" class="error hidden"></p>
  `;

  const stageSel = panel.querySelector("#np-stage");
  for (const s of PROJECT_STAGES) {
    const o = document.createElement("option");
    o.value = s.id;
    o.textContent = s.label;
    if (s.id === "idea") o.selected = true;
    stageSel.appendChild(o);
  }
  const visSel = panel.querySelector("#np-visibility");
  for (const v of PROJECT_VISIBILITIES) {
    const o = document.createElement("option");
    o.value = v.id;
    o.textContent = v.label;
    if (v.id === "public") o.selected = true;
    visSel.appendChild(o);
  }

  panel.querySelector("#np-cancel").onclick = closeProjectCreator;
  panel.querySelector("#np-save").onclick = async () => {
    const errEl = panel.querySelector("#np-error");
    errEl.classList.add("hidden");
    const ref = panel.querySelector("#np-ref").value.trim().toUpperCase();
    const name = panel.querySelector("#np-name").value.trim();
    const hypothesis = panel.querySelector("#np-hyp").value.trim();
    const repoSlug = panel.querySelector("#np-repo").value.trim().toLowerCase();
    if (!ref || !name) {
      errEl.textContent = "Ref and name are required.";
      errEl.classList.remove("hidden");
      return;
    }
    if (!/^[A-Z0-9-]+$/.test(ref)) {
      errEl.textContent = "Ref must use only letters, numbers, and hyphens (e.g. PR-007).";
      errEl.classList.remove("hidden");
      return;
    }
    if (repoSlug && !REPO_SLUG_RE.test(repoSlug)) {
      errEl.textContent =
        "GitHub repo slug must be lowercase, start with a letter, and use only letters, numbers, and hyphens (2–47 chars).";
      errEl.classList.remove("hidden");
      return;
    }
    try {
      await api("/api/projects", {
        method: "POST",
        body: JSON.stringify({
          ref,
          name,
          hypothesis,
          form: panel.querySelector("#np-form").value,
          stage: stageSel.value,
          visibility: visSel.value,
          repo_slug: repoSlug,
        }),
      });
      closeProjectCreator();
      loadProjects();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove("hidden");
    }
  };

  overlay.appendChild(panel);
  document.body.appendChild(overlay);
  panel.querySelector("#np-ref").focus();
}

function reloadPromptViews() {
  if (state.view === "agents") loadPrompts();
  else if (state.selectedProject) loadProject(state.selectedProject.id);
}

function showProjectEditor(project) {
  closeProjectEditor();
  closeTaskEditor();
  closePromptEditor();

  const overlay = el("div", "task-editor-overlay");
  overlay.id = "project-editor-overlay";

  const panel = el("div", "task-editor login-card");
  panel.innerHTML = `
    <p class="overline">Edit project</p>
    <p class="prompt-task-context mono">${escapeHtml(project.ref)}</p>
    <label for="pj-name">Name</label>
    <input id="pj-name" type="text" />
    <label for="pj-hyp">Hypothesis</label>
    <textarea id="pj-hyp" placeholder="What are you testing?"></textarea>
    <label for="pj-stage">Pipeline stage</label>
    <select id="pj-stage"></select>
    <p class="field-hint">Name, hypothesis, and stage sync to the public site when you publish from the Projects view.</p>
    <label for="pj-visibility">Visibility</label>
    <select id="pj-visibility"></select>
    <p class="field-hint">Private projects stay in Foundry and are removed from the public site on publish.</p>
    <label for="pj-repo">GitHub repo (optional)</label>
    <input id="pj-repo" type="text" placeholder="my-project-slug" autocomplete="off" />
    <p class="field-hint">Lowercase slug for local WSL provision; blank = no GitHub.</p>
    <label for="pj-status">Project status</label>
    <select id="pj-status"></select>
    <p class="field-hint">Internal only — archived projects stay out of site sync.</p>
    <div class="task-editor-buttons">
      <button type="button" class="btn" id="pj-save">Save</button>
      <button type="button" class="btn btn-sm secondary" id="pj-cancel">Cancel</button>
    </div>
    <p id="pj-error" class="error hidden"></p>
  `;

  panel.querySelector("#pj-name").value = project.name || "";
  panel.querySelector("#pj-hyp").value = project.hypothesis || "";
  panel.querySelector("#pj-repo").value = project.repo_slug || "";

  const stageSel = panel.querySelector("#pj-stage");
  for (const s of PROJECT_STAGES) {
    const o = document.createElement("option");
    o.value = s.id;
    o.textContent = s.label;
    if (s.id === project.stage) o.selected = true;
    stageSel.appendChild(o);
  }
  const statusSel = panel.querySelector("#pj-status");
  for (const s of PROJECT_STATUSES) {
    const o = document.createElement("option");
    o.value = s.id;
    o.textContent = s.label;
    if (s.id === project.status) o.selected = true;
    statusSel.appendChild(o);
  }
  const visSel = panel.querySelector("#pj-visibility");
  for (const v of PROJECT_VISIBILITIES) {
    const o = document.createElement("option");
    o.value = v.id;
    o.textContent = v.label;
    if (v.id === (project.visibility || "public")) o.selected = true;
    visSel.appendChild(o);
  }

  panel.querySelector("#pj-cancel").onclick = closeProjectEditor;
  panel.querySelector("#pj-save").onclick = async () => {
    const errEl = panel.querySelector("#pj-error");
    errEl.classList.add("hidden");
    const name = panel.querySelector("#pj-name").value.trim();
    const repoSlug = panel.querySelector("#pj-repo").value.trim().toLowerCase();
    if (!name) {
      errEl.textContent = "Name is required.";
      errEl.classList.remove("hidden");
      return;
    }
    if (repoSlug && !REPO_SLUG_RE.test(repoSlug)) {
      errEl.textContent =
        "GitHub repo slug must be lowercase, start with a letter, and use only letters, numbers, and hyphens (2–47 chars).";
      errEl.classList.remove("hidden");
      return;
    }
    try {
      await api(`/api/projects/${project.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name,
          hypothesis: panel.querySelector("#pj-hyp").value.trim(),
          stage: stageSel.value,
          status: statusSel.value,
          visibility: visSel.value,
          repo_slug: repoSlug,
        }),
      });
      closeProjectEditor();
      loadProject(project.id);
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove("hidden");
    }
  };

  overlay.appendChild(panel);
  document.body.appendChild(overlay);
  panel.querySelector("#pj-name").focus();
}

function closeProjectEditor() {
  document.getElementById("project-editor-overlay")?.remove();
}

async function deletePrompt(prompt) {
  if (!confirm(`Delete prompt "${prompt.title}"?`)) return;
  await api(`/api/agent-prompts/${prompt.id}`, { method: "DELETE" });
  reloadPromptViews();
}

function showNewPromptForm(taskId) {
  showPromptEditor(null, taskId);
}

function showPromptEditor(prompt, taskId) {
  closePromptEditor();
  closeTaskEditor();
  const isEdit = Boolean(prompt);
  const resolvedTaskId = isEdit ? prompt.task_id : taskId;
  const task =
    state.tasks.find((t) => Number(t.id) === Number(resolvedTaskId)) ||
    (isEdit ? { title: prompt.task_title || "Task" } : null);

  const overlay = el("div", "task-editor-overlay");
  overlay.id = "prompt-editor-overlay";

  const panel = el("div", "task-editor login-card");
  panel.innerHTML = `
    <p class="overline">${isEdit ? "Edit prompt" : "Agent prompt"}</p>
    ${task ? `<p class="prompt-task-context">${escapeHtml(task.title)}</p>` : ""}
    <label for="pe-title">Title</label>
    <input id="pe-title" type="text" placeholder="Short label for the agent" />
    <label for="pe-text">Prompt</label>
    <textarea id="pe-text" placeholder="Instructions for the agent…"></textarea>
    ${
      isEdit
        ? `
    <label for="pe-status">Status</label>
    <select id="pe-status"></select>
    <label for="pe-priority">Priority</label>
    <input id="pe-priority" type="number" step="1" />
    <label for="pe-notes">Result notes</label>
    <textarea id="pe-notes" placeholder="Optional output or notes from the agent…"></textarea>
    `
        : ""
    }
    <div class="task-editor-buttons">
      <button type="button" class="btn" id="pe-save">${isEdit ? "Save" : "Add prompt"}</button>
      <button type="button" class="btn btn-sm secondary" id="pe-cancel">Cancel</button>
      ${isEdit ? `<button type="button" class="btn btn-sm secondary task-delete-btn" id="pe-delete">Delete</button>` : ""}
    </div>
    <p id="pe-error" class="error hidden"></p>
  `;

  panel.querySelector("#pe-title").value = isEdit ? prompt.title : "";
  panel.querySelector("#pe-text").value = isEdit ? prompt.prompt_text : "";

  if (isEdit) {
    const statusSel = panel.querySelector("#pe-status");
    for (const s of PROMPT_STATUSES) {
      const o = document.createElement("option");
      o.value = s.id;
      o.textContent = s.label;
      if (s.id === prompt.status) o.selected = true;
      statusSel.appendChild(o);
    }
    panel.querySelector("#pe-priority").value = String(prompt.priority ?? 0);
    panel.querySelector("#pe-notes").value = prompt.result_notes || "";
    if (prompt._focusNotes) {
      panel.querySelector("#pe-status").value = "completed";
    }
    panel.querySelector("#pe-delete").onclick = async () => {
      closePromptEditor();
      await deletePrompt(prompt);
    };
  }

  panel.querySelector("#pe-cancel").onclick = closePromptEditor;
  panel.querySelector("#pe-save").onclick = async () => {
    const errEl = panel.querySelector("#pe-error");
    errEl.classList.add("hidden");
    const title = panel.querySelector("#pe-title").value.trim();
    const promptText = panel.querySelector("#pe-text").value.trim();
    if (!title || !promptText) {
      errEl.textContent = "Title and prompt text are required.";
      errEl.classList.remove("hidden");
      return;
    }
    try {
      if (isEdit) {
        await api(`/api/agent-prompts/${prompt.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            title,
            prompt_text: promptText,
            status: panel.querySelector("#pe-status").value,
            priority: Number(panel.querySelector("#pe-priority").value) || 0,
            result_notes: panel.querySelector("#pe-notes").value.trim(),
          }),
        });
      } else {
        await api("/api/agent-prompts", {
          method: "POST",
          body: JSON.stringify({ task_id: taskId, title, prompt_text: promptText }),
        });
      }
      closePromptEditor();
      reloadPromptViews();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove("hidden");
    }
  };

  overlay.appendChild(panel);
  document.body.appendChild(overlay);
  (prompt?._focusNotes ? panel.querySelector("#pe-notes") : panel.querySelector("#pe-title")).focus();
}

function closePromptEditor() {
  document.getElementById("prompt-editor-overlay")?.remove();
}

function closeTaskEditor() {
  document.getElementById("task-editor-overlay")?.remove();
}

function showTaskEditor(task) {
  closeTaskEditor();
  const overlay = el("div", "task-editor-overlay");
  overlay.id = "task-editor-overlay";

  const panel = el("div", "task-editor login-card");
  panel.innerHTML = `
    <p class="overline">Edit task</p>
    <label for="te-title">Title</label>
    <input id="te-title" type="text" value="" />
    <label for="te-desc">Description</label>
    <textarea id="te-desc" placeholder="Optional details…"></textarea>
    <label for="te-status">Status</label>
    <select id="te-status"></select>
    <div class="task-editor-buttons">
      <button type="button" class="btn" id="te-save">Save</button>
      <button type="button" class="btn btn-sm secondary" id="te-cancel">Cancel</button>
      <button type="button" class="btn btn-sm secondary task-delete-btn" id="te-delete">Delete</button>
    </div>
    <p id="te-error" class="error hidden"></p>
  `;

  panel.querySelector("#te-title").value = task.title;
  panel.querySelector("#te-desc").value = task.description || "";
  const statusSel = panel.querySelector("#te-status");
  for (const col of KANBAN_COLS) {
    const o = document.createElement("option");
    o.value = col.id;
    o.textContent = col.label;
    if (col.id === task.status) o.selected = true;
    statusSel.appendChild(o);
  }

  panel.querySelector("#te-cancel").onclick = closeTaskEditor;
  panel.querySelector("#te-delete").onclick = async () => {
    if (!confirm(`Delete task "${task.title}"?`)) return;
    await api(`/api/tasks/${task.id}`, { method: "DELETE" });
    closeTaskEditor();
    loadProject(state.selectedProject.id);
  };
  panel.querySelector("#te-save").onclick = async () => {
    const errEl = panel.querySelector("#te-error");
    errEl.classList.add("hidden");
    const title = panel.querySelector("#te-title").value.trim();
    if (!title) {
      errEl.textContent = "Title is required.";
      errEl.classList.remove("hidden");
      return;
    }
    try {
      await api(`/api/tasks/${task.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title,
          description: panel.querySelector("#te-desc").value.trim(),
          status: statusSel.value,
        }),
      });
      closeTaskEditor();
      loadProject(state.selectedProject.id);
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove("hidden");
    }
  };

  overlay.appendChild(panel);
  document.body.appendChild(overlay);
  panel.querySelector("#te-title").focus();
}

async function publishPublicSite(btn) {
  const logId = "deploy-log";
  let logEl = document.getElementById(logId);
  if (!logEl) {
    logEl = el("pre", "deploy-log mono");
    logEl.id = logId;
    document.getElementById("main").appendChild(logEl);
  }
  logEl.textContent = "Building and deploying site…";
  btn.disabled = true;
  btn.textContent = "Publishing…";
  try {
    const res = await fetch(`${API}/api/site/deploy`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token()}`,
      },
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = body.detail || body;
      const msg = typeof detail === "string" ? detail : detail.message || res.statusText;
      logEl.textContent = [msg, detail.stdout, detail.stderr].filter(Boolean).join("\n\n");
      throw new Error(msg);
    }
    logEl.textContent = [
      body.message,
      body.synced_refs?.length ? `Synced: ${body.synced_refs.join(", ")}` : "",
      `Target: ${body.target_url}`,
      body.stdout,
    ].filter(Boolean).join("\n\n");
  } catch (err) {
    if (logEl.textContent === "Building and deploying site…") {
      logEl.textContent = err.message;
    }
  } finally {
    btn.disabled = false;
    btn.textContent = "Publish public site";
  }
}

function render() {
  if (state.view === "agents") renderAgents();
  else if (state.view === "users") renderUsers();
  else if (state.selectedProject) renderProjectDetail();
  else renderProjects();
}

async function loadUsers() {
  state.users = await api("/api/users");
  state.selectedProject = null;
  state.view = "users";
  render();
}

function renderUsers() {
  const main = document.getElementById("main");
  main.innerHTML = "";
  const toolbar = el("div", "toolbar");
  toolbar.innerHTML = `<p class="overline">Users</p>`;
  const addBtn = el("button", "btn btn-sm", "New user");
  addBtn.onclick = () => showUserCreator();
  toolbar.appendChild(addBtn);
  main.appendChild(toolbar);

  const table = el("table", "users-table");
  table.innerHTML = `
    <thead>
      <tr>
        <th>Email</th>
        <th>Name</th>
        <th>Role</th>
        <th>Status</th>
        <th>Actions</th>
      </tr>
    </thead>
  `;
  const tbody = document.createElement("tbody");
  for (const u of state.users) {
    const tr = document.createElement("tr");
    if (!u.is_active) tr.classList.add("user-revoked");
    tr.innerHTML = `
      <td class="mono">${escapeHtml(u.email)}</td>
      <td>${escapeHtml(u.name)}</td>
      <td>${u.is_admin ? "Admin" : "User"}</td>
      <td>${u.is_active ? "Active" : "Revoked"}</td>
      <td class="user-actions"></td>
    `;
    const actions = tr.querySelector(".user-actions");

    const setPw = el("button", "btn btn-sm secondary", "Set password");
    setPw.type = "button";
    setPw.onclick = () => showSetPasswordForm(u);
    actions.appendChild(setPw);

    const toggleAdmin = el(
      "button",
      "btn btn-sm secondary",
      u.is_admin ? "Demote" : "Make admin"
    );
    toggleAdmin.type = "button";
    toggleAdmin.onclick = async () => {
      try {
        await api(`/api/users/${u.id}`, {
          method: "PATCH",
          body: JSON.stringify({ is_admin: !u.is_admin }),
        });
        await loadUsers();
        await loadMe();
      } catch (err) {
        alert(err.message);
      }
    };
    actions.appendChild(toggleAdmin);

    const toggleActive = el(
      "button",
      "btn btn-sm secondary",
      u.is_active ? "Revoke" : "Restore"
    );
    toggleActive.type = "button";
    toggleActive.onclick = async () => {
      const action = u.is_active ? "revoke access for" : "restore access for";
      if (!confirm(`${action} ${u.email}?`)) return;
      try {
        await api(`/api/users/${u.id}`, {
          method: "PATCH",
          body: JSON.stringify({ is_active: !u.is_active }),
        });
        await loadUsers();
      } catch (err) {
        alert(err.message);
      }
    };
    actions.appendChild(toggleActive);

    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  main.appendChild(table);
}

function showUserCreator() {
  closeUserModals();
  const overlay = el("div", "task-editor-overlay");
  overlay.id = "user-creator-overlay";
  const panel = el("div", "task-editor login-card");
  panel.innerHTML = `
    <p class="overline">New user</p>
    <label for="nu-email">Email</label>
    <input id="nu-email" type="email" required />
    <label for="nu-name">Name</label>
    <input id="nu-name" type="text" required />
    <label for="nu-password">Temporary password</label>
    <input id="nu-password" type="password" minlength="8" required />
    <label class="checkbox-row"><input id="nu-admin" type="checkbox" /> Admin</label>
    <div class="task-editor-buttons">
      <button type="button" class="btn" id="nu-save">Create</button>
      <button type="button" class="btn btn-sm secondary" id="nu-cancel">Cancel</button>
    </div>
    <p id="nu-error" class="error hidden"></p>
  `;
  panel.querySelector("#nu-cancel").onclick = closeUserModals;
  panel.querySelector("#nu-save").onclick = async () => {
    const errEl = panel.querySelector("#nu-error");
    errEl.classList.add("hidden");
    const email = panel.querySelector("#nu-email").value.trim();
    const name = panel.querySelector("#nu-name").value.trim();
    const password = panel.querySelector("#nu-password").value;
    if (!email || !name || password.length < 8) {
      errEl.textContent = "Email, name, and password (8+ characters) are required.";
      errEl.classList.remove("hidden");
      return;
    }
    try {
      await api("/api/users", {
        method: "POST",
        body: JSON.stringify({
          email,
          name,
          password,
          is_admin: panel.querySelector("#nu-admin").checked,
        }),
      });
      closeUserModals();
      loadUsers();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove("hidden");
    }
  };
  overlay.appendChild(panel);
  document.body.appendChild(overlay);
  panel.querySelector("#nu-email").focus();
}

function showSetPasswordForm(user) {
  closeUserModals();
  const overlay = el("div", "task-editor-overlay");
  overlay.id = "user-password-overlay";
  const panel = el("div", "task-editor login-card");
  panel.innerHTML = `
    <p class="overline">Set password</p>
    <p class="prompt-task-context mono">${escapeHtml(user.email)}</p>
    <label for="sp-password">Temporary password</label>
    <input id="sp-password" type="password" minlength="8" required />
    <div class="task-editor-buttons">
      <button type="button" class="btn" id="sp-save">Save</button>
      <button type="button" class="btn btn-sm secondary" id="sp-cancel">Cancel</button>
    </div>
    <p id="sp-error" class="error hidden"></p>
  `;
  panel.querySelector("#sp-cancel").onclick = closeUserModals;
  panel.querySelector("#sp-save").onclick = async () => {
    const errEl = panel.querySelector("#sp-error");
    errEl.classList.add("hidden");
    const password = panel.querySelector("#sp-password").value;
    if (password.length < 8) {
      errEl.textContent = "Password must be at least 8 characters.";
      errEl.classList.remove("hidden");
      return;
    }
    try {
      await api(`/api/users/${user.id}`, {
        method: "PATCH",
        body: JSON.stringify({ password }),
      });
      closeUserModals();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove("hidden");
    }
  };
  overlay.appendChild(panel);
  document.body.appendChild(overlay);
  panel.querySelector("#sp-password").focus();
}

function showChangePasswordForm() {
  closeUserModals();
  const overlay = el("div", "task-editor-overlay");
  overlay.id = "change-password-overlay";
  const panel = el("div", "task-editor login-card");
  panel.innerHTML = `
    <p class="overline">Change password</p>
    <label for="cp-current">Current password</label>
    <input id="cp-current" type="password" required />
    <label for="cp-new">New password</label>
    <input id="cp-new" type="password" minlength="8" required />
    <label for="cp-confirm">Confirm new password</label>
    <input id="cp-confirm" type="password" minlength="8" required />
    <div class="task-editor-buttons">
      <button type="button" class="btn" id="cp-save">Save</button>
      <button type="button" class="btn btn-sm secondary" id="cp-cancel">Cancel</button>
    </div>
    <p id="cp-error" class="error hidden"></p>
  `;
  panel.querySelector("#cp-cancel").onclick = closeUserModals;
  panel.querySelector("#cp-save").onclick = async () => {
    const errEl = panel.querySelector("#cp-error");
    errEl.classList.add("hidden");
    const current_password = panel.querySelector("#cp-current").value;
    const new_password = panel.querySelector("#cp-new").value;
    const confirm = panel.querySelector("#cp-confirm").value;
    if (new_password.length < 8) {
      errEl.textContent = "New password must be at least 8 characters.";
      errEl.classList.remove("hidden");
      return;
    }
    if (new_password !== confirm) {
      errEl.textContent = "New password and confirmation do not match.";
      errEl.classList.remove("hidden");
      return;
    }
    try {
      await api("/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password, new_password }),
      });
      closeUserModals();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove("hidden");
    }
  };
  overlay.appendChild(panel);
  document.body.appendChild(overlay);
  panel.querySelector("#cp-current").focus();
}

function closeUserModals() {
  document.getElementById("user-creator-overlay")?.remove();
  document.getElementById("user-password-overlay")?.remove();
  document.getElementById("change-password-overlay")?.remove();
}

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

document.getElementById("login-form").onsubmit = async (e) => {
  e.preventDefault();
  const errEl = document.getElementById("login-error");
  errEl.classList.add("hidden");
  try {
    const data = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email: document.getElementById("email").value,
        password: document.getElementById("password").value,
      }),
    });
    setToken(data.access_token);
    await afterLogin();
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.remove("hidden");
  }
};

const navToggle = document.querySelector(".nav-toggle");
const headerNav = document.getElementById("foundry-nav");

function closeMobileNav() {
  navToggle?.setAttribute("aria-expanded", "false");
  headerNav?.classList.remove("open");
}

navToggle?.addEventListener("click", () => {
  const expanded = navToggle.getAttribute("aria-expanded") === "true";
  navToggle.setAttribute("aria-expanded", String(!expanded));
  headerNav?.classList.toggle("open");
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeMobileNav();
    closeUserMenu();
  }
});

document.getElementById("user-menu-toggle").onclick = (e) => {
  e.stopPropagation();
  toggleUserMenu();
};

document.getElementById("menu-users").onclick = () => {
  closeUserMenu();
  closeMobileNav();
  document.querySelectorAll(".nav-tabs button").forEach((b) => b.classList.remove("active"));
  state.view = "users";
  state.selectedProject = null;
  loadUsers();
};

document.getElementById("menu-change-password").onclick = () => {
  closeUserMenu();
  closeMobileNav();
  showChangePasswordForm();
};

document.getElementById("menu-sign-out").onclick = () => {
  closeUserMenu();
  closeMobileNav();
  closeUserModals();
  setToken(null);
  showLogin();
};

document.addEventListener("click", (e) => {
  const menu = document.getElementById("user-menu");
  if (menu && !menu.contains(e.target)) closeUserMenu();
});

document.getElementById("home-link").onclick = (e) => {
  e.preventDefault();
  closeMobileNav();
  closeUserMenu();
  state.view = "projects";
  state.selectedProject = null;
  document.querySelectorAll(".nav-tabs button").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === "projects");
  });
  loadProjects();
};

document.querySelectorAll(".nav-tabs button").forEach((btn) => {
  btn.onclick = () => {
    closeMobileNav();
    closeUserMenu();
    document.querySelectorAll(".nav-tabs button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.view = btn.dataset.view;
    state.selectedProject = null;
    if (state.view === "agents") loadPrompts();
    else loadProjects();
  };
});

if (token()) {
  afterLogin().catch(() => {
    setToken(null);
    showLogin();
  });
} else {
  showLogin();
}
