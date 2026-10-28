/* Shared transport only: pages own batch selection and polling lifecycle. */
(() => {
  'use strict';

  async function fetchJson(url, options = {}) {
    const {timeoutMs = 15000, readErrorBody = true, ...requestOptions} = options;
    const controller = typeof AbortController === 'undefined' ? null : new AbortController();
    const upstream = requestOptions.signal;
    const cancel = () => controller.abort(upstream.reason);
    let timer = null;
    try {
      if (controller) {
        if (upstream?.aborted) cancel();
        else upstream?.addEventListener('abort', cancel, {once: true});
        timer = setTimeout(() => controller.abort(), timeoutMs);
      }
      const response = await fetch(url, controller
        ? {...requestOptions, signal: controller.signal} : requestOptions);
      // Keep the timeout active through body consumption, not only response headers.
      const data = response.ok || readErrorBody ? await response.json() : null;
      return {ok: response.ok, status: response.status, data};
    } finally {
      if (timer !== null) clearTimeout(timer);
      if (controller) upstream?.removeEventListener('abort', cancel);
    }
  }

  function backoffDelay(baseMs, failures, maximumMs = 30000) {
    return Math.min(maximumMs, baseMs * 2 ** failures);
  }

  window.GtdTaskApi = Object.freeze({fetchJson, backoffDelay});
})();
