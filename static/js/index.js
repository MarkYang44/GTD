  // Only app-owned text is localized; media metadata and diagnostic details stay intact.
  const localizedLabels = new Map();
  let lastRenderedBatch = null;
  let pendingSkeletonCount = null;
  function tr(zh, en, params = {}) {
    if (window.GtdLanguage) return window.GtdLanguage.t(zh, en, params);
    return zh.replace(/\{(\w+)\}/g, (_, key) => params[key] ?? `{${key}}`);
  }
  function setLocalized(element, zh, en, params = {}) {
    localizedLabels.set(element, {zh, en, params});
    element.textContent = tr(zh, en, params);
  }
  function mediaName(type) { return type === 'audio' ? tr('音频', 'Audio') : tr('视频', 'Video'); }
  function setTaskHeading(type, format) {
    // Store the raw format so switching can also translate its display name.
    taskHeading = {type, format};
    taskTitle.textContent = type === 'audio'
      ? tr('{format} 音频下载任务', '{format} audio downloads', {format: audioFormatTitle(format)})
      : tr('视频下载任务', 'Video downloads');
    localizedLabels.delete(taskTitle);
  }
  let taskHeading = null;
  function statusLabel(status) {
    const labels = {queued:['等待中','Queued'], running:['下载中','Downloading'], running_uninterruptible:['极速下载','Turbo download'], completed:['下载完成','Completed'], failed:['下载失败','Failed'], cancelled:['已取消','Cancelled']};
    return labels[status] ? tr(...labels[status]) : status;
  }
  const downloadErrors = {
    CANCELLED: ['任务已取消', 'Task cancelled', '可以点击重试重新加入队列', 'Click Retry to rejoin the queue'],
    NETWORK_TIMEOUT: ['网络连接源站超时', 'The connection to the source timed out', '请检查网络或代理设置后重试', 'Check your network or proxy settings and retry'],
    NETWORK_CONNECTION_RESET: ['媒体传输连接被远端中断', 'The remote server interrupted the media transfer', '程序会尝试备用线路；如仍失败，请检查网络或代理后重试', 'The app will try an alternate connection. If it fails again, check your network or proxy and retry'],
    RATE_LIMITED: ['请求过于频繁', 'Too many requests', '请稍后再重试，并避免同时提交大量链接', 'Retry later and avoid submitting many links at once'],
    MEMBERSHIP_REQUIRED: ['该内容需要会员权限', 'This content requires a membership', '请确认当前 Cookie 对应账号拥有访问权限', 'Make sure the account associated with your cookies can access this content'],
    AUTH_REQUIRED: ['当前凭证无法访问该内容', 'Your current credentials cannot access this content', '请更新对应平台 Cookie 后重试', 'Update the cookies for this platform and retry'],
    GEO_RESTRICTED: ['该内容受到版权或地区限制', 'This content has copyright or regional restrictions', '请确认当前地区允许访问该内容', 'Check whether this content is available in your region'],
    FORMAT_UNAVAILABLE: ['源站没有可用的目标格式', 'The requested format is unavailable at the source', '请选择其他输出格式或更换链接', 'Choose another output format or URL'],
    ARIA2_FAILED: ['aria2c 极速下载失败', 'aria2c turbo download failed', '请重试；程序会按现有规则降级到标准模式', 'Retry; the app will fall back to standard mode when applicable'],
    POSTPROCESS_FAILED: ['媒体后处理失败', 'Media postprocessing failed', '请确认 FFmpeg 可用且磁盘空间充足', 'Make sure FFmpeg is available and there is enough disk space'],
    COLLECTION_EXTRACT_FAILED: ['无法解析播放列表或合集', 'Unable to read the playlist or collection', '请确认链接公开可访问并更新 Cookie 后重试', 'Make sure the URL is publicly accessible, update your cookies, and retry'],
    METADATA_FAILED: ['无法读取媒体信息', 'Unable to read media information', '请检查链接、Cookie 和网络后重试', 'Check the URL, cookies, and network, then retry'],
    STORAGE_ERROR: ['无法写入下载文件', 'Unable to write the downloaded file', '请检查下载目录权限和磁盘空间', 'Check output folder permissions and available disk space'],
    DOWNLOAD_FAILED: ['下载失败', 'Download failed', '请查看错误日志后重试', 'Check the error log and retry'],
    PREVIEW_EXPIRED: ['下载预览不存在或已过期', 'The download preview is missing or expired', '请重新解析链接并选择条目', 'Parse the links again and select the items'],
    BATCH_NOT_FOUND: ['任务批次不存在或已过期', 'The task batch is missing or expired', '请重新提交下载任务', 'Submit the download tasks again'],
    UNSUPPORTED_PLATFORM: ['该链接不是受支持的 YouTube、Instagram 或 Bilibili 视频页面', 'This URL is not a supported YouTube, Instagram, or Bilibili video page', '播放列表、合集与分 P 请先使用预览功能', 'Preview playlists, collections, and multipart videos first'],
    INVALID_URL: ['链接格式无效', 'Invalid URL', '请粘贴完整的 HTTP(S) 视频链接', 'Paste a complete HTTP(S) video URL'],
    FOLDER_PICKER_UNAVAILABLE: ['', 'The folder picker is unavailable', '请在下载位置输入框中手动输入文件夹路径', 'Enter the folder path manually in the download location field'],
    INVALID_DOWNLOAD_DIR: ['', 'Invalid download folder', '请选择或输入一个可创建且可写的文件夹', 'Choose or enter a folder that can be created and written to'],
    INVALID_REQUEST: ['', 'Invalid request', '请检查请求内容后重试', 'Check the request and retry'],
    TASK_NOT_FOUND: ['', 'Task not found', '请刷新任务列表后重试', 'Refresh the task list and retry'],
    TASK_STATE_CONFLICT: ['', 'This action is unavailable in the current task state', '请刷新任务状态后再操作', 'Refresh the task status before trying again'],
  };
  function localizedError(error) {
    const raw = error.message || error.error || '';
    const entry = downloadErrors[error.error_code];
    if (window.GtdLanguage?.language !== 'en') return {message: raw, suggestion: error.suggestion || ''};
    if (!entry) return {
      message: raw ? `Request failed. Original details: ${raw}` : 'Request failed',
      suggestion: error.suggestion ? `Original suggestion: ${error.suggestion}` : '',
    };
    return {
      // Known codes carry app-owned guidance, not third-party diagnostics.
      message: backendTranslations[raw] || entry[1],
      suggestion: error.suggestion ? (backendTranslations[error.suggestion] || entry[3]) : '',
    };
  }
  const backendTranslations = {
    '计算中': 'Calculating', '未知': 'Unknown', '内容不可访问': 'Content is inaccessible', '源站未提供可下载链接': 'The source did not provide a downloadable URL',
    '请输入一个可创建且可写的文件夹，留空则使用默认 downloads': 'Enter a folder that can be created and written to, or leave blank to use downloads',
    '请刷新任务列表后重试': 'Refresh the task list and retry',
    '正在准备合并音视频并整理最终文件。': 'Preparing to merge audio and video and finalize the file.',
    '高分辨率或长视频可能需要一些时间，界面保持此状态属正常现象。': 'High-resolution or long videos may take a while; this state is normal.',
    '正在准备将完整音轨转码为 MP3 V0。': 'Preparing to transcode the complete audio track to MP3 V0.',
    '随后还会写入元数据与封面；长音频可能需要数十秒至数分钟。': 'Metadata and cover art will follow; long audio may take seconds to minutes.',
    '正在准备将完整音轨解码为 WAV。': 'Preparing to decode the complete audio track to WAV.',
    '正在准备提取 FLAC 音轨。': 'Preparing to extract the FLAC audio track.',
    '正在准备整理原始音轨。': 'Preparing to finalize the original audio track.',
    '随后还会写入元数据与封面；长音频或大文件可能需要一些时间。': 'Metadata and cover art will follow; long audio or large files may take a while.',
    '正在将完整音轨转码为 MP3 V0…': 'Transcoding the complete audio track to MP3 V0…',
    '长音频需要完整解码并重新编码，可能持续数十秒至数分钟。': 'Long audio needs full decoding and re-encoding, which may take seconds to minutes.',
    '正在将完整音轨解码为 WAV…': 'Decoding the complete audio track to WAV…',
    '长音频需要完整解码，期间没有下载进度属于正常现象。': 'Long audio needs full decoding; no download progress during this stage is normal.',
    '正在提取并整理音轨…': 'Extracting and finalizing the audio track…',
    '大文件需要读取并写入完整音轨，请耐心等待。': 'Large files require reading and writing the entire audio track. Please wait.',
    '正在嵌入封面…': 'Embedding cover art…', '程序正在把封面写入最终媒体文件。': 'Writing cover art to the final media file.',
    '正在写入媒体信息…': 'Writing media metadata…', '程序正在保存标题、作者和其他媒体标签。': 'Saving the title, author, and other media tags.',
    '正在合并视频与音频…': 'Merging video and audio…', '高分辨率或长视频需要读取并写入完整媒体流。': 'High-resolution or long videos require reading and writing the complete media streams.',
    '正在整理视频封装…': 'Remuxing the video…', '程序正在生成兼容性更好的最终视频文件。': 'Generating the final video file for improved compatibility.',
    '正在整理最终文件…': 'Finalizing files…', '处理即将完成，程序正在确认文件名与保存位置。': 'Almost done: confirming filenames and output locations.',
    '正在处理媒体文件…': 'Processing media…', '程序仍在正常工作，请保持窗口打开。': 'Processing is continuing normally. Keep this window open.',
  };
  function backendText(value) {
    return window.GtdLanguage?.language === 'en' ? (backendTranslations[value] || value) : value;
  }
  function refreshDownloadLanguage() {
    for (const [element, label] of localizedLabels) setLocalized(element, label.zh, label.en, label.params);
    if (taskHeading) setTaskHeading(taskHeading.type, taskHeading.format);
    renderDownloadDirectoryHistories();
    if (pendingPreview) {
      collectionPreviewTitle.textContent = pendingPreview.is_single ? tr('确认下载内容', 'Confirm downloads')
        : `${pendingPreview.title || tr('下载合集', 'Download collection')} · ${tr('选择条目', 'Select items')}`;
      renderCollectionEntries(pendingDownloadSettings?.mediaType);
      updateCollectionSelection();
    }
    if (pendingSkeletonCount !== null) renderPendingSkeleton(pendingSkeletonCount);
    else if (lastRenderedBatch) renderTasks(lastRenderedBatch);
  }
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
    setLocalized(control.downloadDirHint, "将保存到：{path}", "Save to: {path}", {path});
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
        empty.textContent = tr("暂无最近使用的位置", "No recently used folders");
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
      aria2Available
        ? setLocalized(control.turboHint, "已检测到 aria2c，可为 Bilibili 大文件启用多连接下载", "aria2c detected: multi-connection downloads available for large Bilibili files")
        : setLocalized(control.turboHint, "未安装 aria2c，当前使用标准模式", "aria2c is not installed; using standard mode");
      if (!aria2Available) control.turboToggle.checked = false;
      control.browseButton.disabled = !folderPickerAvailable || isDownloading;
      folderPickerAvailable
        ? setLocalized(control.downloadDirHint, "留空使用默认位置：{path}", "Leave blank for the default: {path}", {path: defaultDownloadDir})
        : setLocalized(control.downloadDirHint, "留空使用默认位置：{path}；当前环境请手动输入路径", "Leave blank for the default: {path}; enter a path manually in this environment", {path: defaultDownloadDir});
    });
  }

  async function chooseDownloadDirectory(mediaType) {
    if (isDownloading) return;
    const control = downloadControls[mediaType];
    if (!control || !folderPickerAvailable) return;
    control.browseButton.disabled = true;
    setLocalized(control.browseButton, "等待选择…", "Waiting for selection…");
    try {
      const response = await fetch("/api/select-directory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ initial_dir: control.downloadDirInput.value.trim() || null }),
      });
      const data = await response.json();
      if (!response.ok) {
        alert("❌ " + formatApiError(data, tr("无法打开文件夹选择器", "Unable to open the folder picker")));
        return;
      }
      if (!data.cancelled && data.download_dir) {
        control.downloadDirInput.value = data.download_dir;
        setLocalized(control.downloadDirHint, "将保存到：{path}", "Save to: {path}", {path: data.download_dir});
        setDownloadDirectoryHistoryExpanded(control, false);
      }
    } catch (error) {
      alert(tr("❌ 无法选择文件夹：", "❌ Unable to select a folder: ") + error.message);
    } finally {
      setLocalized(control.browseButton, "选择文件夹", "Choose folder");
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
      flac: tr("源 FLAC", "Source FLAC"),
      source: tr("原始音轨", "Original audio"),
      wav: "WAV PCM",
    }[audioFormat] || tr("音频", "Audio");
  }

  function formatApiError(data, fallback = tr("请求失败", "Request failed")) {
    if (!data || typeof data !== "object") return fallback;
    const code = data.error_code ? `[${data.error_code}] ` : "";
    const localized = localizedError(data);
    const message = localized.message || fallback;
    const suggestion = localized.suggestion ? `\n${tr("建议：", "Suggestion: ")}${localized.suggestion}` : "";
    return `${code}${message}${suggestion}`;
  }

  async function startDownload(mediaType) {
    if (isDownloading) return;
    const control = downloadControls[mediaType];
    if (!control) return;

    const raw = control.textarea.value.trim();
    if (!raw) {
      alert(tr("请先粘贴至少一个{type}链接。", "Paste at least one {type} URL first.", {type: mediaName(mediaType)}));
      return;
    }

    const urls = raw.split("\n").map(s => s.trim()).filter(Boolean);
    if (urls.length === 0) {
      alert(tr("未检测到有效的链接行。", "No valid URL lines found."));
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
    taskHeading = null;
    setLocalized(taskTitle, "正在解析输入", "Parsing input");
    setLocalized(taskSummary, "读取播放列表、合集与分 P 信息...", "Reading playlists, collections, and multipart videos...");
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
      alert(tr("❌ 网络错误：", "❌ Network error: ") + error.message);
      resetUI();
    }
  }

  function renderCollectionPreview(preview, mediaType) {
    const entries = Array.isArray(preview.entries) ? preview.entries : [];
    collectionPreviewTitle.textContent = preview.is_single
      ? tr("确认下载内容", "Confirm downloads")
      : `${preview.title || tr("下载合集", "Download collection")} · ${tr("选择条目", "Select items")}`;
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
            <span class="collection-entry-title">${escHtml(entry.title || tr("第 {n} 项", "Item {n}", {n: index + 1}))}</span>
            <span class="collection-entry-meta">${selectable ? tr("第 {n} 项 · {type}", "Item {n} · {type}", {n: entry.position || index + 1, type: mediaName(mediaType)}) : escHtml(backendText(entry.unavailable_reason) || tr("不可下载", "Unavailable"))}</span>
          </span>
        </label>`;
    }).join("");
    collectionLoadMoreButton.hidden = collectionRenderLimit >= entries.length;
    if (!collectionLoadMoreButton.hidden) {
      const remaining = entries.length - collectionRenderLimit;
      setLocalized(collectionLoadMoreButton, "显示更多条目（剩余 {n} 项）", "Show more ({n} remaining)", {n: remaining});
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
    collectionSelectAllLabel.textContent = selectableCount > 100 ? tr("选择前 100 项", "Select first 100") : tr("全选", "Select all");
    const truncationNote = pendingPreview && pendingPreview.truncated
      ? tr(" · 预览仅展示前 1000 项，请拆分链接后继续选择", " · Preview shows the first 1,000 items only. Split your links to select more.")
      : "";
    setLocalized(collectionPreviewCount, "已选择 {n} 项 · 最多选择 100 项{note}", "{n} selected · Up to 100 items{note}", {n: selected.length, note: truncationNote});
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
      alert(tr("请至少选择一个可下载条目。", "Select at least one available item."));
      return;
    }
    if (selected.length > 100) {
      alert(tr("一次最多选择 100 项。", "Select up to 100 items at a time."));
      return;
    }

    collectionSubmitButton.disabled = true;
    collectionPreview.hidden = true;
    setOperationalMetrics(0, selected.length);
    renderPendingSkeleton(selected.length);
    setTaskHeading(mediaType, pendingDownloadSettings.audioFormat);
    setLocalized(taskSummary, "正在提交...", "Submitting...");

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
      setLocalized(taskSummary, "共 {n} 个任务 · 保存到 {path}", "{n} tasks · Save to {path}", {n: data.task_count, path: data.download_dir || defaultDownloadDir});
      startPolling();
    } catch (error) {
      alert(tr("❌ 网络错误：", "❌ Network error: ") + error.message);
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

      setTaskHeading(batch.media_type, batch.audio_format);
      setLocalized(taskSummary, "共 {total} 个 · 完成 {completed} · 失败 {failed} · 取消 {cancelled} · 批次 {id}", "{total} total · {completed} completed · {failed} failed · {cancelled} cancelled · Batch {id}", {...batch, cancelled: batch.cancelled || 0});
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
    pendingSkeletonCount = count;
    let html = '<ul class="task-list">';
    for (let i = 0; i < count; i++) {
      html += `
        <li class="task-item task-item-enter status-queued">
          <span class="task-index">${String(i + 1).padStart(2, "0")}</span>
          <div class="task-body"><div class="task-meta">${tr("等待可用下载槽位", "Waiting for an available download slot")}</div></div>
          <span class="badge badge-queued">${tr("等待中", "Queued")}</span>
        </li>`;
    }
    html += "</ul>";
    taskContainer.innerHTML = html;
  }

  function formatAttemptTime(value) {
    const milliseconds = Number(value) * 1000;
    if (!Number.isFinite(milliseconds) || milliseconds <= 0) return tr("未结束", "Not finished");
    return new Date(milliseconds).toLocaleString(window.GtdLanguage?.language === "en" ? "en-US" : "zh-CN", { hour12: false });
  }

  function renderTasks(batch) {
    lastRenderedBatch = batch;
    pendingSkeletonCount = null;
    let html = '<ul class="task-list">';
    batch.tasks.forEach((t, i) => {
      const cls = "status-" + t.status;
      const badgeMap = {
        queued: [tr("等待中", "Queued"), "badge-queued"],
        running: [tr("下载中", "Downloading"), "badge-running"],
        running_uninterruptible: [tr("极速下载", "Turbo download"), "badge-running"],
        completed: [tr("下载完成", "Completed"), "badge-completed"],
        failed: [tr("下载失败", "Failed"), "badge-failed"],
        cancelled: [tr("已取消", "Cancelled"), "badge-cancelled"],
      };
      const [label, badgeCls] = badgeMap[t.status] || [tr("未知", "Unknown"), ""];

      html += `<li class="task-item ${cls}">`;
      html += `<span class="task-index">${String(i + 1).padStart(2, "0")}</span>`;
      html += `<div class="task-body">`;
      html += `<div class="task-url">${escHtml(t.url)}</div>`;

      if (t.status === "completed" && t.result) {
        const r = t.result;
        html += `<div class="task-meta">`;
        html += `<strong>${escHtml(r.title || tr("未知", "Unknown"))}</strong><br>`;
        if (batch.media_type === "audio") {
          html += `${tr("格式: ", "Format: ")}${escHtml(r.format || "MP3")} · `;
          html += `${tr("音频编码: ", "Audio codec: ")}${escHtml(r.acodec || "mp3")} · `;
          if (r.source_acodec && r.source_acodec !== "未知") {
            html += `${tr("源编码: ", "Source codec: ")}${escHtml(r.source_acodec)}`;
            if (r.source_abr_kbps && r.source_abr_kbps !== "未知") {
              html += ` ${escHtml(r.source_abr_kbps)} kbps`;
            }
            html += ` · `;
          }
        } else {
          html += `${tr("分辨率: ", "Resolution: ")}${escHtml(backendText(r.resolution) || "?")} · `;
        }
        html += `${tr("大小: ", "Size: ")}${escHtml(backendText(r.filesize) || "?")}`;
        if (batch.media_type === "audio" && r.audio_format_fallback) {
          html += `<br>${tr("源站未提供 FLAC，已自动回退至 MP3 V0", "The source has no FLAC audio; automatically fell back to MP3 V0")}`;
        }
        if (r.filepath) html += `<br>${tr("保存路径: ", "Saved to: ")}${escHtml(r.filepath)}`;
        html += `</div>`;
      } else if (["running", "running_uninterruptible"].includes(t.status)) {
        if (t.postprocessing) {
          html += `<div class="task-meta"><span class="spinner"></span> ${escHtml(backendText(t.postprocessing.stage_text) || tr("正在处理媒体文件…", "Processing media…"))}</div>`;
          if (t.postprocessing.detail_text) {
            html += `<div class="task-meta">${escHtml(backendText(t.postprocessing.detail_text))}</div>`;
          }
        } else if (t.speed_mode_used === "turbo" && !t.turbo_fallback) {
          html += `<div class="task-meta"><span class="spinner"></span> ${tr("高速下载中", "Downloading in turbo mode")}</div>`;
        } else {
          if (t.turbo_fallback) {
            html += `<div class="task-meta">${tr("极速模式不可用，已切换标准模式", "Turbo mode unavailable; switched to standard mode")}</div>`;
          }
          html += `<div class="task-meta"><span class="spinner"></span> ${tr("正在下载，请稍候…", "Downloading, please wait…")}</div>`;
          html += renderDownloadProgress(t.progress);
        }
        if (t.status === "running_uninterruptible") {
          html += `<div class="task-meta">${tr("aria2c 极速任务不可取消，将继续下载直至完成", "aria2c turbo tasks cannot be cancelled and will run until complete")}</div>`;
        }
      } else if (t.status === "queued") {
        html += `<div class="task-meta">${tr("等待可用下载槽位", "Waiting for an available download slot")}</div>`;
      } else if (t.status === "failed") {
        html += `<div class="task-meta">${tr("下载失败", "Failed")}</div>`;
        if (t.error) {
          const errorText = localizedError(t.error);
          html += `<div class="task-error"><span class="task-error-code">${escHtml(t.error.error_code || "DOWNLOAD_FAILED")}</span> · ${escHtml(errorText.message || tr("下载失败", "Failed"))}`;
          if (errorText.suggestion) html += `<br>${tr("建议：", "Suggestion: ")}${escHtml(errorText.suggestion)}`;
          html += `</div>`;
        }
      } else if (t.status === "cancelled") {
        html += `<div class="task-meta">${tr("任务已取消，已完成文件仍然保留。", "Task cancelled. Completed files are kept.")}</div>`;
      }

      if (t.attempt_count > 0 && Array.isArray(t.attempts)) {
        html += `<details class="task-attempts"><summary>${tr("尝试记录 ", "Attempts ")}${t.attempt_count}</summary><div class="task-attempts-list">`;
        t.attempts.forEach(attempt => {
          const started = formatAttemptTime(attempt.started_at);
          const finished = formatAttemptTime(attempt.finished_at);
          html += `<span class="task-attempt">#${attempt.number} · ${escHtml(statusLabel(attempt.status))}${attempt.output_version > 1 ? `${tr(" · 版本 ", " · Version ")}${attempt.output_version}` : ""}${tr(" · 开始 ", " · Started ")}${escHtml(started)}${tr(" · 结束 ", " · Finished ")}${escHtml(finished)}</span>`;
        });
        html += `</div></details>`;
      }

      html += `<div class="task-actions">`;
      if (t.can_cancel) html += `<button class="task-action" onclick="operateTask('cancel', '${escHtml(t.id)}')">${tr("取消", "Cancel")}</button>`;
      if (t.can_retry) html += `<button class="task-action" onclick="operateTask('retry', '${escHtml(t.id)}')">${tr("重试", "Retry")}</button>`;
      if (t.can_redownload) html += `<button class="task-action" onclick="operateTask('redownload', '${escHtml(t.id)}')">${tr("重新下载", "Redownload")}</button>`;
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
      alert(tr("❌ 网络错误：", "❌ Network error: ") + error.message);
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
      alert(tr("❌ 网络错误：", "❌ Network error: ") + error.message);
    }
  }

  function renderDownloadProgress(progress) {
    const speed = progress && progress.speed_text ? backendText(progress.speed_text) : tr("计算中", "Calculating");
    const eta = progress && progress.eta_text ? backendText(progress.eta_text) : tr("计算中", "Calculating");
    const percent = progress && progress.percent_text ? progress.percent_text : "";
    const totalSize = progress && progress.total_size_text ? backendText(progress.total_size_text) : tr("计算中", "Calculating");
    const totalSizeLabel = progress && progress.total_size_is_estimate ? tr("预计总大小", "Estimated total size") : tr("总大小", "Total size");

    let html = `<div class="task-progress">`;
    html += `<span class="task-progress-item"><span class="task-progress-label">${tr("下载速度", "Download speed")}</span><span class="task-progress-value">${escHtml(speed)}</span></span>`;
    html += `<span class="task-progress-item"><span class="task-progress-label">${tr("预计剩余", "Time remaining")}</span><span class="task-progress-value">${escHtml(eta)}</span></span>`;
    html += `<span class="task-progress-item"><span class="task-progress-label">${escHtml(totalSizeLabel)}</span><span class="task-progress-value">${escHtml(totalSize)}</span></span>`;
    if (percent && percent !== "计算中") {
      html += `<span class="task-progress-item"><span class="task-progress-label">${tr("进度", "Progress")}</span><span class="task-progress-value">${escHtml(percent)}</span></span>`;
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
  document.addEventListener("gtd:languagechange", refreshDownloadLanguage);
  initializeDownloadDirectoryHistory();
  loadCapabilities();
