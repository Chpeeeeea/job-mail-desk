const paperState = {
  paper: null,
  todos: [],
  history: [],
  future: [],
  zoom: 100,
  markdownLevel: "balanced",
  saveTimer: null,
  draggedIndex: null,
  loaded: false,
  loadAttempts: 0,
};

const byId = (id) => document.getElementById(id);
const paperId = new URLSearchParams(location.hash.slice(1)).get("paper");

function apiReady() {
  return window.pywebview && window.pywebview.api;
}

function uid() {
  return crypto.randomUUID().replaceAll("-", "").slice(0, 12);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function applyPreferences(preferences) {
  const font = {
    system: '"Segoe UI", sans-serif',
    yahei: '"Microsoft YaHei UI", sans-serif',
    deng: 'DengXian, "Segoe UI", sans-serif',
  }[preferences.font_family] || '"Segoe UI", sans-serif';
  document.documentElement.style.setProperty("--font", font);
  document.documentElement.style.setProperty(
    "--scale",
    String((preferences.scale || 100) / 100),
  );
  byId("fontSelect").value = preferences.font_family || "system";
  byId("scaleInput").value = preferences.scale || 100;
  byId("scaleOutput").textContent = `${preferences.scale || 100}%`;
  byId("autoClear").checked = Boolean(preferences.auto_clear_completed);
  byId("autoSnap").checked = preferences.auto_snap_capsules !== false;
  paperState.markdownLevel = preferences.markdown_level || "balanced";
}

function parseTodoBody(body) {
  return body
    .split(/\r?\n/)
    .map((line) => {
      const match = line.match(
        /^-\s+\[([ xX])\]\s*(.*?)\s*(?:<!--\s*item:([a-z0-9]+)\s*-->)?\s*(?:<!--\s*note:([a-z0-9]+)\s*-->)?\s*$/,
      );
      if (!match) return null;
      return {
        id: match[3] || uid(),
        text: match[2].trim(),
        done: match[1].toLowerCase() === "x",
        noteId: match[4] || null,
      };
    })
    .filter(Boolean);
}

function serializeTodos() {
  return paperState.todos
    .map((item) => {
      const note = item.noteId ? ` <!-- note:${item.noteId} -->` : "";
      return `- [${item.done ? "x" : " "}] ${item.text} <!-- item:${item.id} -->${note}`;
    })
    .join("\n");
}

function snapshot() {
  paperState.history.push(JSON.stringify(paperState.todos));
  if (paperState.history.length > 50) paperState.history.shift();
  paperState.future = [];
}

function autosize(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(90, textarea.scrollHeight)}px`;
}

function linkedNote(item) {
  return (paperState.paper.notes || []).find((note) => note.id === item.noteId);
}

function chooseNote(item) {
  const notes = paperState.paper.notes || [];
  if (!notes.length) {
    if (confirm("还没有笔记纸。现在创建一张吗？")) {
      window.pywebview.api.create_paper("note");
    }
    return;
  }
  const choices = notes.map((note, index) => `${index + 1}. ${note.title}`).join("\n");
  const answer = prompt(`输入要关联的笔记序号；输入 0 取消关联：\n${choices}`);
  if (answer === null) return;
  const index = Number(answer) - 1;
  snapshot();
  item.noteId = Number(answer) === 0 ? null : notes[index]?.id || item.noteId;
  renderTodos();
  scheduleSave();
}

function renderTodos() {
  const list = byId("todoList");
  list.replaceChildren();
  for (const [index, item] of paperState.todos.entries()) {
    const row = byId("todoTemplate").content.firstElementChild.cloneNode(true);
    row.dataset.index = String(index);
    row.classList.toggle("done", item.done);
    const check = row.querySelector(".todo-check");
    const text = row.querySelector(".todo-text");
    const note = row.querySelector(".todo-note");
    check.checked = item.done;
    text.value = item.text;
    autosize(text);
    check.addEventListener("change", () => {
      snapshot();
      item.done = check.checked;
      if (byId("autoClear").checked && item.done) {
        setTimeout(() => {
          paperState.todos = paperState.todos.filter((entry) => !entry.done);
          renderTodos();
          scheduleSave();
        }, 280);
      } else {
        renderTodos();
        scheduleSave();
      }
    });
    text.addEventListener("input", () => {
      item.text = text.value;
      autosize(text);
      scheduleSave();
    });
    text.addEventListener("dblclick", () => text.select());
    note.classList.toggle("linked", Boolean(item.noteId));
    note.title = linkedNote(item)?.title || "关联笔记";
    note.addEventListener("click", () => {
      if (item.noteId && confirm(`打开关联笔记“${linkedNote(item)?.title || "笔记"}”？`)) {
        window.pywebview.api.open_paper(item.noteId);
      } else {
        chooseNote(item);
      }
    });
    row.querySelector(".todo-delete").addEventListener("click", () => {
      snapshot();
      paperState.todos.splice(index, 1);
      renderTodos();
      scheduleSave();
    });
    const handle = row.querySelector(".todo-handle");
    handle.addEventListener("dragstart", (event) => {
      paperState.draggedIndex = index;
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", item.id);
      row.classList.add("dragging");
    });
    handle.addEventListener("dragend", () => {
      paperState.draggedIndex = null;
      row.classList.remove("dragging");
    });
    row.addEventListener("dragover", (event) => event.preventDefault());
    row.addEventListener("drop", (event) => {
      event.preventDefault();
      let linkedNoteId = event.dataTransfer.getData(
        "application/x-jobmaildesk-note",
      );
      const plainTransfer = event.dataTransfer.getData("text/plain");
      if (!linkedNoteId && plainTransfer.startsWith("jobmaildesk-note:")) {
        linkedNoteId = plainTransfer.slice("jobmaildesk-note:".length);
      }
      if (linkedNoteId) {
        snapshot();
        item.noteId = linkedNoteId;
        renderTodos();
        scheduleSave();
        return;
      }
      const from = paperState.draggedIndex;
      if (from === null || from === index) return;
      snapshot();
      const [moved] = paperState.todos.splice(from, 1);
      paperState.todos.splice(index, 0, moved);
      paperState.draggedIndex = null;
      renderTodos();
      scheduleSave();
    });
    list.append(row);
  }
  const remaining = paperState.todos.filter((item) => !item.done).length;
  byId("todoCount").textContent = `${remaining} 项未完成`;
  byId("capsuleBadge").textContent = String(remaining);
}

function addTodoLines(value) {
  const lines = value
    .split(/\r?\n/)
    .map((line) => line.replace(/^\s*(?:[-*+]|\d+[.)])\s*/, "").trim())
    .filter(Boolean);
  if (!lines.length) return;
  snapshot();
  paperState.todos.push(
    ...lines.map((text) => ({ id: uid(), text, done: false, noteId: null })),
  );
  renderTodos();
  scheduleSave();
}

function simpleMarkdown(source) {
  let html = escapeHtml(source);
  html = html.replace(/^######\s+(.+)$/gm, "<h6>$1</h6>");
  html = html.replace(/^#####\s+(.+)$/gm, "<h5>$1</h5>");
  html = html.replace(/^####\s+(.+)$/gm, "<h4>$1</h4>");
  html = html.replace(/^###\s+(.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^##\s+(.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^#\s+(.+)$/gm, "<h1>$1</h1>");
  html = html.replace(/^&gt;\s+(.+)$/gm, "<blockquote>$1</blockquote>");
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/~~(.+?)~~/g, "<del>$1</del>");
  html = html.replace(/(?<!\*)\*([^*\n]+)\*/g, "<em>$1</em>");
  html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  html = html.replace(
    /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,
    '<a href="$2">$1</a>',
  );
  html = html.replace(/^[-*_]{3,}$/gm, "<hr>");
  html = html.replace(/^(?:-\s+)(.+)$/gm, "<li>$1</li>");
  html = html.replace(/\n/g, "<br>");
  return html;
}

async function renderNote() {
  const preview = byId("notePreview");
  const source = byId("noteEditor").value;
  let html = simpleMarkdown(source);
  const references = [...source.matchAll(/^i:([^\s]+)$/gm)].map(
    (match) => `i:${match[1]}`,
  );
  for (const reference of references) {
    const data = await window.pywebview.api.get_note_image(reference);
    if (data) {
      html = html.replace(
        escapeHtml(reference),
        `<img src="${data}" alt="本地图片">`,
      );
    }
  }
  preview.innerHTML = html;
}

function setMarkdownLevel(level) {
  paperState.markdownLevel = level;
  document.body.dataset.markdownLevel = level;
  document.querySelectorAll(".level").forEach((button) => {
    button.classList.toggle("active", button.dataset.level === level);
  });
  const showPreview = level === "rich";
  byId("noteEditor").classList.toggle("hidden", showPreview);
  byId("notePreview").classList.toggle("hidden", !showPreview);
  if (showPreview) renderNote();
  window.pywebview.api.save_preferences({ markdown_level: level });
}

function wrapSelection(prefix, suffix = prefix) {
  const editor = byId("noteEditor");
  const start = editor.selectionStart;
  const end = editor.selectionEnd;
  const selected = editor.value.slice(start, end);
  editor.setRangeText(`${prefix}${selected}${suffix}`, start, end, "select");
  editor.focus();
  scheduleSave();
}

function formatNote(kind) {
  if (kind === "bold") wrapSelection("**");
  if (kind === "italic") wrapSelection("*");
  if (kind === "link") wrapSelection("[", "](https://)");
}

async function insertImageFile(file) {
  if (!file?.type.startsWith("image/")) return;
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
  const reference = await window.pywebview.api.save_note_image(dataUrl);
  const editor = byId("noteEditor");
  editor.setRangeText(`\n${reference}\n`, editor.selectionStart, editor.selectionEnd, "end");
  scheduleSave();
}

function currentBody() {
  return paperState.paper.kind === "todo"
    ? serializeTodos()
    : byId("noteEditor").value;
}

async function savePaper() {
  clearTimeout(paperState.saveTimer);
  byId("saveState").textContent = "保存中…";
  const updated = await window.pywebview.api.save_paper(paperId, {
    body: currentBody(),
    title: byId("paperTitle").value,
    theme: byId("themeSelect").value,
    linked_task_ids: paperState.paper.linked_task_ids || [],
  });
  paperState.paper = { ...paperState.paper, ...updated };
  byId("saveState").textContent = "已保存";
}

function scheduleSave() {
  byId("saveState").textContent = "待保存";
  clearTimeout(paperState.saveTimer);
  paperState.saveTimer = setTimeout(savePaper, 380);
}

async function loadPaper() {
  if (paperState.loaded) return;
  if (!apiReady()) {
    paperState.loadAttempts += 1;
    if (paperState.loadAttempts < 40) {
      setTimeout(loadPaper, 250);
    } else {
      byId("loadError").textContent = "纸片接口启动超时，请关闭后重新打开。";
      byId("loadError").classList.remove("hidden");
    }
    return;
  }
  try {
    paperState.paper = await window.pywebview.api.get_paper(paperId);
  } catch (error) {
    paperState.loadAttempts += 1;
    if (paperState.loadAttempts < 12) {
      setTimeout(loadPaper, 350);
      return;
    }
    byId("loadError").textContent = `纸片读取失败：${error}`;
    byId("loadError").classList.remove("hidden");
    return;
  }
  paperState.loaded = true;
  const paper = paperState.paper;
  byId("paperTitle").value = paper.title;
  byId("themeSelect").value = paper.theme;
  document.body.dataset.theme = paper.theme;
  applyPreferences(paper.preferences);
  byId("kindMark").textContent = paper.kind === "todo" ? "✓" : "M";
  byId("capsuleKind").textContent = paper.kind === "todo" ? "✓" : "M";
  if (paper.kind === "todo") {
    byId("todoPaper").classList.remove("hidden");
    paperState.todos = parseTodoBody(paper.body);
    renderTodos();
  } else {
    byId("notePaper").classList.remove("hidden");
    byId("noteEditor").value = paper.body;
    byId("capsuleBadge").textContent = "M";
    byId("kindMark").draggable = true;
    byId("kindMark").title = "拖到待办项上建立关联";
    byId("kindMark").addEventListener("dragstart", (event) => {
      event.dataTransfer.effectAllowed = "link";
      event.dataTransfer.setData(
        "application/x-jobmaildesk-note",
        paper.id,
      );
      event.dataTransfer.setData("text/plain", `jobmaildesk-note:${paper.id}`);
    });
    setMarkdownLevel(paper.preferences.markdown_level || "balanced");
  }
}

byId("addTodo").addEventListener("click", () => {
  addTodoLines(byId("todoInput").value);
  byId("todoInput").value = "";
});
byId("todoInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    byId("addTodo").click();
  }
});
byId("clearCompleted").addEventListener("click", () => {
  if (!paperState.todos.some((item) => item.done)) return;
  snapshot();
  paperState.todos = paperState.todos.filter((item) => !item.done);
  renderTodos();
  scheduleSave();
});
byId("undoButton").addEventListener("click", () => {
  const previous = paperState.history.pop();
  if (!previous) return;
  paperState.future.push(JSON.stringify(paperState.todos));
  paperState.todos = JSON.parse(previous);
  renderTodos();
  scheduleSave();
});
byId("redoButton").addEventListener("click", () => {
  const next = paperState.future.pop();
  if (!next) return;
  paperState.history.push(JSON.stringify(paperState.todos));
  paperState.todos = JSON.parse(next);
  renderTodos();
  scheduleSave();
});

byId("noteEditor").addEventListener("input", scheduleSave);
byId("noteEditor").addEventListener("keydown", (event) => {
  if (!event.ctrlKey) return;
  const key = event.key.toLowerCase();
  if (["b", "i", "k"].includes(key)) {
    event.preventDefault();
    formatNote({ b: "bold", i: "italic", k: "link" }[key]);
  }
});
byId("noteEditor").addEventListener("paste", async (event) => {
  const image = [...event.clipboardData.items].find((item) =>
    item.type.startsWith("image/"),
  );
  if (image) {
    event.preventDefault();
    await insertImageFile(image.getAsFile());
  }
});
document.querySelectorAll("[data-format]").forEach((button) =>
  button.addEventListener("click", () => formatNote(button.dataset.format)),
);
document.querySelectorAll("[data-level]").forEach((button) =>
  button.addEventListener("click", () => setMarkdownLevel(button.dataset.level)),
);
byId("insertImage").addEventListener("click", () => byId("imagePicker").click());
byId("imagePicker").addEventListener("change", () =>
  insertImageFile(byId("imagePicker").files[0]),
);

function setZoom(value) {
  paperState.zoom = Math.max(70, Math.min(160, value));
  byId("noteEditor").style.fontSize = `${paperState.zoom}%`;
  byId("notePreview").style.fontSize = `${paperState.zoom}%`;
  byId("zoomReset").textContent = `${paperState.zoom}%`;
}
byId("zoomOut").addEventListener("click", () => setZoom(paperState.zoom - 10));
byId("zoomIn").addEventListener("click", () => setZoom(paperState.zoom + 10));
byId("zoomReset").addEventListener("click", () => setZoom(100));
byId("noteEditor").addEventListener("wheel", (event) => {
  if (!event.ctrlKey) return;
  event.preventDefault();
  setZoom(paperState.zoom + (event.deltaY < 0 ? 10 : -10));
});

byId("paperTitle").addEventListener("input", scheduleSave);
byId("themeSelect").addEventListener("change", () => {
  document.body.dataset.theme = byId("themeSelect").value;
  scheduleSave();
});
byId("fontSelect").addEventListener("change", async () => {
  const prefs = await window.pywebview.api.save_preferences({
    font_family: byId("fontSelect").value,
  });
  applyPreferences(prefs);
});
byId("scaleInput").addEventListener("input", async () => {
  byId("scaleOutput").textContent = `${byId("scaleInput").value}%`;
  const prefs = await window.pywebview.api.save_preferences({
    scale: Number(byId("scaleInput").value),
  });
  applyPreferences(prefs);
});
byId("autoClear").addEventListener("change", () =>
  window.pywebview.api.save_preferences({
    auto_clear_completed: byId("autoClear").checked,
  }),
);
byId("autoSnap").addEventListener("change", () =>
  window.pywebview.api.save_preferences({
    auto_snap_capsules: byId("autoSnap").checked,
  }),
);

byId("settingsButton").addEventListener("click", () =>
  byId("settingsPanel").classList.toggle("hidden"),
);
byId("closeSettings").addEventListener("click", () =>
  byId("settingsPanel").classList.add("hidden"),
);
byId("collapseButton").addEventListener("click", async () => {
  document.body.classList.add("capsule");
  await window.pywebview.api.set_paper_capsule(paperId, true);
});
byId("expandCapsule").addEventListener("click", async () => {
  document.body.classList.remove("capsule");
  await window.pywebview.api.set_paper_capsule(paperId, false);
});
byId("capsule").addEventListener("mouseenter", () =>
  window.pywebview.api.peek_paper_capsule(paperId, true),
);
byId("capsule").addEventListener("mouseleave", () =>
  window.pywebview.api.peek_paper_capsule(paperId, false),
);
byId("externalButton").addEventListener("click", () =>
  window.pywebview.api.open_paper_external(paperId),
);
byId("closeButton").addEventListener("click", () =>
  window.pywebview.api.close_paper(paperId),
);
byId("newPaper").addEventListener("click", () => byId("newDialog").showModal());
byId("cancelNew").addEventListener("click", () => byId("newDialog").close());
document.querySelectorAll("[data-new-kind]").forEach((button) =>
  button.addEventListener("click", async () => {
    byId("newDialog").close();
    await window.pywebview.api.create_paper(button.dataset.newKind);
  }),
);
byId("trashButton").addEventListener("click", async () => {
  if (confirm("把这张纸片移到本地回收区？可以从 trash 目录恢复。")) {
    await window.pywebview.api.move_paper_to_trash(paperId);
  }
});

window.addEventListener("pywebviewready", loadPaper);
setTimeout(loadPaper, 700);
