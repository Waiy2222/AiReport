/* ================================================================
   AI资讯早报/晚报 Dashboard — app.js
   ================================================================ */

// ---------- Config ----------
const API_BASE = (window.DASHBOARD_API_BASE || "http://localhost:8005").replace(/\/+$/, "");
const REFRESH_INTERVAL = 30000;  // 30 seconds

// ---------- State ----------
let refreshTimer = null;
let logPage = { offset: 0, limit: 20, total: 0 };
let scheduleData = null;

// ---------- Init ----------
document.addEventListener("DOMContentLoaded", () => {
  startClock();
  loadAll();
  refreshTimer = setInterval(loadAll, REFRESH_INTERVAL);
});

// ---------- API helpers ----------
async function apiGet(path, params = {}) {
  const url = new URL(`${API_BASE}${path}`);
  Object.entries(params).forEach(([k, v]) => { if (v !== "" && v != null) url.searchParams.set(k, v); });
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${body}`);
  }
  return res.json();
}

async function apiPost(path, body = null) {
  const opts = { method: "POST", headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${API_BASE}${path}`, opts);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json();
}

// ---------- Load all data ----------
async function loadAll() {
  try {
    const [overview, schedule, stats, healthAll, userStats, videos] = await Promise.allSettled([
      apiGet("/admin/overview"),
      apiGet("/admin/schedule"),
      apiGet("/api/dashboard/stats"),
      apiGet("/api/dashboard/health/all"),
      apiGet("/api/dashboard/users/stats"),
      apiGet("/api/dashboard/videos"),
    ]);
    const ov   = overview.status   === "fulfilled" ? overview.value   : null;
    const sch  = schedule.status   === "fulfilled" ? schedule.value   : null;
    const st   = stats.status      === "fulfilled" ? stats.value      : null;
    const hAll = healthAll.status  === "fulfilled" ? healthAll.value  : null;
    const us   = userStats.status  === "fulfilled" ? userStats.value  : null;
    const vs   = videos.status     === "fulfilled" ? videos.value     : null;

    if (ov)  renderOverview(ov);
    if (sch) { scheduleData = sch; renderSchedule(sch); }
    if (st)  renderStats(st);
    if (hAll) renderModuleHealth(hAll, ov?.modules);
    if (us)  renderUserStats(us);
    if (vs)  renderVideos(vs);
    refreshTagStates();
    if (!ov && !sch && !st && !hAll) showToast("error", "无法连接后端，请确认服务运行在 " + API_BASE);
  } catch (e) {
    console.error("loadAll error:", e);
  }
  loadLogs();
}

// ---------- Clock ----------
function startClock() {
  const tick = () => {
    const now = new Date();
    document.getElementById("clock").textContent =
      now.toLocaleString("zh-CN", { hour12: false });
  };
  tick();
  setInterval(tick, 1000);
}

// ---------- Render Module Health ----------
function renderModuleHealth(healthAll, overviewModules) {
  const container = document.getElementById("moduleCards");
  const map = { A: "资讯抓取", B: "AI加工", C: "推送", D: "发布", E: "调度", F: "视频生成" };

  const overviewStatus = overviewModules || {};
  const healthModules = healthAll?.modules || {};

  let html = "";
  for (const m of ["A", "B", "C", "D", "E", "F"]) {
    const runStatus = overviewStatus[m] || healthModules[m]?.status || "unknown";
    const lastRun = healthModules[m]?.last_run || null;
    const cls = statusClass(runStatus);
    html += `
      <div class="module-card ${cls}">
        <div class="mod-label">${m}</div>
        <div class="mod-status">${statusLabel(runStatus)}</div>
        <div class="mod-time">${lastRun ? formatTime(lastRun) : "—"}</div>
      </div>`;
  }
  container.innerHTML = html;
}

// ---------- Render Overview (briefings) ----------
function renderOverview(ov) {
  const container = document.getElementById("briefingCards");
  // preview 通过当前服务器代理到 module-b
  const previewBase = `${window.location.origin}/preview/`;
  let html = "";
  ["morning", "evening"].forEach((type) => {
    const d = ov[type] || {};
    const status = d.status || "pending";
    const bid = d.briefing_id || null;
    const genAt = d.generated_at || null;
    const label = type === "morning" ? "早报" : "晚报";
    const previewUrl = bid ? `${previewBase}${bid}` : "#";
    html += `
      <div class="briefing-card">
        <div class="bf-header">
          <span class="bf-type">${label}</span>
          <span class="badge badge-${status}">${statusLabel(status)}</span>
        </div>
        <div class="bf-id">ID: ${bid || "—"}</div>
        <div class="bf-time">${genAt ? formatTime(genAt) : "—"}</div>
        <div class="bf-actions">
          ${bid ? `<a href="${previewUrl}" target="_blank" class="btn btn-view">查看简报</a>
                   <a href="${previewBase.replace('/preview/', '/longimage/')}${bid}" class="btn btn-longimage">下载长图</a>` : ""}
        </div>
      </div>`;
  });
  container.innerHTML = html;
}

function toggleBriefing(el) {
  const expanded = el.classList.contains("expanded");
  document.querySelectorAll(".briefing-card").forEach((c) => c.classList.remove("expanded"));
  if (!expanded) el.classList.add("expanded");
}

// ---------- Trigger Pipeline ----------
function getSelectedTags() {
  const checked = document.querySelectorAll("#tagSelector input[type=checkbox]:checked");
  return Array.from(checked).map(cb => cb.value).join(",");
}

function toggleAICore() {
  const boxes = document.querySelectorAll(".tag-group-primary input[type=checkbox]");
  const anyUnchecked = Array.from(boxes).some(cb => !cb.checked);
  boxes.forEach(cb => { cb.checked = anyUnchecked; });
}

async function triggerPipeline(type) {
  const btnId = type === "morning" ? "triggerMorning" : "triggerEvening";
  const btn = document.getElementById(btnId);
  const fb = document.getElementById("triggerFeedback");
  const originalText = btn.textContent;

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 执行中...';
  fb.innerHTML = "";
  fb.className = "trigger-feedback";

  const tags = getSelectedTags();
  let url = `/admin/trigger?type=${type}`;
  if (tags) url += `&tags=${encodeURIComponent(tags)}`;

  try {
    const result = await apiPost(url);
    fb.innerHTML = `触发成功: batch_id=${result.batch_id}, status=${result.status}`;
    fb.className = "trigger-feedback success";
    showToast("success", `${type === "morning" ? "早报" : "晚报"}流水线触发成功`);
    setTimeout(loadAll, 3000);
  } catch (e) {
    fb.innerHTML = `触发失败: ${e.message}`;
    fb.className = "trigger-feedback error";
    showToast("error", `触发失败: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

async function triggerVideoPipeline() {
  const btn = document.getElementById("triggerVideo");
  const fb = document.getElementById("triggerFeedback");
  const originalText = btn.textContent;

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 生成中...';
  fb.innerHTML = "";
  fb.className = "trigger-feedback";

  try {
    const result = await apiPost("/admin/trigger-video?type=ai_agent_weekly");
    fb.innerHTML = `视频生成已触发: video_id=${result.video_id}, status=${result.status}`;
    fb.className = "trigger-feedback success";
    showToast("success", "视频生成触发成功");
    setTimeout(loadAll, 5000);
  } catch (e) {
    fb.innerHTML = `触发失败: ${e.message}`;
    fb.className = "trigger-feedback error";
    showToast("error", `视频触发失败: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

// ---------- Render User Stats ----------
function renderUserStats(us) {
  const container = document.getElementById("userStatsContent");
  const au = us.active_users || {};
  const tags = us.tag_distribution || {};
  const actions = us.recent_actions || {};

  const tagItems = Object.entries(tags)
    .sort((a, b) => b[1] - a[1])
    .map(([tag, count]) => `<span class="tag-chip">${tag} <strong>${count}</strong></span>`)
    .join("");

  const actionItems = Object.entries(actions)
    .map(([action, count]) => `<span class="stat-chip">${action}: ${count}</span>`)
    .join("");

  container.innerHTML = `
    <div class="user-stats-row">
      <div class="user-stat-card">
        <div class="stat-value">${au.last_7_days ?? 0}</div>
        <div class="stat-label">7日活跃</div>
      </div>
      <div class="user-stat-card">
        <div class="stat-value">${au.last_30_days ?? 0}</div>
        <div class="stat-label">30日活跃</div>
      </div>
      <div class="user-stat-card">
        <div class="stat-value">${us.total_subscribed ?? 0}</div>
        <div class="stat-label">订阅用户</div>
      </div>
    </div>
    <div class="user-stats-detail">
      <div class="detail-block">
        <h4>标签分布</h4>
        <div class="tag-cloud">${tagItems || '<span class="empty-hint">暂无数据</span>'}</div>
      </div>
      <div class="detail-block">
        <h4>近7日行为</h4>
        <div class="action-chips">${actionItems || '<span class="empty-hint">暂无数据</span>'}</div>
      </div>
    </div>`;
}

// ---------- Render Videos ----------
function renderVideos(vs) {
  const container = document.getElementById("videosContent");
  const videos = vs.videos || [];
  const byStatus = vs.by_status || {};

  const statusChips = Object.entries(byStatus)
    .map(([status, count]) => `<span class="stat-chip badge-${statusBadge(status)}">${statusLabel(status)}: ${count}</span>`)
    .join("");

  const rows = videos.map((v) => `
    <tr>
      <td title="${v.id}">${v.id?.slice(0, 8) ?? "—"}...</td>
      <td>${v.type || "—"}</td>
      <td>${v.title || "—"}</td>
      <td><span class="badge badge-${statusBadge(v.status)}">${statusLabel(v.status)}</span></td>
      <td>${v.duration_seconds ? v.duration_seconds + "s" : "—"}</td>
      <td>${v.created_at ? formatTime(v.created_at) : "—"}</td>
    </tr>
  `).join("");

  container.innerHTML = `
    <div class="user-stats-row">
      <div class="user-stat-card">
        <div class="stat-value">${vs.total ?? 0}</div>
        <div class="stat-label">视频总数</div>
      </div>
      <div class="user-stat-card" style="flex:2">
        <div class="action-chips">${statusChips || '<span class="empty-hint">暂无</span>'}</div>
      </div>
    </div>
    <div class="table-wrapper">
      <table class="runs-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>类型</th>
            <th>标题</th>
            <th>状态</th>
            <th>时长</th>
            <th>创建时间</th>
          </tr>
        </thead>
        <tbody>${rows || '<tr><td colspan="6" class="loading-placeholder">暂无视频记录</td></tr>'}</tbody>
      </table>
    </div>`;
}

// ---------- Render Stats ----------
function renderStats(st) {
  const container = document.getElementById("statsGrid");
  const ov = st.overall || {};
  const bft = st.briefings_by_type || {};
  let html = `
    <div class="stat-card stat-total">
      <div class="stat-value">${ov.total_runs ?? 0}</div>
      <div class="stat-label">总运行次数</div>
    </div>
    <div class="stat-card stat-success">
      <div class="stat-value">${ov.total_success ?? 0}</div>
      <div class="stat-label">成功</div>
    </div>
    <div class="stat-card stat-failed">
      <div class="stat-value">${ov.total_failed ?? 0}</div>
      <div class="stat-label">失败</div>
    </div>
    <div class="stat-card stat-rate">
      <div class="stat-value">${ov.success_rate ?? 0}%</div>
      <div class="stat-label">成功率</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${st.total_briefings ?? 0}</div>
      <div class="stat-label">简报总数</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${bft.morning || 0}/${bft.evening || 0}</div>
      <div class="stat-label">早报/晚报</div>
    </div>`;
  container.innerHTML = html;
}

// ---------- Render Schedule ----------
function renderSchedule(sch) {
  const container = document.getElementById("scheduleContent");
  const running = sch.scheduler_running;
  let html = "";
  ["morning", "evening"].forEach((type) => {
    const job = (sch.jobs || []).find((j) => j.id.includes(type));
    const nextRun = job?.next_run || null;
    const timeStr = type === "morning" ? sch.morning_time : sch.evening_time;
    html += `
      <div class="schedule-card">
        <div class="sched-label">${type === "morning" ? "早报" : "晚报"}定时</div>
        <div class="sched-time">${timeStr}</div>
        <div class="sched-countdown" id="countdown-${type}">${nextRun ? countdown(nextRun) : "—"}</div>
      </div>`;
  });
  html += `
    <div style="grid-column:1/-1">
      <span class="schedule-status ${running ? 'active' : 'stopped'}">
        ${running ? '调度运行中' : '调度已停止'}
      </span>
      <span style="font-size:0.75rem;color:var(--text-secondary);margin-left:8px;">
        时区: ${sch.timezone || "Asia/Shanghai"}
      </span>
    </div>`;
  container.innerHTML = html;
}

function countdown(isoStr) {
  const target = new Date(isoStr);
  const now = new Date();
  const diff = target - now;
  if (diff < 0) return "已过期";
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  const s = Math.floor((diff % 60000) / 1000);
  return `下次运行: ${h}时${m}分${s}秒后`;
}

// ---------- Run Logs ----------
async function loadLogs(offset = 0) {
  const module = document.getElementById("logFilterModule")?.value || "";
  const status = document.getElementById("logFilterStatus")?.value || "";
  logPage.offset = offset;

  try {
    const data = await apiGet("/api/dashboard/logs", {
      module, status, limit: logPage.limit, offset,
    });
    logPage.total = data.total;
    renderRunsTable(data.logs);
    renderLogPagination();
  } catch (e) {
    console.error("loadLogs error:", e);
    document.getElementById("runsTbody").innerHTML =
      `<tr><td colspan="6" class="loading-placeholder">加载失败: ${e.message}</td></tr>`;
  }
}

function renderRunsTable(logs) {
  const tbody = document.getElementById("runsTbody");
  if (!logs || logs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="loading-placeholder">暂无运行记录</td></tr>';
    return;
  }
  let html = "";
  logs.forEach((l) => {
    html += `
      <tr>
        <td><strong>${l.module}</strong></td>
        <td>${l.run_type === "morning" ? "早报" : l.run_type === "evening" ? "晚报" : l.run_type}</td>
        <td><span class="badge badge-${statusBadge(l.status)}">${statusLabel(l.status)}</span></td>
        <td>${l.started_at ? formatTime(l.started_at) : "—"}</td>
        <td>${l.finished_at ? formatTime(l.finished_at) : "—"}</td>
        <td>${l.status === "failed"
          ? `<button class="btn btn-retry" onclick="retryRun('${l.id}')">重试</button>`
          : "—"}</td>
      </tr>`;
  });
  tbody.innerHTML = html;
}

function renderLogPagination() {
  const container = document.getElementById("logPagination");
  const totalPages = Math.ceil(logPage.total / logPage.limit);
  const currentPage = Math.floor(logPage.offset / logPage.limit) + 1;
  container.innerHTML = `
    <button ${logPage.offset === 0 ? "disabled" : ""}
            onclick="loadLogs(${Math.max(0, logPage.offset - logPage.limit)})">上一页</button>
    <span>第 ${currentPage} / ${Math.max(1, totalPages)} 页 (共 ${logPage.total} 条)</span>
    <button ${logPage.offset + logPage.limit >= logPage.total ? "disabled" : ""}
            onclick="loadLogs(${logPage.offset + logPage.limit})">下一页</button>`;
}

// ---------- Retry ----------
async function retryRun(runId) {
  if (!confirm(`确定要重试运行 ${runId} 吗？`)) return;
  try {
    const result = await apiPost(`/api/dashboard/retry/${runId}`);
    showToast("success", `重试已触发 (${result.run_type})`);
    setTimeout(loadAll, 3000);
    loadLogs(logPage.offset);
  } catch (e) {
    showToast("error", `重试失败: ${e.message}`);
  }
}

// ---------- Modal ----------
function openModal(title, body) {
  document.getElementById("modalTitle").textContent = title;
  document.getElementById("modalBody").innerHTML = body;
  document.getElementById("modalOverlay").classList.add("active");
}

function closeModal() {
  document.getElementById("modalOverlay").classList.remove("active");
}

// ---------- Toast ----------
function showToast(type, message) {
  const container = document.getElementById("toastContainer");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity 0.3s";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ---------- 标签可用性刷新 ----------
async function refreshTagStates() {
  try {
    const [morning, evening] = await Promise.allSettled([
      apiGet("/api/briefings/latest?type=morning"),
      apiGet("/api/briefings/latest?type=evening"),
    ]);
    const activeTags = new Set();
    [morning, evening].forEach(r => {
      if (r.status !== "fulfilled" || !r.value) return;
      (r.value.sections || []).forEach(sec =>
        (sec.items || []).forEach(item =>
          (item.tags || []).forEach(t => activeTags.add(t))
        )
      );
    });

    document.querySelectorAll("#tagSelector input[type=checkbox]").forEach(cb => {
      const hasNews = activeTags.has(cb.value);
      cb.parentElement.classList.toggle("tag-disabled", !hasNews);
      // 无新闻 → 取消勾选 + 禁用
      if (!hasNews) {
        cb.checked = false;
        cb.disabled = true;
      } else {
        cb.disabled = false;
      }
    });
  } catch (e) {
    console.warn("refreshTagStates error:", e);
  }
}

// ---------- Helpers ----------
function statusClass(s) {
  if (s === "success") return "status-ok";
  if (s === "failed" || s === "error") return "status-fail";
  if (s === "running") return "status-running";
  return "status-unknown";
}

function statusLabel(s) {
  const map = { success: "成功", failed: "失败", running: "运行中", pending: "待处理", done: "已完成", unknown: "未知" };
  return map[s] || s;
}

function statusBadge(s) {
  const map = { success: "done", failed: "failed", running: "pending", done: "done", pending: "pending" };
  return map[s] || "pending";
}

function formatTime(isoStr) {
  if (!isoStr) return "—";
  try {
    const d = new Date(isoStr);
    return d.toLocaleString("zh-CN", { hour12: false });
  } catch (e) { return isoStr; }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
