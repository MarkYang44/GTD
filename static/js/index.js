  // Only app-owned text is localized; media metadata and diagnostic details stay intact.
  // Each entry re-renders one element's text after a language switch.
  const localizedLabels = new Map();
  let lastRenderedBatch = null;
  let pendingSkeletonCount = null;
  function subtitleWarningText(code) {
    const labels = {
      manual: tr('字幕', 'Subtitles'), automatic: tr('自动字幕', 'Automatic captions'), danmaku: tr('弹幕', 'Danmaku'),
      subtitle_metadata: tr('字幕列表', 'Subtitle list'), subtitle_embedding: tr('字幕封装', 'Subtitle embedding'), mkv_remux: tr('MKV 封装', 'MKV remux'),
    };
    const parts = code.split(':');
    if (!labels[parts[0]]) return backendText(code);
    const detail = parts.length > 2 ? ` (${parts[1]})` : '';
    return labels[parts[0]] + detail + (parts.at(-1) === 'failed'
      ? tr('失败，已保留视频。', ' failed; video retained.')
      : tr('未获取到可用内容，请检查源站及登录权限。', ' unavailable; check the source and login permissions.'));
  }

  function tr(zh, en, params = {}) {
    if (window.GtdLanguage) return window.GtdLanguage.t(zh, en, params);
    return zh.replace(/\{(\w+)\}/g, (_, key) => params[key] ?? `{${key}}`);
  }
  function setLocalizedText(element, render) {
    localizedLabels.set(element, render);
    element.textContent = render();
  }
  function setLocalized(element, zh, en, params = {}) {
    setLocalizedText(element, () => tr(zh, en, params));
  }
  // Inline messages replace blocking dialogs; `kind` lets the page clear one reason without another.
  function showNotice(element, render, {tone = "error", kind = ""} = {}) {
    if (!element) return;
    element.dataset.tone = tone;
    element.dataset.kind = kind;
    setLocalizedText(element, render);
    element.hidden = false;
  }
  function clearNotice(element, kind = null) {
    if (!element || (kind !== null && element.dataset.kind !== kind)) return;
    localizedLabels.delete(element);
    element.textContent = "";
    element.dataset.kind = "";
    element.hidden = true;
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
    INTERRUPTED: ['服务重启导致任务中断', 'The task was interrupted by a server restart', '请手动重试', 'Retry this task manually'],
    CANCELLED: ['任务已取消', 'Task cancelled', '可以点击重试重新加入队列', 'Click Retry to rejoin the queue'],
    NETWORK_TIMEOUT: ['网络连接源站超时', 'The connection to the source timed out', '请检查本机网络连接及源站可达性后重试', 'Check your internet connection and source availability, then retry'],
    NETWORK_CONNECTION_RESET: ['媒体传输连接被远端中断', 'The remote server interrupted the media transfer', '程序会尝试备用线路；如仍失败，请检查本机网络连接及源站可达性后重试', 'The app will try an alternate connection. If it fails again, check your internet connection and source availability, then retry'],
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
    "正在获取并封装字幕…": "Fetching and embedding subtitles…",
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
    for (const [element, render] of localizedLabels) element.textContent = render();
    if (taskHeading) setTaskHeading(taskHeading.type, taskHeading.format);
    renderDownloadDirectoryHistories();
    renderBatchHistory();
    if (pendingPreview) {
      collectionPreviewTitle.textContent = previewHeading(pendingPreview);
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
      urlCount: document.getElementById("videoUrlCount"),
      notice: document.getElementById("videoNotice"),
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
      urlCount: document.getElementById("audioUrlCount"),
      notice: document.getElementById("audioNotice"),
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
  const taskCard = document.getElementById("task-card");
  const taskTitle = document.getElementById("task-title");
  const taskSummary = document.getElementById("task-summary");
  const taskNotice = document.getElementById("taskNotice");
  const taskContainer = document.getElementById("task-container");
  const emptyStateMarkup = taskContainer.innerHTML;
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
  const collectionNotice = document.getElementById("collectionNotice");
  const retryFailedButton = document.getElementById("retryFailedButton");
  const URL_PASTE_LINE_LIMIT = 20;
  const COLLECTION_PAGE_SIZE = 50;
  const DOWNLOAD_DIRECTORY_HISTORY_KEY = "multiple-video-downloader.download-directory-history.v1";
  const DOWNLOAD_DIRECTORY_HISTORY_LIMIT = 3;
  const VISIBLE_POLL_INTERVAL_MS = 800;
  const HIDDEN_POLL_INTERVAL_MS = 3000;

  const CURRENT_BATCH_KEY = "gtd_current_batch_v1";
  const batchHistory = document.getElementById("batchHistory");
  let historyBatches = [];
  let historyLoading = false;
  let pollFailureCount = 0;
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

  function countUrlLines(value) {
    return value.split("\n").map(line => line.trim()).filter(Boolean).length;
  }

  // The counter makes the paste limit visible before it is reached.
  function updateUrlCount(mediaType) {
    const control = downloadControls[mediaType];
    const count = countUrlLines(control.textarea.value);
    control.urlCount.hidden = count === 0;
    setLocalized(control.urlCount, "{n} / {limit} 行", "{n} / {limit} lines", {n: count, limit: URL_PASTE_LINE_LIMIT});
    control.urlCount.classList[count >= URL_PASTE_LINE_LIMIT ? "add" : "remove"]("is-full");
    control.clearButton.disabled = isDownloading || count === 0;
    if (count > 0) clearNotice(control.notice, "empty");
    if (count < URL_PASTE_LINE_LIMIT) clearNotice(control.notice, "limit");
  }

  function clearInput(mediaType) {
    if (isDownloading) return;
    const control = downloadControls[mediaType];
    control.textarea.value = "";
    updateUrlCount(mediaType);
    clearNotice(control.notice);
    control.textarea.focus();
  }

  function handleUrlPaste(mediaType, event) {
    const control = downloadControls[mediaType];
    const textarea = control.textarea;
    const pastedText = event.clipboardData && event.clipboardData.getData("text");
    if (!pastedText) return;
    const start = textarea.selectionStart ?? textarea.value.length;
    const end = textarea.selectionEnd ?? start;
    const nextValue = textarea.value.slice(0, start) + pastedText + textarea.value.slice(end);
    const lineCount = countUrlLines(nextValue);
    if (lineCount < URL_PASTE_LINE_LIMIT) return;
    if (lineCount > URL_PASTE_LINE_LIMIT) {
      event.preventDefault();
      showNotice(control.notice, () => tr(
        "粘贴内容会超过 20 行上限，未添加。",
        "That paste would go past the 20-line limit, so it wasn't added.",
      ), {kind: "limit"});
      return;
    }
    showNotice(control.notice, () => tr(
      "已达到 20 行上限，更多链接请分批提交。",
      "You've reached the 20-line limit. Submit more links in another batch.",
    ), {tone: "info", kind: "limit"});
  }

  function handleUrlKeydown(mediaType, event) {
    if (event.key !== "Enter" || !(event.metaKey || event.ctrlKey) || event.isComposing) return;
    event.preventDefault();
    startDownload(mediaType);
  }

  function initializeUrlInputs() {
    Object.entries(downloadControls).forEach(([mediaType, control]) => {
      control.textarea.addEventListener("paste", event => handleUrlPaste(mediaType, event));
      control.textarea.addEventListener("input", () => updateUrlCount(mediaType));
      control.textarea.addEventListener("keydown", event => handleUrlKeydown(mediaType, event));
      updateUrlCount(mediaType);
    });
  }

  const videoSubtitlesToggle = document.getElementById("videoSubtitlesToggle");
  const videoAutomaticCaptionsToggle = document.getElementById("videoAutomaticCaptionsToggle");
  const videoDanmakuToggle = document.getElementById("videoDanmakuToggle");
  videoSubtitlesToggle.addEventListener("change", () => {
    if (!videoSubtitlesToggle.checked) videoAutomaticCaptionsToggle.checked = false;
    videoAutomaticCaptionsToggle.disabled = isDownloading || !videoSubtitlesToggle.checked;
  });

  function setControlsDisabled(disabled) {
    videoSubtitlesToggle.disabled = disabled;
    videoDanmakuToggle.disabled = disabled;
    videoAutomaticCaptionsToggle.disabled = disabled || !videoSubtitlesToggle.checked;
    if (batchHistory) batchHistory.disabled = disabled;
    Object.values(downloadControls).forEach(control => {
      control.textarea.disabled = disabled;
      control.downloadButton.disabled = disabled;
      control.clearButton.disabled = disabled || countUrlLines(control.textarea.value) === 0;
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

  // Long default folders keep their last two segments, which is the part people recognize.
  function shortenPath(path) {
    const value = String(path || "");
    if (value.length <= 32) return value;
    const separator = value.includes("\\") && !value.includes("/") ? "\\" : "/";
    const parts = value.split(/[\\/]+/).filter(Boolean);
    return parts.length > 2 ? `…${separator}${parts.slice(-2).join(separator)}` : value;
  }

  function showDefaultDownloadDir(control) {
    const path = shortenPath(defaultDownloadDir);
    const input = control.downloadDirInput;
    input.setAttribute("data-i18n-placeholder-zh", `默认：${path}`);
    input.setAttribute("data-i18n-placeholder-en", `Default: ${path}`);
    input.placeholder = window.GtdLanguage?.language === "en" ? `Default: ${path}` : `默认：${path}`;
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
        ? setLocalized(control.turboHint, "已检测到 aria2c，大文件可多连接下载", "aria2c found: large files can use multiple connections")
        : setLocalized(control.turboHint, "未安装 aria2c，使用标准模式", "aria2c isn't installed, so standard mode is used");
      if (!aria2Available) control.turboToggle.checked = false;
      control.browseButton.disabled = !folderPickerAvailable || isDownloading;
      showDefaultDownloadDir(control);
      if (folderPickerAvailable) clearNotice(control.downloadDirHint);
      else showNotice(control.downloadDirHint, () => tr(
        "此处无法打开文件夹选择器，请直接输入路径；留空使用默认位置。",
        "The folder picker isn't available here. Type a path, or leave it blank for the default.",
      ), {tone: "info"});
    });
  }

  async function chooseDownloadDirectory(mediaType) {
    if (isDownloading) return;
    const control = downloadControls[mediaType];
    if (!control || !folderPickerAvailable) return;
    control.browseButton.disabled = true;
    setLocalized(control.browseButton, "等待选择…", "Waiting for selection…");
    clearNotice(control.notice);
    try {
      const response = await fetch("/api/select-directory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ initial_dir: control.downloadDirInput.value.trim() || null }),
      });
      const data = await response.json();
      if (!response.ok) {
        showNotice(control.notice, () => formatApiError(data, tr("无法打开文件夹选择器", "Unable to open the folder picker")));
        return;
      }
      if (!data.cancelled && data.download_dir) {
        control.downloadDirInput.value = data.download_dir;
        setDownloadDirectoryHistoryExpanded(control, false);
      }
    } catch (error) {
      showNotice(control.notice, () => tr("无法选择文件夹：", "Unable to select a folder: ") + error.message);
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

  function scrollToElement(element, block) {
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    element.scrollIntoView?.({ behavior: reduced ? "auto" : "smooth", block });
  }

  async function startDownload(mediaType) {
    if (isDownloading) return;
    const control = downloadControls[mediaType];
    if (!control) return;
    clearNotice(control.notice);

    const urls = control.textarea.value.split("\n").map(s => s.trim()).filter(Boolean);
    if (urls.length === 0) {
      showNotice(control.notice, mediaType === "audio"
        ? () => tr("请先粘贴至少一个音频链接。", "Paste at least one audio link first.")
        : () => tr("请先粘贴至少一个视频链接。", "Paste at least one video link first."),
      {tone: "info", kind: "empty"});
      control.textarea.focus();
      return;
    }

    const speedMode = control.turboToggle.checked ? "turbo" : "standard";
    const audioFormat = mediaType === "audio"
      ? document.querySelector('input[name="audioFormat"]:checked').value
      : "mp3";

    pendingDownloadSettings = {
      mediaType,
      subtitleOptions: mediaType === "video" ? {
        subtitles: videoSubtitlesToggle.checked,
        automatic: videoSubtitlesToggle.checked && videoAutomaticCaptionsToggle.checked,
        danmaku: videoDanmakuToggle.checked,
      } : null,
      speedMode,
      audioFormat,
      downloadDir: control.downloadDirInput.value.trim(),
    };
    isDownloading = true;
    setControlsDisabled(true);
    clearNotice(taskNotice);
    taskHeading = null;
    setLocalized(taskTitle, "正在解析输入", "Parsing input");
    setLocalized(taskSummary, "读取播放列表、合集与分 P 信息...", "Reading playlists, collections, and multipart videos...");
    await previewInput(mediaType, urls);
  }

  async function previewInput(mediaType, inputs) {
    const control = downloadControls[mediaType];
    try {
      const response = await fetch("/api/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ inputs }),
      });
      const preview = await response.json();
      if (!response.ok) {
        resetUI();
        showNotice(control.notice, () => formatApiError(preview));
        return;
      }
      pendingPreview = preview;
      renderCollectionPreview(preview, mediaType);
      if (!preview.requires_selection) await submitPreview(mediaType);
    } catch (error) {
      resetUI();
      showNotice(control.notice, () => tr("网络错误：", "Network error: ") + error.message);
    }
  }

  function previewHeading(preview) {
    if (preview.is_single) return tr("确认下载内容", "Confirm downloads");
    const title = !preview.title_is_generated && preview.title ? preview.title
      : tr("下载预览（{n} 项）", "Download preview ({n} items)", {n: preview.entries?.length || 0});
    return `${title} · ${tr("选择条目", "Select items")}`;
  }

  function renderCollectionPreview(preview, mediaType) {
    const entries = Array.isArray(preview.entries) ? preview.entries : [];
    collectionPreviewTitle.textContent = previewHeading(preview);
    collectionRenderLimit = COLLECTION_PAGE_SIZE;
    collectionSelectedIds = new Set(
      entries.filter(entry => entry.selectable === true).slice(0, 100).map(entry => entry.id)
    );
    renderCollectionEntries(mediaType);
    clearNotice(collectionNotice);
    collectionPreview.hidden = false;
    updateCollectionSelection();
    if (preview.requires_selection) {
      // Parsing is done; the page is now waiting for a choice, not working.
      taskHeading = null;
      setLocalized(taskTitle, "等待选择条目", "Choose items to download");
      setLocalized(taskSummary, "勾选上方条目，然后点击“下载所选条目”。", "Pick items above, then select Download selected items.");
      scrollToElement(collectionPreview, "center");
    }
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
            <span class="collection-entry-title">${escHtml(!entry.title_is_generated && entry.title ? entry.title : tr("第 {n} 项", "Item {n}", {n: entry.position || index + 1}))}</span>
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
    if (selected.length > 0) clearNotice(collectionNotice);
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
    clearNotice(collectionNotice);
    if (selected.length === 0) {
      showNotice(collectionNotice, () => tr("请至少选择一个可下载条目。", "Select at least one available item."), {tone: "info"});
      return;
    }
    if (selected.length > 100) {
      showNotice(collectionNotice, () => tr("一次最多选择 100 项。", "Select up to 100 items at a time."), {tone: "info"});
      return;
    }

    collectionSubmitButton.disabled = true;
    collectionPreview.hidden = true;
    setOperationalMetrics(0, selected.length);
    renderPendingSkeleton(selected.length);
    setTaskHeading(mediaType, pendingDownloadSettings.audioFormat);
    setLocalized(taskSummary, "正在提交...", "Submitting...");
    scrollToElement(taskCard, "start");

    const payload = {
      preview_id: pendingPreview.preview_id,
      selected_entry_ids: selected,
      media_type: mediaType,
      speed_mode: pendingDownloadSettings.speedMode,
      audio_format: pendingDownloadSettings.audioFormat,
      download_dir: pendingDownloadSettings.downloadDir || null,
    };
    if (pendingDownloadSettings.subtitleOptions && Object.values(pendingDownloadSettings.subtitleOptions).some(Boolean)) {
      payload.subtitle_options = pendingDownloadSettings.subtitleOptions;
    }
    try {
      const response = await fetch("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        restoreTaskPanel();
        collectionPreview.hidden = false;
        collectionSubmitButton.disabled = false;
        showNotice(collectionNotice, () => formatApiError(data));
        return;
      }
      rememberDownloadDirectory(data.download_dir);
      currentBatchId = data.batch_id;
      rememberCurrentBatch(currentBatchId);
      pendingPreview = null;
      pendingDownloadSettings = null;
      // The links now live in the task list, so the box is ready for the next batch.
      downloadControls[mediaType].textarea.value = "";
      updateUrlCount(mediaType);
      setLocalized(taskSummary, "共 {n} 个任务 · 保存到 {path}", "{n} tasks · Save to {path}", {n: data.task_count, path: data.download_dir || defaultDownloadDir});
      startPolling();
    } catch (error) {
      restoreTaskPanel();
      collectionPreview.hidden = false;
      collectionSubmitButton.disabled = false;
      showNotice(collectionNotice, () => tr("网络错误：", "Network error: ") + error.message);
    }
  }

  function startPolling() {
    stopPolling();
    pollingActive = true;
    pollFailureCount = 0;
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
      title: task.title,
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

  function setBatchSummary(batch) {
    setLocalized(
      taskSummary,
      "共 {total} 个 · 完成 {completed} · 失败 {failed} · 取消 {cancelled}",
      "{total} total · {completed} completed · {failed} failed · {cancelled} cancelled",
      {
        total: batch.total ?? (Array.isArray(batch.tasks) ? batch.tasks.length : 0),
        completed: batch.completed || 0,
        failed: batch.failed || 0,
        cancelled: batch.cancelled || 0,
      },
    );
  }

  async function pollStatus() {
    if (!pollingActive || !currentBatchId || pollInFlight) return;
    const requestedBatchId = currentBatchId;
    pollInFlight = true;
    try {
      const resp = await fetchJsonWithTimeout("/api/batch/" + requestedBatchId);
      if (currentBatchId !== requestedBatchId) return;
      if (resp.status === 404 || resp.status === 410) {
        stopPolling();
        currentBatchId = null;
        rememberCurrentBatch(null);
        isDownloading = false;
        setControlsDisabled(false);
        setOperationalMetrics(0, 0);
        pendingSkeletonCount = null;
        lastRenderedBatch = null;
        lastTaskRenderSignature = null;
        retryFailedButton.hidden = true;
        taskHeading = null;
        setLocalized(taskTitle, "下载任务", "Download tasks");
        setLocalized(taskSummary, "任务不存在或已过期，请重新提交或选择历史记录。", "This batch is missing or expired. Submit again or select a saved batch.");
        taskContainer.innerHTML = '<div class="empty-state"><p><span data-guide-copy="zh">原任务已无法查询，已下载文件不会被删除。</span><span data-guide-copy="en">This batch is no longer available. Downloaded files are kept.</span></p></div>';
        return;
      }
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const batch = resp.data;
      if (currentBatchId !== requestedBatchId) return;
      pollFailureCount = 0;
      updateOperationalMetrics(batch);
      const renderSignature = taskRenderSignature(batch);
      if (renderSignature !== lastTaskRenderSignature) {
        renderTasks(batch);
        lastTaskRenderSignature = renderSignature;
      }

      setTaskHeading(batch.media_type, batch.audio_format);
      setBatchSummary(batch);
      retryFailedButton.hidden = !batch.tasks.some(task => task.can_retry && task.status === "failed");

      if (batch.all_done) {
        stopPolling();
        isDownloading = false;
        setControlsDisabled(false);
      }
    } catch (_) {
      if (currentBatchId !== requestedBatchId) return;
      pollFailureCount = Math.min(pollFailureCount + 1, 6);
      setLocalized(taskSummary, "连接暂不可用，正在自动重试…", "Connection unavailable. Retrying automatically…");
    } finally {
      pollInFlight = false;
      const normalDelay = document.hidden ? HIDDEN_POLL_INTERVAL_MS : VISIBLE_POLL_INTERVAL_MS;
      scheduleNextPoll(window.GtdTaskApi.backoffDelay(normalDelay, pollFailureCount));
    }
  }

  function renderPendingSkeleton(count) {
    pendingSkeletonCount = count;
    let html = '<ul class="task-list">';
    for (let i = 0; i < count; i++) {
      html += `
        <li class="task-item task-item-enter status-queued">
          <span class="task-index">${String(i + 1).padStart(2, "0")}</span>
          <div class="task-body"><div class="task-heading"><span class="task-name">${tr("等待可用下载槽位", "Waiting for an available download slot")}</span><span class="badge badge-queued">${tr("等待中", "Queued")}</span></div></div>
        </li>`;
    }
    html += "</ul>";
    taskContainer.innerHTML = html;
  }

  // Put the panel back to the last real state after a submission that never started.
  function restoreTaskPanel() {
    pendingSkeletonCount = null;
    if (lastRenderedBatch) {
      renderTasks(lastRenderedBatch);
      updateOperationalMetrics(lastRenderedBatch);
    } else {
      taskContainer.innerHTML = emptyStateMarkup;
      setOperationalMetrics(0, 0);
    }
    restoreTaskPanelHeading();
  }

  function restoreTaskPanelHeading() {
    if (lastRenderedBatch) {
      setTaskHeading(lastRenderedBatch.media_type, lastRenderedBatch.audio_format);
      setBatchSummary(lastRenderedBatch);
      return;
    }
    taskHeading = null;
    setLocalized(taskTitle, "下载任务", "Download tasks");
    setLocalized(taskSummary, "等待链接输入", "Waiting for links");
  }

  function formatAttemptTime(value) {
    const milliseconds = Number(value) * 1000;
    if (!Number.isFinite(milliseconds) || milliseconds <= 0) return tr("未结束", "Not finished");
    return new Date(milliseconds).toLocaleString(window.GtdLanguage?.language === "en" ? "en-US" : "zh-CN", { hour12: false });
  }

  // The media title is what people recognize; generated placeholders follow the page language.
  function taskDisplayTitle(task) {
    const resultTitle = task.status === "completed" && task.result && task.result.title;
    if (resultTitle) return String(resultTitle);
    const title = typeof task.title === "string" ? task.title.trim() : "";
    const generated = /^第 (\d+) 项$/.exec(title);
    if (generated) return tr("第 {n} 项", "Item {n}", {n: generated[1]});
    if (title) return title;
    return task.platform === "local" ? tr("本地视频", "Local video") : "";
  }

  function progressPercent(progress) {
    const value = Number.parseFloat(progress && progress.percent_text);
    return Number.isFinite(value) ? Math.min(100, Math.max(0, value)) : null;
  }

  function renderProgressBar(percent, label) {
    return `<div class="task-progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent}" aria-label="${escHtml(label)}"><span style="width: ${percent}%"></span></div>`;
  }

  function renderTask(batch, t, i, openAttempts) {
    const running = ["running", "running_uninterruptible"].includes(t.status);
    const badgeMap = {
      queued: [tr("等待中", "Queued"), "badge-queued"],
      running: [tr("下载中", "Downloading"), "badge-running"],
      running_uninterruptible: [tr("极速下载", "Turbo download"), "badge-running"],
      completed: [tr("下载完成", "Completed"), "badge-completed"],
      failed: [tr("下载失败", "Failed"), "badge-failed"],
      cancelled: [tr("已取消", "Cancelled"), "badge-cancelled"],
    };
    let [label, badgeCls] = badgeMap[t.status] || [tr("未知", "Unknown"), ""];
    if (t.platform === 'local' && t.status === 'running') label = tr('提取中', 'Extracting');
    else if (running && t.postprocessing) label = tr("处理中", "Processing");
    const name = taskDisplayTitle(t);
    const url = t.platform === "local" ? "" : (t.url || "");
    const r = t.result || {};
    let html = `<li class="task-item status-${escHtml(t.status)}">`;
    html += `<span class="task-index">${String(i + 1).padStart(2, "0")}</span>`;
    html += `<div class="task-body">`;
    html += `<div class="task-heading"><span class="task-name">${escHtml(name || url || tr("未知", "Unknown"))}</span>`;
    html += `<span class="badge ${badgeCls}">${running ? '<span class="spinner" aria-hidden="true"></span>' : ""}${label}</span></div>`;
    if (name && url) html += `<div class="task-url" title="${escHtml(url)}">${escHtml(url)}</div>`;

    if (t.status === "completed" && t.result) {
      const facts = [];
      if (batch.media_type === "audio") {
        facts.push(`${tr("格式: ", "Format: ")}${escHtml(r.format || "MP3")}`);
        facts.push(`${tr("音频编码: ", "Audio codec: ")}${escHtml(r.acodec || "mp3")}`);
        if (r.source_acodec && r.source_acodec !== "未知") {
          const bitrate = r.source_abr_kbps && r.source_abr_kbps !== "未知" ? ` ${escHtml(r.source_abr_kbps)} kbps` : "";
          facts.push(`${tr("源编码: ", "Source codec: ")}${escHtml(r.source_acodec)}${bitrate}`);
        }
      } else {
        facts.push(`${tr("分辨率: ", "Resolution: ")}${escHtml(backendText(r.resolution) || "?")}`);
      }
      facts.push(`${tr("大小: ", "Size: ")}${escHtml(backendText(r.filesize) || "?")}`);
      html += `<div class="task-meta">${facts.join(" · ")}</div>`;
      if (batch.media_type === "audio" && r.audio_format_fallback) {
        html += `<div class="task-meta">${tr("源站未提供 FLAC，已自动回退至 MP3 V0", "The source has no FLAC audio; automatically fell back to MP3 V0")}</div>`;
      }
      const subtitleStatus = {
        embedded: tr("已嵌入可切换字幕轨道", "Switchable subtitle tracks embedded"),
        partial: tr("仅嵌入部分字幕轨道", "Some subtitle tracks embedded"),
        unavailable: tr("未获取到可嵌入的字幕轨道", "No subtitle tracks available to embed"),
      }[r.subtitle_status];
      if (subtitleStatus) html += `<div class="task-meta">${escHtml(subtitleStatus)}</div>`;
      if (Array.isArray(r.subtitle_warnings)) {
        r.subtitle_warnings.forEach(warning => {
          html += `<div class="task-meta">${tr("字幕提示: ", "Subtitle note: ")}${escHtml(subtitleWarningText(String(warning)))}</div>`;
        });
      }
      if (r.filepath) html += `<div class="task-path"><span>${tr("保存路径", "Saved to")}</span><span class="task-path-value">${escHtml(r.filepath)}</span></div>`;
    } else if (running) {
      if (t.postprocessing) {
        html += `<div class="task-meta">${escHtml(backendText(t.postprocessing.stage_text) || tr("正在处理媒体文件…", "Processing media…"))}</div>`;
        if (t.postprocessing.detail_text) {
          html += `<div class="task-meta">${escHtml(backendText(t.postprocessing.detail_text))}</div>`;
        }
      } else if (t.platform === "local") {
        const percent = progressPercent(t.progress);
        if (percent !== null) html += renderProgressBar(percent, tr("音频处理进度", "Audio processing progress"));
      } else if (t.speed_mode_used === "turbo" && !t.turbo_fallback) {
        html += `<div class="task-meta">${tr("高速下载中", "Downloading in turbo mode")}</div>`;
      } else {
        if (t.turbo_fallback) {
          html += `<div class="task-meta">${tr("极速模式不可用，已切换标准模式", "Turbo mode unavailable; switched to standard mode")}</div>`;
        }
        html += renderDownloadProgress(t.progress);
      }
      if (t.status === "running_uninterruptible") {
        html += `<div class="task-meta">${tr("aria2c 极速任务不可取消，将继续下载直至完成", "aria2c turbo tasks cannot be cancelled and will run until complete")}</div>`;
      }
    } else if (t.status === "queued") {
      html += `<div class="task-meta">${tr("等待可用下载槽位", "Waiting for an available download slot")}</div>`;
    } else if (t.status === "failed" && t.error) {
      const errorText = localizedError(t.error);
      html += `<div class="task-error"><span>${escHtml(errorText.message || tr("下载失败", "Failed"))}</span>`;
      if (errorText.suggestion) html += `<span>${tr("建议：", "Suggestion: ")}${escHtml(errorText.suggestion)}</span>`;
      html += `<span class="task-error-code">${escHtml(t.error.error_code || "DOWNLOAD_FAILED")}</span></div>`;
    } else if (t.status === "cancelled") {
      html += `<div class="task-meta">${tr("任务已取消，已完成文件仍然保留。", "Task cancelled. Completed files are kept.")}</div>`;
    }

    // A single attempt is the task itself; the history only helps once there was a retry.
    if (t.attempt_count > 1 && Array.isArray(t.attempts)) {
      html += `<details class="task-attempts" data-task-id="${escHtml(t.id)}"${openAttempts.has(t.id) ? " open" : ""}><summary>${tr("尝试记录 ", "Attempts ")}${t.attempt_count}</summary><div class="task-attempts-list">`;
      t.attempts.forEach(attempt => {
        const started = formatAttemptTime(attempt.started_at);
        const finished = formatAttemptTime(attempt.finished_at);
        html += `<span class="task-attempt">#${escHtml(attempt.number)} · ${escHtml(statusLabel(attempt.status))}${attempt.output_version > 1 ? `${tr(" · 版本 ", " · Version ")}${escHtml(attempt.output_version)}` : ""}${tr(" · 开始 ", " · Started ")}${escHtml(started)}${tr(" · 结束 ", " · Finished ")}${escHtml(finished)}</span>`;
      });
      html += `</div></details>`;
    }

    let actions = "";
    if (t.can_cancel) actions += `<button class="task-action" type="button" onclick="operateTask('cancel', '${escHtml(t.id)}')">${tr("取消", "Cancel")}</button>`;
    if (t.can_retry) actions += `<button class="task-action" type="button" onclick="operateTask('retry', '${escHtml(t.id)}')">${tr("重试", "Retry")}</button>`;
    if (t.can_redownload) actions += `<button class="task-action" type="button" onclick="operateTask('redownload', '${escHtml(t.id)}')">${tr("重新下载", "Redownload")}</button>`;
    if (t.platform === 'local' && t.status === "completed" && typeof r.download_url === 'string' && r.download_url.startsWith('/api/extract-audio/')) {
      actions += `<a class="task-action" href="${escHtml(r.download_url)}" download>${tr('下载音频', 'Download audio')}</a>`;
    }
    html += `<div class="task-actions">${actions}</div>`;
    html += `</div></li>`;
    return html;
  }

  function renderTasks(batch) {
    lastRenderedBatch = batch;
    pendingSkeletonCount = null;
    // Keep any attempt history the reader opened across live re-renders.
    const openAttempts = new Set(
      Array.from(taskContainer.querySelectorAll("details.task-attempts[open]")).map(node => node.dataset.taskId),
    );
    const tasks = Array.isArray(batch.tasks) ? batch.tasks : [];
    taskContainer.innerHTML = `<ul class="task-list">${tasks.map((task, index) => renderTask(batch, task, index, openAttempts)).join("")}</ul>`;
  }

  async function operateTask(action, taskId) {
    if (!currentBatchId) return;
    clearNotice(taskNotice);
    try {
      const response = await fetch(`/api/batch/${currentBatchId}/task/${taskId}/${action}`, { method: "POST" });
      const data = await response.json();
      if (!response.ok) {
        showNotice(taskNotice, () => formatApiError(data));
        return;
      }
      if (["retry", "redownload"].includes(action)) {
        isDownloading = true;
        setControlsDisabled(true);
      }
      startPolling();
    } catch (error) {
      showNotice(taskNotice, () => tr("网络错误：", "Network error: ") + error.message);
    }
  }

  async function retryFailedTasks() {
    if (!currentBatchId) return;
    clearNotice(taskNotice);
    try {
      const response = await fetch(`/api/batch/${currentBatchId}/retry-failed`, { method: "POST" });
      const data = await response.json();
      if (!response.ok) {
        showNotice(taskNotice, () => formatApiError(data));
        return;
      }
      retryFailedButton.hidden = true;
      isDownloading = true;
      setControlsDisabled(true);
      startPolling();
    } catch (error) {
      showNotice(taskNotice, () => tr("网络错误：", "Network error: ") + error.message);
    }
  }

  function renderDownloadProgress(progress) {
    const speed = progress && progress.speed_text ? backendText(progress.speed_text) : tr("计算中", "Calculating");
    const eta = progress && progress.eta_text ? backendText(progress.eta_text) : tr("计算中", "Calculating");
    const percentText = progress && progress.percent_text ? progress.percent_text : "";
    const totalSize = progress && progress.total_size_text ? backendText(progress.total_size_text) : tr("计算中", "Calculating");
    const totalSizeLabel = progress && progress.total_size_is_estimate ? tr("预计总大小", "Estimated total size") : tr("总大小", "Total size");
    const percent = progressPercent(progress);
    const item = (labelText, value) => `<span class="task-progress-item"><span class="task-progress-label">${escHtml(labelText)}</span><span class="task-progress-value">${escHtml(value)}</span></span>`;

    let html = percent === null ? "" : renderProgressBar(percent, tr("下载进度", "Download progress"));
    html += `<div class="task-progress">`;
    if (percentText && percentText !== "计算中") html += item(tr("进度", "Progress"), percentText);
    html += item(tr("下载速度", "Download speed"), speed);
    html += item(tr("预计剩余", "Time remaining"), eta);
    html += item(totalSizeLabel, totalSize);
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
    clearNotice(collectionNotice);
    if (resetMetrics) setOperationalMetrics(0, 0);
    restoreTaskPanelHeading();
  }

  // Escapes text for element content and quoted attributes alike.
  function escHtml(value) {
    if (value === null || value === undefined || value === "") return "";
    return String(value).replace(/[&<>"']/g, character => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[character]);
  }

  function fetchJsonWithTimeout(url, timeoutMs = 15000) {
    return window.GtdTaskApi.fetchJson(url, {timeoutMs, readErrorBody: false});
  }

  function rememberCurrentBatch(batchId) {
    try {
      if (batchId) localStorage.setItem(CURRENT_BATCH_KEY, batchId);
      else localStorage.removeItem(CURRENT_BATCH_KEY);
    } catch (_) { /* Persistence is optional; current-page controls still work. */ }
  }

  function renderBatchHistory() {
    if (!batchHistory) return;
    const selected = currentBatchId || batchHistory.value;
    batchHistory.innerHTML = `<option value="">${tr("选择历史任务", "Select a saved batch")}</option>` + historyBatches.map(batch => {
      const date = new Date(batch.created_at * 1000).toLocaleString(window.GtdLanguage?.language === "en" ? "en-US" : "zh-CN", {hour12: false});
      const description = tr("{date} · {n} 项 · 完成 {done} · 失败 {failed}", "{date} · {n} items · {done} completed · {failed} failed", {date, n: batch.total, done: batch.completed, failed: batch.failed});
      return `<option value="${escHtml(batch.id)}">${escHtml(description)}</option>`;
    }).join("");
    batchHistory.value = selected || "";
  }

  async function refreshBatchHistory() {
    if (!batchHistory || historyLoading) return;
    historyLoading = true;
    try {
      const response = await fetchJsonWithTimeout("/api/batches");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = response.data;
      historyBatches = Array.isArray(data.batches) ? data.batches : [];
      renderBatchHistory();
      clearNotice(taskNotice, "history");
    } catch (_) {
      showNotice(taskNotice, () => tr("暂时无法读取任务历史，请点击“刷新”重试。", "Task history is unavailable right now. Select Refresh to try again."), {kind: "history"});
    } finally { historyLoading = false; }
  }

  function selectHistoryBatch(batchId) {
    if (!batchId || isDownloading || pendingPreview) return;
    stopPolling();
    clearNotice(taskNotice);
    currentBatchId = batchId;
    rememberCurrentBatch(batchId);
    lastTaskRenderSignature = null;
    isDownloading = true;
    setControlsDisabled(true);
    setLocalized(taskSummary, "正在恢复任务状态…", "Restoring task status…");
    startPolling();
  }

  function initializeBatchHistory() {
    // Opening or refreshing the homepage starts at its character empty state.
    // Saved batches remain available through the history picker.
    rememberCurrentBatch(null);
    refreshBatchHistory();
  }

  Object.assign(window, {
    refreshBatchHistory,
    selectHistoryBatch,
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
  initializeUrlInputs();
  initializeDownloadDirectoryHistory();
  loadCapabilities();
  initializeBatchHistory();
