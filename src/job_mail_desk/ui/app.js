const state = {
  view: "today",
  payload: { tasks: [], counts: {}, health: {} },
  calendarAnchor: new Date(),
  selectedDate: new Date(),
  compact: false,
};

const cards = document.querySelector("#cards");
const template = document.querySelector("#taskTemplate");
const healthText = document.querySelector("#healthText");
const healthDot = document.querySelector("#healthDot");
const urgentStrip = document.querySelector("#urgentStrip");
const taskDialog = document.querySelector("#taskDialog");
const taskForm = document.querySelector("#taskForm");
const createDialog = document.querySelector("#createDialog");

function apiReady() {
  return window.pywebview && window.pywebview.api;
}

function escapeText(value) {
  return String(value ?? "");
}

function renderHealth() {
  const health = state.payload.health || {};
  if (health.last_error) {
    healthText.textContent = `最近错误：${health.last_error}`;
    healthDot.className = "health-dot error";
    return;
  }
  if (health.last_scan_at) {
    const stamp = new Date(health.last_scan_at).toLocaleString("zh-CN", {
      hour12: false,
    });
    healthText.textContent = `最近扫描 ${stamp}`;
    healthDot.className = "health-dot ok";
    return;
  }
  healthText.textContent = "尚未完成扫描";
  healthDot.className = "health-dot";
}

function renderCapsule() {
  const next = state.payload.tasks.find((task) => task.time) || state.payload.tasks[0];
  document.querySelector("#capsuleTime").textContent = next
    ? next.time_label.replace(/^\d{2}-\d{2}\s/, "")
    : "--:--";
  document.querySelector("#capsuleCompany").textContent = next
    ? next.company
    : "暂无任务";
}

function renderCounts() {
  const counts = state.payload.counts || {};
  document.querySelector("#countToday").textContent = counts.today || 0;
  const anchor = state.calendarAnchor;
  const weekStart = beginningOfWeek(anchor);
  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekEnd.getDate() + 7);
  document.querySelector("#countWeek").textContent = state.payload.tasks.filter(
    (task) => {
      if (!task.time) return false;
      const date = new Date(task.time);
      return date >= weekStart && date < weekEnd;
    },
  ).length;
  document.querySelector("#countMonth").textContent = state.payload.tasks.filter(
    (task) => {
      if (!task.time) return false;
      const date = new Date(task.time);
      return (
        date.getFullYear() === anchor.getFullYear() &&
        date.getMonth() === anchor.getMonth()
      );
    },
  ).length;
  document.querySelector("#countReview").textContent = counts.review || 0;
  document.querySelector("#countResearch").textContent = counts.research || 0;
  const urgent = state.payload.tasks.filter(
    (task) => task.priority === "urgent" && task.status !== "done",
  );
  urgentStrip.classList.toggle("hidden", urgent.length === 0);
  urgentStrip.textContent = urgent.length
    ? `⚠ ${urgent.length} 个 24 小时内硬截止，请先核对官方通知`
    : "";
}

function dateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function tasksOn(date) {
  const key = dateKey(date);
  return state.payload.tasks.filter(
    (task) => task.time && dateKey(new Date(task.time)) === key,
  );
}

function beginningOfWeek(date) {
  const value = new Date(date);
  const day = value.getDay() || 7;
  value.setDate(value.getDate() - day + 1);
  value.setHours(0, 0, 0, 0);
  return value;
}

function calendarToolbar(title, onPrevious, onNext) {
  const toolbar = document.createElement("div");
  toolbar.className = "calendar-toolbar";
  const previous = document.createElement("button");
  previous.textContent = "‹";
  previous.addEventListener("click", onPrevious);
  const heading = document.createElement("strong");
  heading.textContent = title;
  const next = document.createElement("button");
  next.textContent = "›";
  next.addEventListener("click", onNext);
  toolbar.append(previous, heading, next);
  return toolbar;
}

function eventNode(task) {
  const event = document.createElement("div");
  event.className = `calendar-event ${task.priority === "urgent" ? "urgent" : ""}`;
  const time = document.createElement("time");
  time.textContent = new Date(task.time).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const label = document.createElement("span");
  label.textContent = `${task.company} · ${task.stage}`;
  const done = document.createElement("button");
  done.textContent = "✓";
  done.title = "标记完成";
  done.addEventListener("click", () => handleAction(task, "done"));
  event.append(time, label, done);
  return event;
}

function renderWeek() {
  cards.replaceChildren();
  const start = beginningOfWeek(state.calendarAnchor);
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  const title = `${start.getMonth() + 1}月${start.getDate()}日 — ${end.getMonth() + 1}月${end.getDate()}日`;
  cards.append(
    calendarToolbar(
      title,
      () => {
        state.calendarAnchor.setDate(state.calendarAnchor.getDate() - 7);
        render();
      },
      () => {
        state.calendarAnchor.setDate(state.calendarAnchor.getDate() + 7);
        render();
      },
    ),
  );
  const agenda = document.createElement("div");
  agenda.className = "week-agenda";
  const weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
  for (let offset = 0; offset < 7; offset += 1) {
    const date = new Date(start);
    date.setDate(date.getDate() + offset);
    const row = document.createElement("section");
    row.className = `week-day ${dateKey(date) === dateKey(new Date()) ? "today" : ""}`;
    const label = document.createElement("div");
    label.className = "week-date";
    label.innerHTML = `<span>${weekdays[offset]}</span><strong>${date.getDate()}</strong>`;
    const events = document.createElement("div");
    events.className = "week-events";
    const items = tasksOn(date);
    if (items.length) {
      items.forEach((item) => events.append(eventNode(item)));
    } else {
      const empty = document.createElement("span");
      empty.className = "no-events";
      empty.textContent = "无安排";
      events.append(empty);
    }
    row.append(label, events);
    agenda.append(row);
  }
  cards.append(agenda);
}

function renderSelectedDay(container) {
  const section = document.createElement("section");
  section.className = "selected-day";
  const heading = document.createElement("h2");
  heading.textContent = `${state.selectedDate.getMonth() + 1}月${state.selectedDate.getDate()}日安排`;
  section.append(heading);
  const items = tasksOn(state.selectedDate);
  if (items.length) {
    items.forEach((item) => section.append(eventNode(item)));
  } else {
    const empty = document.createElement("span");
    empty.className = "no-events";
    empty.textContent = "这一天没有已确认时间的任务";
    section.append(empty);
  }
  container.append(section);
}

function renderMonth() {
  cards.replaceChildren();
  const anchor = state.calendarAnchor;
  const year = anchor.getFullYear();
  const month = anchor.getMonth();
  cards.append(
    calendarToolbar(
      `${year} 年 ${month + 1} 月`,
      () => {
        state.calendarAnchor = new Date(year, month - 1, 1);
        state.selectedDate = new Date(state.calendarAnchor);
        render();
      },
      () => {
        state.calendarAnchor = new Date(year, month + 1, 1);
        state.selectedDate = new Date(state.calendarAnchor);
        render();
      },
    ),
  );
  const weekdays = document.createElement("div");
  weekdays.className = "month-weekdays";
  ["一", "二", "三", "四", "五", "六", "日"].forEach((day) => {
    const label = document.createElement("span");
    label.textContent = day;
    weekdays.append(label);
  });
  cards.append(weekdays);
  const grid = document.createElement("div");
  grid.className = "month-grid";
  const first = beginningOfWeek(new Date(year, month, 1));
  for (let offset = 0; offset < 42; offset += 1) {
    const date = new Date(first);
    date.setDate(date.getDate() + offset);
    const cell = document.createElement("button");
    const items = tasksOn(date);
    cell.className = [
      "month-cell",
      date.getMonth() !== month ? "outside" : "",
      dateKey(date) === dateKey(new Date()) ? "today" : "",
      dateKey(date) === dateKey(state.selectedDate) ? "selected" : "",
    ].join(" ");
    cell.textContent = date.getDate();
    const dots = document.createElement("div");
    dots.className = "event-dots";
    items.slice(0, 5).forEach((item) => {
      const dot = document.createElement("i");
      dot.className = `event-dot ${item.priority === "urgent" ? "urgent" : ""}`;
      dots.append(dot);
    });
    cell.append(dots);
    cell.addEventListener("click", () => {
      state.selectedDate = date;
      renderMonth();
    });
    grid.append(cell);
  }
  cards.append(grid);
  renderSelectedDay(cards);
}

async function handleAction(task, action) {
  if (!apiReady()) return;
  if (action === "done") {
    state.payload = await window.pywebview.api.update_status(task.id, "done");
  } else if (action === "confirm") {
    state.payload = await window.pywebview.api.update_status(task.id, "confirmed");
  } else if (action === "ignore") {
    state.payload = await window.pywebview.api.update_status(task.id, "irrelevant");
  } else if (action === "source") {
    await window.pywebview.api.open_source(task.id);
  } else if (action === "obsidian") {
    await window.pywebview.api.open_obsidian(task.id);
  } else if (action === "edit") {
    showTaskDialog(task);
    return;
  } else if (action === "snooze") {
    const until = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
    state.payload = await window.pywebview.api.snooze(task.id, until);
  }
  render();
}

function renderCards() {
  cards.replaceChildren();
  if (state.view === "week") {
    renderWeek();
    return;
  }
  if (state.view === "month") {
    renderMonth();
    return;
  }
  const tasks = state.payload.tasks.filter((task) =>
    state.view === "research"
      ? !["not_queued", "completed"].includes(task.research_status)
      : task.view === state.view,
  );
  if (!tasks.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "这一栏暂时没有任务。";
    cards.append(empty);
    return;
  }
  for (const task of tasks) {
    const node = template.content.firstElementChild.cloneNode(true);
    node.dataset.priority = task.priority;
    node.querySelector(".company").textContent = escapeText(task.company);
    node.querySelector(".role").textContent = escapeText(task.role);
    node.querySelector(".time-label").textContent = escapeText(task.time_label);
    node.querySelector(".remaining").textContent = escapeText(task.remaining);
    node.querySelector(".stage").textContent = escapeText(task.stage);
    const round = node.querySelector(".round");
    round.textContent = escapeText(task.round);
    round.hidden = !task.round;
    const research = node.querySelector(".research");
    research.textContent = `研究：${escapeText(task.research_status)}`;
    node.querySelector(".action").textContent = escapeText(task.action);
    node.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", () =>
        handleAction(task, button.dataset.action),
      );
    });
    cards.append(node);
  }
}

function render() {
  renderCounts();
  renderCards();
  renderHealth();
  renderCapsule();
}

function inputDate(value) {
  return value ? value.slice(0, 16) : "";
}

function showTaskDialog(task = null) {
  taskForm.reset();
  document.querySelector("#formError").textContent = "";
  document.querySelector("#dialogTitle").textContent = task
    ? "编辑求职任务"
    : "新建求职任务";
  taskForm.elements.task_id.value = task?.id || "";
  taskForm.elements.company.value = task?.company || "";
  taskForm.elements.role.value =
    task?.role === "岗位待确认" ? "" : task?.role || "";
  taskForm.elements.stage.value = task?.stage || "自定义待办";
  taskForm.elements.round.value = task?.round || "";
  taskForm.elements.start_at.value = inputDate(task?.start_at);
  taskForm.elements.end_at.value = inputDate(task?.end_at);
  taskForm.elements.deadline_at.value = inputDate(task?.deadline_at);
  taskForm.elements.action_summary.value = task?.action || "";
  taskForm.elements.manual_notes.value = task?.manual_notes || "";
  taskDialog.showModal();
}

function formPayload() {
  return Object.fromEntries(
    [
      "company",
      "role",
      "stage",
      "round",
      "start_at",
      "end_at",
      "deadline_at",
      "action_summary",
      "manual_notes",
    ].map((name) => [name, taskForm.elements[name].value.trim()]),
  );
}

async function saveTask(event) {
  event.preventDefault();
  if (!apiReady()) return;
  const taskId = taskForm.elements.task_id.value;
  try {
    state.payload = taskId
      ? await window.pywebview.api.edit_task(taskId, formPayload())
      : await window.pywebview.api.create_task(formPayload());
    taskDialog.close();
    render();
  } catch (error) {
    document.querySelector("#formError").textContent =
      error?.message || String(error);
  }
}

async function setCapsule(compact) {
  if (!apiReady()) return;
  state.compact = compact;
  document.body.classList.toggle("capsule", compact);
  await window.pywebview.api.set_capsule(compact);
}

async function refresh() {
  if (!apiReady()) return;
  state.payload = await window.pywebview.api.get_dashboard();
  render();
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelector(".tab.active").classList.remove("active");
    tab.classList.add("active");
    state.view = tab.dataset.view;
    renderCards();
  });
});

document.querySelector("#refreshButton").addEventListener("click", refresh);
document.querySelector("#addButton").addEventListener("click", () => createDialog.showModal());
document.querySelector("#closeCreateDialog").addEventListener("click", () => createDialog.close());
document.querySelectorAll("[data-create]").forEach((button) => {
  button.addEventListener("click", async () => {
    const kind = button.dataset.create;
    createDialog.close();
    if (kind === "job") {
      showTaskDialog();
    } else if (apiReady()) {
      await window.pywebview.api.create_paper(kind);
    }
  });
});
document.querySelector("#capsuleButton").addEventListener("click", () => setCapsule(true));
document.querySelector("#expandButton").addEventListener("click", () => setCapsule(false));
document.querySelector("#capsuleView").addEventListener("mouseenter", () =>
  window.pywebview.api.peek_capsule(true),
);
document.querySelector("#capsuleView").addEventListener("mouseleave", () =>
  window.pywebview.api.peek_capsule(false),
);
document.querySelector("#closeDialog").addEventListener("click", () => taskDialog.close());
document.querySelector("#cancelDialog").addEventListener("click", () => taskDialog.close());
taskForm.addEventListener("submit", saveTask);
document.querySelector("#scanButton").addEventListener("click", async () => {
  const button = document.querySelector("#scanButton");
  if (!apiReady() || button.disabled) return;
  button.disabled = true;
  button.textContent = "…";
  try {
    await window.pywebview.api.trigger_scan();
    await refresh();
  } finally {
    button.disabled = false;
    button.textContent = "↻";
  }
});

window.addEventListener("pywebviewready", refresh);
setTimeout(refresh, 800);
setInterval(refresh, 60_000);
