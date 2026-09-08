(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const tr = (zh, en) => window.GtdLanguage?.language === 'en' ? en : zh;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const KEY = 'gtd_extract_batch_v1';
  const errors = {
    UPLOAD_TOO_LARGE: ['视频超过 2 GiB，请选择较小的文件。', 'This video exceeds 2 GiB. Choose a smaller file.'],
    UPLOAD_STORAGE_FULL: ['暂存空间不足，请稍后重试。', 'Upload storage is full. Try again later.'],
    INVALID_UPLOAD: ['请选择一个非空的视频文件。', 'Choose one nonempty video file.'],
    INVALID_MEDIA: ['无法读取此视频，请检查文件是否完整。', 'This video could not be read. Check that the file is complete.'],
    NO_AUDIO: ['此视频没有音轨，请选择其他视频。', 'This video has no audio track. Choose another video.'],
    INPUT_EXPIRED: ['输入文件已过期或丢失，请重新上传。', 'The input file expired or is missing. Upload it again.'],
    FFMPEG_MISSING: ['服务缺少 FFmpeg 或 ffprobe，安装后重试。', 'FFmpeg or ffprobe is missing on the server. Install it and retry.'],
    EXTRACTION_FAILED: ['音频提取失败，请重试或选择其他视频。', 'Audio extraction failed. Retry or choose another video.'],
    NETWORK_ERROR: ['连接失败，请检查网络后刷新历史。', 'Connection failed. Check your network and refresh history.'],
    UPLOAD_CANCELLED: ['上传已取消。', 'Upload cancelled.'],
    BATCH_NOT_FOUND: ['找不到此任务，请刷新历史或重新上传。', 'This batch is unavailable. Refresh history or upload again.'],
    TASK_NOT_FOUND: ['找不到此任务，请刷新历史。', 'This task is unavailable. Refresh history.'],
    TASK_STATE_CONFLICT: ['任务状态已改变，请刷新后重试。', 'The task status changed. Refresh and try again.'],
    INVALID_TASK_ACTION: ['任务状态已改变，请刷新后重试。', 'The task status changed. Refresh and try again.']
  };
  let file = null, xhr = null, batchId = '', batch = null, history = [], timer = null, failures = 0, generation = 0;
  let uploadPercent = 0, uploadStage = '', currentError = null, historyLoading = false;
  const errorText = error => {
    const pair = errors[error?.error_code];
    return pair ? tr(...pair) : (window.GtdLanguage?.language === 'en' ? 'The operation failed. Refresh and try again.' : [error?.message, error?.suggestion].filter(Boolean).join(' ') || '操作失败，请刷新后重试。');
  };
  function showError(error) { currentError = error; $('extract-error').hidden = !error; $('extract-error').textContent = error ? errorText(error) : ''; }
  function persist() { try { if (batchId) localStorage.setItem(KEY, batchId); else localStorage.removeItem(KEY); } catch (_) {} }
  function renderFile() { $('selected-file').textContent = file ? `${file.name} · ${(file.size / 1048576).toFixed(1)} MiB` : tr('尚未选择文件', 'No file selected'); }
  function choose(files) {
    if (xhr) return;
    file = null;
    if (files.length !== 1 || !files[0].size) showError({error_code: 'INVALID_UPLOAD'});
    else if (files[0].size > 2 * 1024 ** 3) showError({error_code: 'UPLOAD_TOO_LARGE'});
    else { file = files[0]; showError(null); }
    renderFile();
  }
  function renderUpload() {
    $('upload-state').hidden = !uploadStage;
    $('upload-progress').value = uploadPercent;
    $('upload-label').textContent = uploadStage === 'sent' ? tr('上传完成，正在加入队列…', 'Upload complete. Adding to the queue…') : uploadStage === 'queued' ? tr('上传完成，已加入提取队列。可继续选择其他视频。', 'Upload complete and queued. You can choose another video.') : `${tr('上传视频', 'Uploading video')} · ${uploadPercent}%`;
  }
  async function request(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(url, {...options, signal: controller.signal});
      let data;
      try { data = await response.json(); } catch (_) { throw {error_code: 'NETWORK_ERROR'}; }
      if (!response.ok) throw data;
      return data;
    } catch (error) { throw error?.error_code ? error : {error_code: 'NETWORK_ERROR'}; }
    finally { clearTimeout(timeout); }
  }
  function statusLabel(status) {
    const labels = {queued:['等待中','Queued'], running:['提取中','Extracting'], completed:['已完成','Completed'], failed:['失败','Failed'], cancelled:['已取消','Cancelled']};
    return tr(...(labels[status] || ['处理中','Processing']));
  }
  function renderTasks() {
    if (!batch) { $('extract-tasks').innerHTML = `<div class="empty-state"><p>${tr('选择视频后开始提取音频', 'Choose a video to start extracting audio')}</p></div>`; $('extract-summary').textContent = ''; return; }
    const tasks = Array.isArray(batch.tasks) ? batch.tasks : [];
    $('extract-summary').textContent = `${tasks.filter(t => t.status === 'completed').length} / ${tasks.length} ${tr('已完成', 'completed')}`;
    $('extract-tasks').innerHTML = '<ul class="task-list">' + tasks.map((task, i) => {
      const status = ['queued','running','completed','failed','cancelled'].includes(task.status) ? task.status : 'running';
      const result = task.result || {};
      let detail = '';
      if (status === 'running') {
        const percent = parseFloat(task.progress?.percent_text);
        detail = `<div class="task-meta">${tr('音频处理进度', 'Audio processing progress')}${Number.isFinite(percent) ? ` · ${esc(task.progress.percent_text)}` : ` · ${tr('处理中…', 'Processing…')}`}<progress max="100" ${Number.isFinite(percent) ? `value="${Math.max(0, Math.min(100, percent))}"` : ''} aria-label="${tr('音频处理进度', 'Audio processing progress')}"></progress></div>`;
      } else if (status === 'queued') detail = `<div class="task-meta">${tr('等待队列中的可用位置', 'Waiting for an available queue slot')}</div>`;
      else if (status === 'failed') detail = `<div class="task-error">${esc(errorText(task.error))}</div>`;
      else if (status === 'completed') detail = `<div class="task-meta">${esc(result.format || '—')} · ${esc(result.acodec || '—')} · ${esc(result.filesize || '—')}${result.filepath ? `<br>${tr('保存位置：', 'Saved to: ')}${esc(result.filepath)}` : ''}</div>`;
      let actions = '';
      for (const action of ['cancel', 'retry']) if (task[`can_${action}`]) actions += `<button type="button" class="task-action" data-task="${esc(task.id)}" data-action="${action}">${action === 'cancel' ? tr('取消', 'Cancel') : tr('重试', 'Retry')}</button>`;
      if (status === 'completed' && typeof result.download_url === 'string' && result.download_url.startsWith('/api/extract-audio/') && !result.download_url.startsWith('//')) actions += `<a class="task-action" href="${esc(result.download_url)}" download>${tr('下载音频', 'Download audio')} ↗</a>`;
      return `<li class="task-item status-${status}"><span class="task-index">${String(i + 1).padStart(2,'0')}</span><div class="task-body"><div class="task-url">${esc(result.title || task.title || task.url || tr('本地视频', 'Local video'))}</div>${detail}<div class="task-actions">${actions}</div></div><span class="badge badge-${status}">${statusLabel(status)}</span></li>`;
    }).join('') + '</ul>';
  }
  function renderHistory() {
    $('extract-history').innerHTML = `<option value="">${tr('选择历史任务', 'Select a saved batch')}</option>` + history.map(item => `<option value="${esc(item.id)}">${esc(new Date(item.created_at * 1000).toLocaleString(window.GtdLanguage?.language === 'en' ? 'en-US' : 'zh-CN'))} · ${item.completed || 0}/${item.total || 1} ${tr('已完成', 'completed')}</option>`).join('');
    $('extract-history').value = batchId;
  }
  async function refreshHistory() {
    if (historyLoading) return;
    historyLoading = true; $('refresh-history').disabled = true;
    try { const data = await request('/api/extract-audio/batches'); history = data.batches || []; renderHistory(); $('history-feedback').textContent = ''; }
    catch (error) { $('history-feedback').textContent = errorText(error); }
    finally { historyLoading = false; $('refresh-history').disabled = false; }
  }
  async function poll(token) {
    if (!batchId || token !== generation) return;
    const requested = batchId;
    try {
      const data = await request(`/api/batch/${encodeURIComponent(requested)}`);
      if (token !== generation) return;
      batch = data; failures = 0; renderTasks(); $('history-feedback').textContent = '';
      if ((data.tasks || []).some(task => ['queued','running','running_uninterruptible'].includes(task.status))) timer = setTimeout(() => poll(token), 1200);
      else refreshHistory();
    } catch (error) {
      if (token !== generation) return;
      failures += 1; $('history-feedback').textContent = errorText(error);
      if (failures < 6 && error.error_code !== 'BATCH_NOT_FOUND') timer = setTimeout(() => poll(token), Math.min(30000, 1500 * 2 ** failures));
    }
  }
  function selectBatch(id) { clearTimeout(timer); generation += 1; failures = 0; batchId = id; batch = null; persist(); renderHistory(); renderTasks(); if (id) poll(generation); }
  $('video-file').addEventListener('change', e => choose(e.target.files));
  const drop = $('extract-drop');
  ['dragenter','dragover'].forEach(name => drop.addEventListener(name, e => { e.preventDefault(); if (!xhr) drop.classList.add('drag-over'); }));
  ['dragleave','drop'].forEach(name => drop.addEventListener(name, e => { e.preventDefault(); drop.classList.remove('drag-over'); }));
  drop.addEventListener('drop', e => { choose(e.dataTransfer.files); });
  $('extract-form').addEventListener('submit', e => {
    e.preventDefault(); if (xhr) return;
    if (!file) { showError({error_code:'INVALID_UPLOAD'}); return; }
    showError(null);
    const data = new FormData(); data.append('video', file); data.append('audio_format', document.querySelector('input[name="audio_format"]:checked').value);
    xhr = new XMLHttpRequest(); xhr.open('POST', '/api/extract-audio'); xhr.timeout = 30 * 60 * 1000;
    $('extract-submit').disabled = true; $('video-file').disabled = true; $('upload-cancel').hidden = false; uploadStage = 'uploading'; uploadPercent = 0; renderUpload();
    xhr.upload.onprogress = event => { if (event.lengthComputable) { uploadPercent = Math.round(100 * event.loaded / event.total); if (uploadPercent === 100) uploadStage = 'sent'; renderUpload(); } };
    xhr.onload = () => {
      let response; try { response = JSON.parse(xhr.responseText); } catch (_) { response = {error_code:'NETWORK_ERROR'}; }
      if (xhr.status >= 200 && xhr.status < 300 && response.batch_id) { uploadStage = 'queued'; uploadPercent = 100; file = null; $('video-file').value = ''; renderFile(); selectBatch(response.batch_id); refreshHistory(); }
      else { uploadStage = ''; showError(response); }
    };
    xhr.onerror = xhr.ontimeout = () => { uploadStage = ''; showError({error_code:'NETWORK_ERROR'}); };
    xhr.onabort = () => { uploadStage = ''; showError({error_code:'UPLOAD_CANCELLED'}); };
    xhr.onloadend = () => { xhr = null; $('extract-submit').disabled = false; $('video-file').disabled = false; $('upload-cancel').hidden = true; renderUpload(); };
    xhr.send(data);
  });
  $('upload-cancel').addEventListener('click', () => xhr?.abort());
  $('extract-history').addEventListener('change', e => selectBatch(e.target.value));
  $('refresh-history').addEventListener('click', () => { refreshHistory(); if (batchId) { clearTimeout(timer); generation += 1; failures = 0; poll(generation); } });
  $('extract-tasks').addEventListener('click', async event => {
    const button = event.target.closest('button[data-action]'); if (!button || button.disabled) return;
    button.disabled = true; const requested = batchId;
    try { await request(`/api/batch/${encodeURIComponent(requested)}/task/${encodeURIComponent(button.dataset.task)}/${button.dataset.action}`, {method:'POST'}); if (requested === batchId) { clearTimeout(timer); generation += 1; failures = 0; poll(generation); } }
    catch (error) { showError(error); } finally { button.disabled = false; }
  });
  document.addEventListener('gtd:languagechange', () => { renderFile(); renderUpload(); renderHistory(); renderTasks(); showError(currentError); });
  try { batchId = localStorage.getItem(KEY) || ''; } catch (_) {}
  renderFile(); renderTasks(); refreshHistory(); if (batchId) poll(generation);
})();
