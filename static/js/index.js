  const videoDownloadButton = document.getElementById("videoDownloadButton");
  const audioDownloadButton = document.getElementById("audioDownloadButton");
  const downloadControls = {
    video: {
      textarea: document.getElementById("videoUrls"),
      downloadButton: videoDownloadButton,
      clearButton: document.getElementById("videoClearButton"),
      turboToggle: document.getElementById("videoTurboToggle"),
      turboHint: document.getElementById("videoTurboHint"),
      downloadDirInput: document.getElementById("videoDownloadDir"),
      downloadDirField: document.getElementById("videoDownloadDirField"),
      historyButton: document.getElementById("videoDownloadDirHistoryButton"),
      historyMenu: document.getElementById("videoDownloadDirHistory"),
      browseButton: document.getElementById("videoBrowseButton"),
      downloadDirHint: document.getElementById("videoDownloadDirHint"),
      formatInputs: [],
      name: "视频",
    },
    audio: {
      textarea: document.getElementById("audioUrls"),
      downloadButton: audioDownloadButton,
      clearButton: document.getElementById("audioClearButton"),
      turboToggle: document.getElementById("audioTurboToggle"),
      turboHint: document.getElementById("audioTurboHint"),
      downloadDirInput: document.getElementById("audioDownloadDir"),
      downloadDirField: document.getElementById("audioDownloadDirField"),
      historyButton: document.getElementById("audioDownloadDirHistoryButton"),
      historyMenu: document.getElementById("audioDownloadDirHistory"),
      browseButton: document.getElementById("audioBrowseButton"),
      downloadDirHint: document.getElementById("audioDownloadDirHint"),
      formatInputs: Array.from(document.querySelectorAll('input[name="audioFormat"]')),
      name: "音频",
    },
  };
  const taskTitle = document.getElementById("task-title");
  const taskSummary = document.getElementById("task-summary");
  const taskContainer = document.getElementById("task-container");
  const activeMetric = document.getElementById("metric-active");
  const queueMetric = document.getElementById("metric-queue");
  const collectionPreview = document.getElementById("collectionPreview");
  const collectionPreviewList = document.getElementById("collectionPreviewList");
  const collectionPreviewTitle = document.getElementById("collectionPreviewTitle");
  const collectionPreviewCount = document.getElementById("collectionPreviewCount");
  const collectionSelectAll = document.getElementById("collectionSelectAll");
  const collectionSelectAllLabel = document.getElementById("collectionSelectAllLabel");
  const collectionSubmitButton = document.getElementById("collectionSubmitButton");
  const collectionLoadMoreButton = document.getElementById("collectionLoadMoreButton");
  const retryFailedButton = document.getElementById("retryFailedButton");
  const COLLECTION_PAGE_SIZE = 50;
  const DOWNLOAD_DIRECTORY_HISTORY_KEY = "multiple-video-downloader.download-directory-history.v1";
  const DOWNLOAD_DIRECTORY_HISTORY_LIMIT = 3;
  const VISIBLE_POLL_INTERVAL_MS = 800;
  const HIDDEN_POLL_INTERVAL_MS = 3000;

  let pollingTimer = null;
  let pollInFlight = false;
  let pollingActive = false;
  let lastTaskRenderSignature = null;
  let currentBatchId = null;
  let isDownloading = false;
  let aria2Available = false;
  let pendingPreview = null;
  let pendingDownloadSettings = null;
  let collectionRenderLimit = COLLECTION_PAGE_SIZE;
  let collectionSelectedIds = new Set();
  let folderPickerAvailable = false;
  let defaultDownloadDir = "downloads";
  let downloadDirectoryHistoryCache = [];
  let downloadDirectoryHistoryLoaded = false;
  const metricTargets = new WeakMap();

  function downloadDirectoryHistoryKey(path) {
    let comparable = path.trim().replace(/[\\/]+$/, "");
    if (/^[A-Za-z]:$/.test(comparable)) comparable += "\\";
    return /^(?:[A-Za-z]:[\\/]|\\\\)/.test(comparable)
      ? comparable.toLocaleLowerCase()
      : comparable;
  }

  function sanitizeDownloadDirectoryHistory(values) {
    const sanitized = [];
    const seen = new Set();
    for (const value of Array.isArray(values) ? values : []) {
      if (typeof value !== "string" || !value.trim()) continue;
      const path = value.trim();
      const key = downloadDirectoryHistoryKey(path);
      if (seen.has(key)) continue;
      seen.add(key);
      sanitized.push(path);
      if (sanitized.length === DOWNLOAD_DIRECTORY_HISTORY_LIMIT) break;
    }
    return sanitized;
  }

  function readDownloadDirectoryHistory() {
    if (!downloadDirectoryHistoryLoaded) {
      downloadDirectoryHistoryLoaded = true;
      try {
        const stored = JSON.parse(localStorage.getItem(DOWNLOAD_DIRECTORY_HISTORY_KEY) || "[]");
        downloadDirectoryHistoryCache = sanitizeDownloadDirectoryHistory(stored);
      } catch (_) {
        downloadDirectoryHistoryCache = [];
      }
    }
    return [...downloadDirectoryHistoryCache];
  }

  function writeDownloadDirectoryHistory(paths) {
    downloadDirectoryHistoryCache = sanitizeDownloadDirectoryHistory(paths);
    try {
      localStorage.setItem(
        DOWNLOAD_DIRECTORY_HISTORY_KEY,
        JSON.stringify(downloadDirectoryHistoryCache),
      );
    } catch (_) {
      // Browsers with blocked local storage still keep history for this page session.
    }
  }

  function setDownloadDirectoryHistoryExpanded(control, expanded) {
    control.historyMenu.hidden = !expanded;
    control.historyButton.setAttribute("aria-expanded", String(expanded));
    control.downloadDirInput.setAttribute("aria-expanded", String(expanded));
  }

  function closeDownloadDirectoryHistories(exceptMediaType = null) {
    Object.entries(downloadControls).forEach(([mediaType, control]) => {
      if (mediaType !== exceptMediaType) setDownloadDirectoryHistoryExpanded(control, false);
    });
  }

  function selectDownloadDirectoryHistory(mediaType, path) {
    const control = downloadControls[mediaType];
    if (!control || isDownloading) return;
    control.downloadDirInput.value = path;
    control.downloadDirHint.textContent = `将保存到：${path}`;
    setDownloadDirectoryHistoryExpanded(control, false);
    control.downloadDirInput.focus();
  }

  function renderDownloadDirectoryHistories() {
    const paths = readDownloadDirectoryHistory();
    Object.entries(downloadControls).forEach(([mediaType, control]) => {
      control.historyMenu.replaceChildren();
      if (paths.length === 0) {
        const empty = document.createElement("div");
        empty.className = "download-location-history-empty";
        empty.textContent = "暂无最近使用的位置";
        control.historyMenu.appendChild(empty);
        return;
      }
      paths.forEach(path => {
        const option = document.createElement("button");
        option.type = "button";
        option.className = "download-location-history-option";
        option.setAttribute("role", "option");
        option.title = path;
        option.textContent = path;
        option.addEventListener("click", () => selectDownloadDirectoryHistory(mediaType, path));
        control.historyMenu.appendChild(option);
      });
    });
  }

  function toggleDownloadDirectoryHistory(mediaType, event = null) {
    if (event) event.stopPropagation();
    const control = downloadControls[mediaType];
    if (!control || isDownloading) return;
    const shouldOpen = control.historyMenu.hidden;
    closeDownloadDirectoryHistories(mediaType);
    renderDownloadDirectoryHistories();
    setDownloadDirectoryHistoryExpanded(control, shouldOpen);
  }

  function rememberDownloadDirectory(path) {
    if (typeof path !== "string" || !path.trim()) return;
    writeDownloadDirectoryHistory([path.trim(), ...readDownloadDirectoryHistory()]);
    renderDownloadDirectoryHistories();
  }

  function initializeDownloadDirectoryHistory() {
    renderDownloadDirectoryHistories();
    Object.entries(downloadControls).forEach(([mediaType, control]) => {
      control.historyButton.addEventListener("keydown", event => {
        if (event.key !== "ArrowDown") return;
        event.preventDefault();
        if (control.historyMenu.hidden) toggleDownloadDirectoryHistory(mediaType, event);
        const firstOption = control.historyMenu.querySelector(".download-location-history-option");
        if (firstOption) firstOption.focus();
      });
    });
    document.addEventListener("click", event => {
      Object.values(downloadControls).forEach(control => {
        if (!control.downloadDirField.contains(event.target)) {
          setDownloadDirectoryHistoryExpanded(control, false);
        }
      });
    });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape") closeDownloadDirectoryHistories();
    });
  }

  function clearInput(mediaType) {
    if (isDownloading) return;
    const control = downloadControls[mediaType];
    control.textarea.value = "";
    control.textarea.focus();
  }

  function setControlsDisabled(disabled) {
    Object.values(downloadControls).forEach(control => {
      control.textarea.disabled = disabled;
      control.downloadButton.disabled = disabled;
      control.clearButton.disabled = disabled;
      control.downloadDirInput.disabled = disabled;
      control.historyButton.disabled = disabled;
      if (disabled) setDownloadDirectoryHistoryExpanded(control, false);
      control.browseButton.disabled = disabled || !folderPickerAvailable;
      control.turboToggle.disabled = disabled || !aria2Available;
      control.formatInputs.forEach(formatInput => {
        formatInput.disabled = disabled;
      });
    });
  }

  async function loadCapabilities() {
    try {
      const response = await fetch("/api/capabilities");
      if (!response.ok) throw new Error("capability request failed");
      const capabilities = await response.json();
      aria2Available = capabilities.aria2c_available === true;
      folderPickerAvailable = capabilities.folder_picker_available === true;
      defaultDownloadDir = capabilities.default_download_dir || "downloads";
    } catch (_) {
      aria2Available = false;
      folderPickerAvailable = false;
    }

    Object.values(downloadControls).forEach(control => {
      control.turboToggle.disabled = !aria2Available || isDownloading;
      control.turboHint.textContent = aria2Available
        ? "已检测到 aria2c，可为 Bilibili 大文件启用多连接下载"
        : "未安装 aria2c，当前使用标准模式";
      if (!aria2Available) control.turboToggle.checked = false;
      control.browseButton.disabled = !folderPickerAvailable || isDownloading;
      control.downloadDirHint.textContent = folderPickerAvailable
        ? `留空使用默认位置：${defaultDownloadDir}`
        : `留空使用默认位置：${defaultDownloadDir}；当前环境请手动输入路径`;
    });
  }

  async function chooseDownloadDirectory(mediaType) {
    if (isDownloading) return;
    const control = downloadControls[mediaType];
    if (!control || !folderPickerAvailable) return;
    control.browseButton.disabled = true;
    control.browseButton.textContent = "等待选择…";
    try {
      const response = await fetch("/api/select-directory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ initial_dir: control.downloadDirInput.value.trim() || null }),
      });
      const data = await response.json();
      if (!response.ok) {
        alert("❌ " + formatApiError(data, "无法打开文件夹选择器"));
        return;
      }
      if (!data.cancelled && data.download_dir) {
        control.downloadDirInput.value = data.download_dir;
        control.downloadDirHint.textContent = `将保存到：${data.download_dir}`;
        setDownloadDirectoryHistoryExpanded(control, false);
      }
    } catch (error) {
      alert("❌ 无法选择文件夹：" + error.message);
    } finally {
      control.browseButton.textContent = "选择文件夹";
      control.browseButton.disabled = isDownloading || !folderPickerAvailable;
    }
  }

  function setOperationalMetrics(active, queue) {
    [[activeMetric, active], [queueMetric, queue]].forEach(([element, value]) => {
      const nextValue = String(value).padStart(2, "0");
      const requestedTarget = metricTargets.get(element);
      if (
        requestedTarget === nextValue
        || (requestedTarget === undefined && element.textContent === nextValue)
      ) return;
      if (typeof window.MotionSystem?.setNumber === "function") {
        window.MotionSystem?.setNumber(element, nextValue);
      } else {
        element.textContent = nextValue;
      }
      metricTargets.set(element, nextValue);
      element.classList.remove("metric-flash");
      void element.offsetWidth;
      element.classList.add("metric-flash");
      window.setTimeout(() => element.classList.remove("metric-flash"), 320);
    });
  }

  function updateOperationalMetrics(batch) {
    const tasks = Array.isArray(batch.tasks) ? batch.tasks : [];
    const active = Number.isInteger(batch.active)
      ? batch.active
      : tasks.filter(task => ["running", "running_uninterruptible"].includes(task.status)).length;
    const queue = Number.isInteger(batch.queued)
      ? batch.queued
      : tasks.filter(task => task.status === "queued").length;
    setOperationalMetrics(active, queue);
  }

  function audioFormatTitle(audioFormat) {
    return {
      mp3: "MP3 V0",
      flac: "源 FLAC",
      source: "原始音轨",
      wav: "WAV PCM",
    }[audioFormat] || "音频";
  }

  function formatApiError(data, fallback = "请求失败") {
    if (!data || typeof data !== "object") return fallback;
    const code = data.error_code ? `[${data.error_code}] ` : "";
    const message = data.message || data.error || fallback;
    const suggestion = data.suggestion ? `\n建议：${data.suggestion}` : "";
    return `${code}${message}${suggestion}`;
  }

  async function startDownload(mediaType) {
    if (isDownloading) return;
    const control = downloadControls[mediaType];
    if (!control) return;

    const raw = control.textarea.value.trim();
    if (!raw) {
      alert(`请先粘贴至少一个${control.name}链接。`);
      return;
    }

    const urls = raw.split("\n").map(s => s.trim()).filter(Boolean);
    if (urls.length === 0) {
      alert("未检测到有效的链接行。");
      return;
    }

    const speedMode = control.turboToggle.checked ? "turbo" : "standard";
    const audioFormat = mediaType === "audio"
      ? document.querySelector('input[name="audioFormat"]:checked').value
      : "mp3";

    pendingDownloadSettings = {
      mediaType,
      speedMode,
      audioFormat,
      downloadDir: control.downloadDirInput.value.trim(),
    };
    isDownloading = true;
    setControlsDisabled(true);
    taskTitle.textContent = "正在解析输入";
    taskSummary.textContent = "读取播放列表、合集与分 P 信息...";
    await previewInput(mediaType, urls);
  }

  async function previewInput(mediaType, inputs) {
    try {
      const response = await fetch("/api/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ inputs }),
      });
      const preview = await response.json();
      if (!response.ok) {
        alert("❌ " + formatApiError(preview));
        resetUI();
        return;
      }
      pendingPreview = preview;
      renderCollectionPreview(preview, mediaType);
      if (!preview.requires_selection) await submitPreview(mediaType);
    } catch (error) {
      alert("❌ 网络错误：" + error.message);
      resetUI();
    }
  }

  function renderCollectionPreview(preview, mediaType) {
    const entries = Array.isArray(preview.entries) ? preview.entries : [];
    collectionPreviewTitle.textContent = preview.is_single
      ? "确认下载内容"
      : `${preview.title || "下载合集"} · 选择条目`;
    collectionRenderLimit = COLLECTION_PAGE_SIZE;
    collectionSelectedIds = new Set(
      entries.filter(entry => entry.selectable === true).slice(0, 100).map(entry => entry.id)
    );
    renderCollectionEntries(mediaType);
    collectionPreview.hidden = false;
    updateCollectionSelection();
    collectionPreview.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function renderCollectionEntries(mediaType) {
    const entries = Array.isArray(pendingPreview && pendingPreview.entries)
      ? pendingPreview.entries
      : [];
    const visibleEntries = entries.slice(0, collectionRenderLimit);
    collectionPreviewList.innerHTML = visibleEntries.map((entry, index) => {
      const selectable = entry.selectable === true;
      const checked = selectable && collectionSelectedIds.has(entry.id);
      const thumbnail = entry.thumbnail
        ? `<img class="collection-thumb" src="${escHtml(entry.thumbnail)}" alt="" loading="lazy">`
        : `<span class="collection-thumb collection-thumb-placeholder">${String(index + 1).padStart(2, "0")}</span>`;
      return `
        <label class="collection-entry ${selectable ? "" : "is-unavailable"}">
          <input type="checkbox" class="collection-entry-checkbox" data-entry-id="${escHtml(entry.id)}" data-selectable="${selectable}" ${checked ? "checked" : ""} ${selectable ? "" : "disabled"} onchange="updateCollectionSelection(this)">
          ${thumbnail}
          <span class="collection-entry-copy">
            <span class="collection-entry-title">${escHtml(entry.title || `第 ${index + 1} 项`)}</span>
            <span class="collection-entry-meta">${selectable ? `第 ${entry.position || index + 1} 项 · ${mediaType === "audio" ? "音频" : "视频"}` : escHtml(entry.unavailable_reason || "不可下载")}</span>
          </span>
        </label>`;
    }).join("");
    collectionLoadMoreButton.hidden = collectionRenderLimit >= entries.length;
    if (!collectionLoadMoreButton.hidden) {
      const remaining = entries.length - collectionRenderLimit;
      collectionLoadMoreButton.textContent = `显示更多条目（剩余 ${remaining} 项）`;
    }
  }

  function loadMoreCollectionEntries() {
    collectionRenderLimit += COLLECTION_PAGE_SIZE;
    renderCollectionEntries(pendingDownloadSettings && pendingDownloadSettings.mediaType);
    updateCollectionSelection();
  }

  function selectedEntryIds() {
    return Array.from(collectionSelectedIds);
  }

  function toggleCollectionSelectAll() {
    const entries = Array.isArray(pendingPreview && pendingPreview.entries)
      ? pendingPreview.entries
      : [];
    collectionSelectedIds = collectionSelectAll.checked
      ? new Set(entries.filter(entry => entry.selectable === true).slice(0, 100).map(entry => entry.id))
      : new Set();
    updateCollectionSelection();
  }

  function updateCollectionSelection(changedInput = null) {
    if (changedInput) {
      const entryId = changedInput.dataset.entryId;
      if (changedInput.checked && collectionSelectedIds.size < 100) {
        collectionSelectedIds.add(entryId);
      } else {
        collectionSelectedIds.delete(entryId);
        changedInput.checked = false;
      }
    }
    const selected = selectedEntryIds();
    const inputs = Array.from(collectionPreviewList.querySelectorAll(".collection-entry-checkbox"));
    const entries = Array.isArray(pendingPreview && pendingPreview.entries)
      ? pendingPreview.entries
      : [];
    const selectableCount = entries.filter(entry => entry.selectable === true).length;
    const selectionTarget = Math.min(selectableCount, 100);
    const atLimit = selected.length >= 100;
    inputs.forEach(input => {
      const isSelectable = input.dataset.selectable === "true";
      input.checked = collectionSelectedIds.has(input.dataset.entryId);
      input.disabled = !isSelectable || (atLimit && !input.checked);
    });
    collectionSelectAll.checked = selectionTarget > 0 && selected.length === selectionTarget;
    collectionSelectAll.indeterminate = selected.length > 0 && selected.length < selectionTarget;
    collectionSelectAll.disabled = selectionTarget === 0;
    collectionSelectAllLabel.textContent = selectableCount > 100 ? "选择前 100 项" : "全选";
    const truncationNote = pendingPreview && pendingPreview.truncated
      ? " · 预览仅展示前 1000 项，请拆分链接后继续选择"
      : "";
    collectionPreviewCount.textContent = `已选择 ${selected.length} 项 · 最多选择 100 项${truncationNote}`;
    collectionSubmitButton.disabled = selected.length === 0 || selected.length > 100;
  }

  function cancelCollectionPreview() {
    pendingPreview = null;
    pendingDownloadSettings = null;
    collectionPreview.hidden = true;
    collectionPreviewList.innerHTML = "";
    collectionLoadMoreButton.hidden = true;
    collectionSelectedIds = new Set();
    resetUI();
  }

  async function submitPreview(mediaType = pendingDownloadSettings && pendingDownloadSettings.mediaType) {
    if (!pendingPreview || !pendingDownloadSettings) return;
    const selected = selectedEntryIds();
    if (selected.length === 0) {
      alert("请至少选择一个可下载条目。");
      return;
    }
    if (selected.length > 100) {
      alert("一次最多选择 100 项。");
      return;
    }

    collectionSubmitButton.disabled = true;
    collectionPreview.hidden = true;
    setOperationalMetrics(0, selected.length);
    renderPendingSkeleton(selected.length);
    taskTitle.textContent = mediaType === "audio"
      ? `${audioFormatTitle(pendingDownloadSettings.audioFormat)} 音频下载任务`
      : "视频下载任务";
    taskSummary.textContent = "正在提交...";

    const payload = {
      preview_id: pendingPreview.preview_id,
      selected_entry_ids: selected,
      media_type: mediaType,
      speed_mode: pendingDownloadSettings.speedMode,
      audio_format: pendingDownloadSettings.audioFormat,
      download_dir: pendingDownloadSettings.downloadDir || null,
    };
    try {
      const response = await fetch("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        alert("❌ " + formatApiError(data));
        collectionPreview.hidden = false;
        collectionSubmitButton.disabled = false;
        return;
      }
      rememberDownloadDirectory(data.download_dir);
      currentBatchId = data.batch_id;
      pendingPreview = null;
      pendingDownloadSettings = null;
      taskSummary.textContent = `共 ${data.task_count} 个任务 · 保存到 ${data.download_dir || defaultDownloadDir}`;
      startPolling();
    } catch (error) {
      alert("❌ 网络错误：" + error.message);
      collectionPreview.hidden = false;
      collectionSubmitButton.disabled = false;
    }
  }

  function startPolling() {
    stopPolling();
    pollingActive = true;
    pollStatus();
  }

  function stopPolling() {
    pollingActive = false;
    if (pollingTimer) {
      clearTimeout(pollingTimer);
      pollingTimer = null;
    }
  }

  function scheduleNextPoll(delay) {
    if (!pollingActive || !currentBatchId) return;
    if (pollingTimer) clearTimeout(pollingTimer);
    pollingTimer = setTimeout(() => {
      pollingTimer = null;
      pollStatus();
    }, delay);
  }

  function taskRenderSignature(batch) {
    const tasks = Array.isArray(batch.tasks) ? batch.tasks : [];
    return JSON.stringify(tasks.map(task => ({
      id: task.id,
      url: task.url,
      status: task.status,
      progress: task.progress,
      result: task.result,
      postprocessing: task.postprocessing,
      speed_mode_used: task.speed_mode_used,
      turbo_fallback: task.turbo_fallback,
      error: task.error,
      attempt_count: task.attempt_count,
      attempts: task.attempts,
      can_cancel: task.can_cancel,
      can_retry: task.can_retry,
      can_redownload: task.can_redownload,
    })));
  }

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && pollingActive && !pollInFlight) {
      pollStatus();
      return;
    }
    if (!pollInFlight) {
      scheduleNextPoll(document.hidden ? HIDDEN_POLL_INTERVAL_MS : VISIBLE_POLL_INTERVAL_MS);
    }
  });

  async function pollStatus() {
    if (!pollingActive || !currentBatchId || pollInFlight) return;
    const requestedBatchId = currentBatchId;
    pollInFlight = true;
    try {
      const resp = await fetch("/api/batch/" + requestedBatchId);
      if (!resp.ok) return;
      const batch = await resp.json();
      if (currentBatchId !== requestedBatchId) return;
      updateOperationalMetrics(batch);
      const renderSignature = taskRenderSignature(batch);
      if (renderSignature !== lastTaskRenderSignature) {
        renderTasks(batch);
        lastTaskRenderSignature = renderSignature;
      }

      taskTitle.textContent = batch.media_type === "audio"
        ? `${audioFormatTitle(batch.audio_format)} 音频下载任务`
        : "视频下载任务";
      taskSummary.textContent =
        `共 ${batch.total} 个 · 完成 ${batch.completed} · 失败 ${batch.failed} · 取消 ${batch.cancelled || 0} · 批次 ${batch.id}`;
      retryFailedButton.hidden = !batch.tasks.some(task => task.can_retry && task.status === "failed");

      if (batch.all_done) {
        stopPolling();
        isDownloading = false;
        setControlsDisabled(false);
      }
    } catch (_) { /* retry on next tick */
    } finally {
      pollInFlight = false;
      scheduleNextPoll(document.hidden ? HIDDEN_POLL_INTERVAL_MS : VISIBLE_POLL_INTERVAL_MS);
    }
  }

  function renderPendingSkeleton(count) {
    let html = '<ul class="task-list">';
    for (let i = 0; i < count; i++) {
      html += `
        <li class="task-item task-item-enter status-queued">
          <span class="task-index">${String(i + 1).padStart(2, "0")}</span>
          <div class="task-body"><div class="task-meta">等待可用下载槽位</div></div>
          <span class="badge badge-queued">等待中</span>
        </li>`;
    }
    html += "</ul>";
    taskContainer.innerHTML = html;
  }

  function formatAttemptTime(value) {
    const milliseconds = Number(value) * 1000;
    if (!Number.isFinite(milliseconds) || milliseconds <= 0) return "未结束";
    return new Date(milliseconds).toLocaleString("zh-CN", { hour12: false });
  }

  function renderTasks(batch) {
    let html = '<ul class="task-list">';
    batch.tasks.forEach((t, i) => {
      const cls = "status-" + t.status;
      const badgeMap = {
        queued: ["等待中", "badge-queued"],
        running: ["下载中", "badge-running"],
        running_uninterruptible: ["极速下载", "badge-running"],
        completed: ["下载完成", "badge-completed"],
        failed: ["下载失败", "badge-failed"],
        cancelled: ["已取消", "badge-cancelled"],
      };
      const [label, badgeCls] = badgeMap[t.status] || ["未知", ""];

      html += `<li class="task-item ${cls}">`;
      html += `<span class="task-index">${String(i + 1).padStart(2, "0")}</span>`;
      html += `<div class="task-body">`;
      html += `<div class="task-url">${escHtml(t.url)}</div>`;

      if (t.status === "completed" && t.result) {
        const r = t.result;
        html += `<div class="task-meta">`;
        html += `<strong>${escHtml(r.title || "未知")}</strong><br>`;
        if (batch.media_type === "audio") {
          html += `格式: ${escHtml(r.format || "MP3")} · `;
          html += `音频编码: ${escHtml(r.acodec || "mp3")} · `;
          if (r.source_acodec && r.source_acodec !== "未知") {
            html += `源编码: ${escHtml(r.source_acodec)}`;
            if (r.source_abr_kbps && r.source_abr_kbps !== "未知") {
              html += ` ${escHtml(r.source_abr_kbps)} kbps`;
            }
            html += ` · `;
          }
        } else {
          html += `分辨率: ${escHtml(r.resolution || "?")} · `;
        }
        html += `大小: ${escHtml(r.filesize || "?")}`;
        if (batch.media_type === "audio" && r.audio_format_fallback) {
          html += `<br>源站未提供 FLAC，已自动回退至 MP3 V0`;
        }
        if (r.filepath) html += `<br>保存路径: ${escHtml(r.filepath)}`;
        html += `</div>`;
      } else if (["running", "running_uninterruptible"].includes(t.status)) {
        if (t.postprocessing) {
          html += `<div class="task-meta"><span class="spinner"></span> ${escHtml(t.postprocessing.stage_text || "正在处理媒体文件…")}</div>`;
          if (t.postprocessing.detail_text) {
            html += `<div class="task-meta">${escHtml(t.postprocessing.detail_text)}</div>`;
          }
        } else if (t.speed_mode_used === "turbo" && !t.turbo_fallback) {
          html += `<div class="task-meta"><span class="spinner"></span> 高速下载中</div>`;
        } else {
          if (t.turbo_fallback) {
            html += `<div class="task-meta">极速模式不可用，已切换标准模式</div>`;
          }
          html += `<div class="task-meta"><span class="spinner"></span> 正在下载，请稍候…</div>`;
          html += renderDownloadProgress(t.progress);
        }
        if (t.status === "running_uninterruptible") {
          html += `<div class="task-meta">aria2c 极速任务不可取消，将继续下载直至完成</div>`;
        }
      } else if (t.status === "queued") {
        html += `<div class="task-meta">等待可用下载槽位</div>`;
      } else if (t.status === "failed") {
        html += `<div class="task-meta">下载失败</div>`;
        if (t.error) {
          html += `<div class="task-error"><span class="task-error-code">${escHtml(t.error.error_code || "DOWNLOAD_FAILED")}</span> · ${escHtml(t.error.message || "下载失败")}`;
          if (t.error.suggestion) html += `<br>建议：${escHtml(t.error.suggestion)}`;
          html += `</div>`;
        }
      } else if (t.status === "cancelled") {
        html += `<div class="task-meta">任务已取消，已完成文件仍然保留。</div>`;
      }

      if (t.attempt_count > 0 && Array.isArray(t.attempts)) {
        html += `<details class="task-attempts"><summary>尝试记录 ${t.attempt_count}</summary><div class="task-attempts-list">`;
        t.attempts.forEach(attempt => {
          const started = formatAttemptTime(attempt.started_at);
          const finished = formatAttemptTime(attempt.finished_at);
          html += `<span class="task-attempt">#${attempt.number} · ${escHtml(attempt.status)}${attempt.output_version > 1 ? ` · 版本 ${attempt.output_version}` : ""} · 开始 ${escHtml(started)} · 结束 ${escHtml(finished)}</span>`;
        });
        html += `</div></details>`;
      }

      html += `<div class="task-actions">`;
      if (t.can_cancel) html += `<button class="task-action" onclick="operateTask('cancel', '${escHtml(t.id)}')">取消</button>`;
      if (t.can_retry) html += `<button class="task-action" onclick="operateTask('retry', '${escHtml(t.id)}')">重试</button>`;
      if (t.can_redownload) html += `<button class="task-action" onclick="operateTask('redownload', '${escHtml(t.id)}')">重新下载</button>`;
      html += `</div>`;

      html += `</div>`;
      html += `<span class="badge ${badgeCls}">${["running", "running_uninterruptible"].includes(t.status) ? '<span class="spinner"></span>' : ""}${label}</span>`;
      html += `</li>`;
    });
    html += "</ul>";
    taskContainer.innerHTML = html;
  }

  async function operateTask(action, taskId) {
    if (!currentBatchId) return;
    try {
      const response = await fetch(`/api/batch/${currentBatchId}/task/${taskId}/${action}`, { method: "POST" });
      const data = await response.json();
      if (!response.ok) {
        alert("❌ " + formatApiError(data));
        return;
      }
      if (["retry", "redownload"].includes(action)) {
        isDownloading = true;
        setControlsDisabled(true);
      }
      startPolling();
    } catch (error) {
      alert("❌ 网络错误：" + error.message);
    }
  }

  async function retryFailedTasks() {
    if (!currentBatchId) return;
    try {
      const response = await fetch(`/api/batch/${currentBatchId}/retry-failed`, { method: "POST" });
      const data = await response.json();
      if (!response.ok) {
        alert("❌ " + formatApiError(data));
        return;
      }
      retryFailedButton.hidden = true;
      isDownloading = true;
      setControlsDisabled(true);
      startPolling();
    } catch (error) {
      alert("❌ 网络错误：" + error.message);
    }
  }

  function renderDownloadProgress(progress) {
    const speed = progress && progress.speed_text ? progress.speed_text : "计算中";
    const eta = progress && progress.eta_text ? progress.eta_text : "计算中";
    const percent = progress && progress.percent_text ? progress.percent_text : "";
    const totalSize = progress && progress.total_size_text ? progress.total_size_text : "计算中";
    const totalSizeLabel = progress && progress.total_size_is_estimate ? "预计总大小" : "总大小";

    let html = `<div class="task-progress">`;
    html += `<span class="task-progress-item"><span class="task-progress-label">下载速度</span><span class="task-progress-value">${escHtml(speed)}</span></span>`;
    html += `<span class="task-progress-item"><span class="task-progress-label">预计剩余</span><span class="task-progress-value">${escHtml(eta)}</span></span>`;
    html += `<span class="task-progress-item"><span class="task-progress-label">${escHtml(totalSizeLabel)}</span><span class="task-progress-value">${escHtml(totalSize)}</span></span>`;
    if (percent && percent !== "计算中") {
      html += `<span class="task-progress-item"><span class="task-progress-label">进度</span><span class="task-progress-value">${escHtml(percent)}</span></span>`;
    }
    html += `</div>`;
    return html;
  }

  function resetUI(resetMetrics = true) {
    isDownloading = false;
    setControlsDisabled(false);
    pendingPreview = null;
    pendingDownloadSettings = null;
    collectionSelectedIds = new Set();
    collectionPreview.hidden = true;
    if (resetMetrics) setOperationalMetrics(0, 0);
  }

  function escHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  Object.assign(window, {
    cancelCollectionPreview,
    chooseDownloadDirectory,
    clearInput,
    loadMoreCollectionEntries,
    operateTask,
    retryFailedTasks,
    startDownload,
    submitPreview,
    toggleCollectionSelectAll,
    toggleDownloadDirectoryHistory,
    updateCollectionSelection,
  });
  initializeDownloadDirectoryHistory();
  loadCapabilities();
