const state = {
  view: "today",
  payload: { tasks: [], counts: {}, health: {} },
  calendarAnchor: new Date(),
  selectedDate: new Date(),
  compact: false,
  calendarInitialized: false,
  saving: false,
  expandedCompanies: new Set(),
  setupInitialized: false,
  settingsFirstRun: false,
};

const cards = document.querySelector("#cards");
const template = document.querySelector("#taskTemplate");
const healthText = document.querySelector("#healthText");
const healthDot = document.querySelector("#healthDot");
const urgentStrip = document.querySelector("#urgentStrip");
const taskDialog = document.querySelector("#taskDialog");
const taskForm = document.querySelector("#taskForm");
const settingsDialog = document.querySelector("#settingsDialog");
const settingsForm = document.querySelector("#settingsForm");
let updatePollTimer = null;

function apiReady() {
  return window.pywebview && window.pywebview.api;
}

function escapeText(value) {
  return String(value ?? "");
}

function escapeHtml(value) {
  return escapeText(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

const researchLabels = {
  not_queued: "",
  queued: "备战：待整理",
  running: "备战：整理中",
  completed: "备战：已就绪",
  blocked: "备战：需处理",
  closed: "",
};

const confirmationTimers = new WeakMap();
const guardedActions = new Set(["toggle_done", "snooze", "ignore"]);

function requestAction(button, task, action) {
  if (!guardedActions.has(action)) {
    handleAction(task, action);
    return;
  }
  if (button.dataset.armed === action) {
    clearTimeout(confirmationTimers.get(button));
    confirmationTimers.delete(button);
    button.disabled = true;
    handleAction(task, action);
    return;
  }
  const originalLabel = button.textContent;
  button.dataset.armed = action;
  button.classList.add("confirming");
  button.textContent = "再点确认";
  button.title = "3 秒内再次点击才会执行";
  const timer = setTimeout(() => {
    delete button.dataset.armed;
    button.classList.remove("confirming");
    button.textContent = originalLabel;
  }, 3000);
  confirmationTimers.set(button, timer);
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
  const urgent = state.payload.tasks.filter((task) => task.priority === "urgent");
  const count = urgent.length || state.payload.tasks.length;
  document.querySelector("#capsuleCount").textContent = String(Math.min(count, 9));
  document.querySelector("#capsuleCount").classList.toggle("urgent", urgent.length > 0);
}

function renderCounts() {
  const counts = state.payload.counts || {};
  document.querySelector("#countToday").textContent = counts.today || 0;
  document.querySelector("#countProgress").textContent = counts.progress || 0;
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
  document.querySelector("#countList").textContent = counts.list || 0;
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
  event.className = [
    "calendar-event",
    task.priority === "urgent" ? "urgent" : "",
    task.status === "done" ? "done" : "",
  ].join(" ");
  const time = document.createElement("time");
  time.textContent = new Date(task.time).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const label = document.createElement("span");
  label.textContent = `${task.company} · ${task.stage}`;
  const done = document.createElement("button");
  done.textContent = task.status === "done" ? "↶" : "✓";
  done.title = task.status === "done" ? "恢复为待办" : "标记完成";
  done.addEventListener("click", (eventObject) => {
    eventObject.stopPropagation();
    requestAction(done, task, "toggle_done");
  });
  event.addEventListener("click", () => showTaskDialog(task));
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
  if (action === "toggle_done") {
    const restored = task.time ? "planned" : "needs_review";
    const status = task.status === "done" ? restored : "done";
    state.payload = await window.pywebview.api.update_status(task.id, status);
  } else if (action === "ignore") {
    state.payload = await window.pywebview.api.update_status(task.id, "irrelevant");
  } else if (action === "source") {
    await window.pywebview.api.open_source(task.id);
  } else if (action === "obsidian") {
    await window.pywebview.api.open_obsidian(task.id);
  } else if (action === "research") {
    await window.pywebview.api.open_research(task.id);
  } else if (action === "edit" || action === "edit_time") {
    showTaskDialog(task, action === "edit_time");
    return;
  } else if (action === "snooze") {
    const until = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
    state.payload = await window.pywebview.api.snooze(task.id, until);
  }
  render();
}

function renderCards() {
  cards.replaceChildren();
  if (state.view === "progress") {
    renderProgress();
    return;
  }
  if (state.view === "week") {
    renderWeek();
    return;
  }
  if (state.view === "month") {
    renderMonth();
    return;
  }
  const tasks = state.view === "list"
    ? state.payload.tasks.filter((task) => task.actionable)
    : state.payload.tasks.filter((task) => task.view === state.view);
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
    node.classList.toggle("done", task.status === "done");
    node.title = "点击卡片查看和修改详情";
    node.querySelector(".company").textContent = escapeText(task.company);
    node.querySelector(".role").textContent = escapeText(task.role);
    node.querySelector(".time-label").textContent = escapeText(task.time_label);
    node.querySelector(".remaining").textContent = escapeText(task.remaining);
    node.querySelector(".stage").textContent = escapeText(task.stage);
    const round = node.querySelector(".round");
    round.textContent = escapeText(task.round);
    round.hidden = !task.round;
    const research = node.querySelector(".research");
    research.textContent = researchLabels[task.research_status] || "";
    research.hidden = !research.textContent;
    research.title = "根据公司、岗位和阶段整理公开流程、题型与准备建议；不会再次读取或公开邮件正文。";
    const researchButton = node.querySelector(".research-open");
    researchButton.hidden = !task.research_result_path;
    const snoozed = node.querySelector(".snoozed");
    const snoozedUntil = task.snoozed_until
      ? new Date(task.snoozed_until)
      : null;
    snoozed.hidden = !snoozedUntil || snoozedUntil <= new Date();
    snoozed.textContent = snoozed.hidden
      ? ""
      : `已延后至 ${snoozedUntil.toLocaleString("zh-CN", {
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        })}`;
    node.querySelector(".action").textContent = escapeText(task.action);
    const doneButton = node.querySelector('[data-action="toggle_done"]');
    doneButton.textContent = task.status === "done" ? "恢复" : "完成";
    doneButton.title = task.status === "done"
      ? "首次点击准备恢复，再点一次执行"
      : "首次点击准备完成，再点一次执行";
    const timeButton = node.querySelector('[data-action="edit_time"]');
    timeButton.hidden = Boolean(task.time);
    timeButton.title = "打开详情并补充开始、结束或截止时间";
    const snoozeButton = node.querySelector('[data-action="snooze"]');
    snoozeButton.title = "两次点击后暂时移出提醒区 24 小时；不会修改活动时间";
    const sourceButton = node.querySelector('[data-action="source"]');
    sourceButton.hidden = !task.has_source;
    sourceButton.title = "打开邮件中提取到的通知或操作链接；不是打开邮箱原文";
    const ignoreButton = node.querySelector('[data-action="ignore"]');
    ignoreButton.title = "两次点击后永久忽略此本地任务；不会修改邮件";
    node.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", (eventObject) => {
        eventObject.stopPropagation();
        requestAction(button, task, button.dataset.action);
      });
    });
    node.addEventListener("click", () => showTaskDialog(task));
    cards.append(node);
  }
}

function renderProgress() {
  cards.replaceChildren();
  const applications = state.payload.progress || [];
  if (!applications.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "暂时没有可汇总的求职流程。";
    cards.append(empty);
    return;
  }
  const companies = new Map();
  applications.forEach((application) => {
    const group = companies.get(application.company) || [];
    group.push(application);
    companies.set(application.company, group);
  });

  const overview = document.createElement("div");
  overview.className = "progress-overview";
  const activeCount = applications.filter((application) => application.active).length;
  const overviewText = document.createElement("span");
  overviewText.textContent = `${companies.size} 家企业 · ${activeCount} 条申请进行中`;
  const toggleAll = document.createElement("button");
  const allExpanded = [...companies.keys()].every((company) =>
    state.expandedCompanies.has(company),
  );
  toggleAll.textContent = allExpanded ? "收起全部" : "展开全部";
  toggleAll.addEventListener("click", () => {
    state.expandedCompanies = allExpanded
      ? new Set()
      : new Set(companies.keys());
    renderProgress();
  });
  overview.append(overviewText, toggleAll);
  cards.append(overview);

  companies.forEach((items, company) => {
    const group = document.createElement("details");
    group.className = "progress-company";
    group.open = state.expandedCompanies.has(company);
    group.addEventListener("toggle", () => {
      if (group.open) state.expandedCompanies.add(company);
      else state.expandedCompanies.delete(company);
    });

    const activeItems = items.filter((application) => application.active);
    const lead = activeItems[0] || items[0];
    const stages = [...new Set(items.map((application) => {
      const round = application.current_round
        ? ` · ${application.current_round}`
        : "";
      return `${application.current_stage}${round}`;
    }))].slice(0, 2);
    const summary = document.createElement("summary");
    summary.className = "progress-company-summary";
    summary.title = `${company}｜${stages.join("；")}`;
    summary.innerHTML = `
      <span class="progress-chevron" aria-hidden="true"></span>
      <span class="progress-company-identity">
        <strong>${escapeHtml(company)}</strong>
        <small>${items.length} 条申请链 · ${escapeHtml(stages.join("；"))}</small>
      </span>
      <span class="progress-company-state ${activeItems.length ? "active" : "closed"}">
        ${activeItems.length ? `${activeItems.length} 进行中` : escapeHtml(lead.status_label)}
      </span>
    `;
    const body = document.createElement("div");
    body.className = "progress-company-body";
    items.forEach((application) => {
      const card = document.createElement("article");
      card.className = `progress-card ${application.active ? "active" : "closed"}`;
      const currentRound = application.current_round
        ? ` · ${application.current_round}`
        : "";
      const project = application.project ? ` · ${application.project}` : "";
      card.innerHTML = `
        <div class="progress-head">
          <div><strong>${escapeHtml(application.role)}</strong><small>${escapeHtml(project)}</small></div>
          <span>${escapeHtml(application.status_label)}</span>
        </div>
        <div class="progress-current">当前：${escapeHtml(application.current_stage)}${escapeHtml(currentRound)}</div>
        <div class="progress-timeline"></div>
      `;
      const timeline = card.querySelector(".progress-timeline");
      application.history.slice(0, 6).forEach((event) => {
        const row = document.createElement("button");
        row.type = "button";
        row.className = `progress-event ${event.status}`;
        const time = event.time
          ? new Date(event.time).toLocaleString("zh-CN", {
              month: "2-digit",
              day: "2-digit",
              hour: "2-digit",
              minute: "2-digit",
              hour12: false,
            })
          : "时间待确认";
        row.innerHTML = `<time>${escapeHtml(time)}</time><span>${escapeHtml(event.stage)}${event.round ? ` · ${escapeHtml(event.round)}` : ""}</span><em>${escapeHtml(event.status_label)}</em>`;
        const sourceTask = state.payload.tasks.find((task) => task.id === event.task_id);
        if (sourceTask) {
          row.title = "打开该节点详情";
          row.addEventListener("click", () => showTaskDialog(sourceTask));
        } else {
          row.disabled = true;
        }
        timeline.append(row);
      });
      body.append(card);
    });
    group.append(summary, body);
    cards.append(group);
  });
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

async function showTaskDialog(task = null, focusTime = false) {
  if (apiReady()) await window.pywebview.api.set_editor_mode(true);
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
  if (focusTime) taskForm.elements.start_at.focus();
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
  if (!apiReady() || state.saving) return;
  const taskId = taskForm.elements.task_id.value;
  const submitButton = taskForm.querySelector("button[type='submit']");
  state.saving = true;
  submitButton.disabled = true;
  try {
    state.payload = taskId
      ? await window.pywebview.api.edit_task(taskId, formPayload())
      : await window.pywebview.api.create_task(formPayload());
    taskDialog.close();
    state.calendarInitialized = false;
    initializeCalendarAnchor();
    render();
  } catch (error) {
    document.querySelector("#formError").textContent =
      error?.message || String(error);
  } finally {
    state.saving = false;
    submitButton.disabled = false;
  }
}

async function showSettingsDialog(firstRun = false, payload = null) {
  if (!apiReady()) return;
  await window.pywebview.api.set_editor_mode(true);
  const settings = payload || await window.pywebview.api.get_app_settings();
  state.settingsFirstRun = firstRun || !settings.credential_configured;
  document.querySelector("#settingsTitle").textContent = state.settingsFirstRun
    ? "首次设置"
    : "设置";
  document.querySelector("#firstRunHint").classList.toggle(
    "hidden",
    !state.settingsFirstRun,
  );
  document.querySelector("#closeSettings").hidden = state.settingsFirstRun;
  document.querySelector("#cancelSettings").hidden = state.settingsFirstRun;
  document.querySelector("#settingsStatus").textContent = "";
  settingsForm.elements.email.value = settings.email || "";
  settingsForm.elements.authorization_code.value = "";
  settingsForm.elements.poll_minutes.value = settings.poll_minutes || 10;
  settingsForm.elements.lookback_days.value = settings.lookback_days || 3;
  settingsForm.elements.obsidian_enabled.checked = Boolean(settings.obsidian_enabled);
  settingsForm.elements.obsidian_output.value = settings.obsidian_output || "";
  settingsForm.elements.progress_enabled.checked = Boolean(settings.progress_enabled);
  settingsForm.elements.progress_output.value = settings.progress_output || "";
  settingsForm.elements.progress_source.value = settings.progress_source || "";
  settingsForm.elements.updates_enabled.checked = Boolean(settings.updates_enabled);
  settingsForm.elements.update_channel.value = settings.update_channel || "preview";
  document.querySelector("#currentVersion").textContent = `v${settings.app_version}`;
  renderUpdateStatus(await window.pywebview.api.get_update_status());
  if (!settingsDialog.open) settingsDialog.showModal();
}

window.openSettingsDialog = showSettingsDialog;

function settingsPayload() {
  return {
    email: settingsForm.elements.email.value.trim(),
    authorization_code: settingsForm.elements.authorization_code.value.trim(),
    poll_minutes: Number(settingsForm.elements.poll_minutes.value),
    lookback_days: Number(settingsForm.elements.lookback_days.value),
    obsidian_enabled: settingsForm.elements.obsidian_enabled.checked,
    obsidian_output: settingsForm.elements.obsidian_output.value.trim(),
    progress_enabled: settingsForm.elements.progress_enabled.checked,
    progress_output: settingsForm.elements.progress_output.value.trim(),
    progress_source: settingsForm.elements.progress_source.value.trim(),
    updates_enabled: settingsForm.elements.updates_enabled.checked,
    update_channel: settingsForm.elements.update_channel.value,
  };
}

function renderUpdateStatus(payload) {
  const status = document.querySelector("#updateStatus");
  const release = document.querySelector("#openUpdateRelease");
  const notes = document.querySelector("#updateNotes");
  const settingsButton = document.querySelector("#settingsButton");
  const banner = document.querySelector("#updateBanner");
  const current = payload.current_version ? `当前 v${payload.current_version}` : "";
  const messages = {
    idle: "尚未检查更新",
    checking: "正在检查 GitHub Release…",
    up_to_date: `${current}，已是最新版本`,
    available: `发现 v${payload.version}，请查看公告后手动更新`,
    error: payload.detail || "更新检查失败",
  };
  status.textContent = messages[payload.state] || payload.detail || "尚未检查更新";
  status.classList.toggle("error", payload.state === "error");
  status.classList.toggle("success", payload.state === "up_to_date");
  release.disabled = !payload.release_url;
  notes.classList.toggle("hidden", !payload.notes);
  document.querySelector("#updateNotesText").textContent = payload.notes || "";
  settingsButton.classList.toggle("update-ready", payload.state === "available");
  banner.classList.toggle("hidden", payload.state !== "available");
  banner.textContent = payload.state === "available"
    ? `v${payload.version} 可用 · 查看更新公告`
    : "";
}

async function pollUpdateStatus() {
  if (!apiReady()) return;
  const payload = await window.pywebview.api.get_update_status();
  renderUpdateStatus(payload);
  if (payload.state === "checking") {
    if (!updatePollTimer) {
      updatePollTimer = setInterval(pollUpdateStatus, 750);
    }
  } else if (updatePollTimer) {
    clearInterval(updatePollTimer);
    updatePollTimer = null;
  }
}

async function checkForUpdates() {
  if (!apiReady()) return;
  renderUpdateStatus(await window.pywebview.api.check_for_updates());
  await pollUpdateStatus();
}

window.checkForUpdates = checkForUpdates;

async function saveAppSettings(event) {
  event.preventDefault();
  if (!apiReady()) return;
  const button = settingsForm.querySelector("button[type='submit']");
  button.disabled = true;
  document.querySelector("#settingsStatus").textContent = "正在保存…";
  try {
    await window.pywebview.api.save_app_settings(settingsPayload());
    state.settingsFirstRun = false;
    settingsDialog.close();
    await refresh();
  } catch (error) {
    document.querySelector("#settingsStatus").textContent =
      error?.message || String(error);
  } finally {
    button.disabled = false;
  }
}

async function pickSettingsPath(kind) {
  if (!apiReady()) return;
  const selected = await window.pywebview.api.select_markdown_path(kind);
  if (selected) settingsForm.elements[kind].value = selected;
}

async function createProgressTemplateFromSettings() {
  if (!apiReady()) return;
  let path = settingsForm.elements.progress_source.value.trim();
  if (!path) {
    path = await window.pywebview.api.select_markdown_path("progress_source");
    if (!path) return;
    settingsForm.elements.progress_source.value = path;
  }
  try {
    const result = await window.pywebview.api.create_progress_source_template(path);
    document.querySelector("#settingsStatus").textContent = result.created
      ? `模板已创建：${result.path}`
      : "该文件已有内容，未覆盖。";
    settingsForm.elements.progress_enabled.checked = true;
  } catch (error) {
    document.querySelector("#settingsStatus").textContent =
      error?.message || String(error);
  }
}

async function testMailSettings() {
  if (!apiReady()) return;
  const status = document.querySelector("#settingsStatus");
  status.textContent = "正在测试只读连接…";
  const result = await window.pywebview.api.test_mail_settings(settingsPayload());
  status.textContent = result.detail;
  status.classList.toggle("success", Boolean(result.ok));
}

async function setCapsule(compact) {
  if (!apiReady()) return;
  state.compact = compact;
  document.body.classList.toggle("capsule", compact);
  await window.pywebview.api.set_capsule(compact);
}

async function refresh() {
  if (!apiReady()) return;
  try {
    const nextPayload = await window.pywebview.api.get_dashboard();
    state.payload = nextPayload;
    initializeCalendarAnchor();
    render();
  } catch (error) {
    healthText.textContent = "本地快照读取失败，稍后自动重试";
    healthDot.className = "health-dot error";
    console.error("dashboard refresh failed", error);
  }
}

async function initializeApp() {
  if (state.setupInitialized || !apiReady()) return;
  state.setupInitialized = true;
  await refresh();
  const settings = await window.pywebview.api.get_app_settings();
  if (!settings.credential_configured) await showSettingsDialog(true, settings);
  if (settings.updates_enabled) {
    await window.pywebview.api.maybe_check_for_updates();
    await pollUpdateStatus();
  }
}

function initializeCalendarAnchor() {
  if (state.calendarInitialized) return;
  const now = new Date();
  const next = state.payload.tasks
    .filter((task) => task.time && new Date(task.time) >= now)
    .sort((a, b) => new Date(a.time) - new Date(b.time))[0];
  if (next) {
    state.calendarAnchor = new Date(next.time);
    state.selectedDate = new Date(next.time);
  }
  state.calendarInitialized = true;
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
document.querySelector("#addButton").addEventListener("click", () => showTaskDialog());
document.querySelector("#settingsButton").addEventListener("click", () => showSettingsDialog(false));
document.querySelector("#updateBanner").addEventListener("click", () => showSettingsDialog(false));
document.querySelector("#capsuleButton").addEventListener("click", () => setCapsule(true));
document.querySelector("#expandButton").addEventListener("click", () => setCapsule(false));
document.querySelector("#closeDialog").addEventListener("click", () => taskDialog.close());
document.querySelector("#cancelDialog").addEventListener("click", () => taskDialog.close());
taskDialog.addEventListener("close", () => {
  if (apiReady()) window.pywebview.api.set_editor_mode(false);
});
taskForm.addEventListener("submit", saveTask);
settingsForm.addEventListener("submit", saveAppSettings);
document.querySelector("#closeSettings").addEventListener("click", () => settingsDialog.close());
document.querySelector("#cancelSettings").addEventListener("click", () => settingsDialog.close());
settingsDialog.addEventListener("cancel", (event) => {
  if (state.settingsFirstRun) event.preventDefault();
});
settingsDialog.addEventListener("close", () => {
  if (apiReady()) window.pywebview.api.set_editor_mode(false);
});
document.querySelectorAll("[data-pick-path]").forEach((button) => {
  button.addEventListener("click", () => pickSettingsPath(button.dataset.pickPath));
});
document.querySelector("#createProgressTemplate").addEventListener(
  "click",
  createProgressTemplateFromSettings,
);
document.querySelector("#testMailSettings").addEventListener("click", testMailSettings);
document.querySelector("#checkUpdates").addEventListener("click", checkForUpdates);
document.querySelector("#openUpdateRelease").addEventListener("click", () => {
  if (apiReady()) window.pywebview.api.open_update_release();
});
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

window.addEventListener("pywebviewready", initializeApp);
setTimeout(initializeApp, 800);
setInterval(refresh, 60_000);
