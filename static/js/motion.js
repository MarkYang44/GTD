(() => {
  "use strict";

  const root = document.documentElement;
  let reduced = true;
  let finePointer = false;
  const REVEAL_SELECTOR = "[data-motion-reveal]";
  const SURFACE_SELECTOR = "[data-motion-surface]";
  const PARALLAX_SELECTOR = "[data-motion-parallax]";
  const MAX_PARALLAX = 12;
  const MAX_TILT = 0.6;
  const NUMBER_DURATION = 280;
  let frameId = null;
  let scrollDirty = true;
  let activeSurface = null;
  let pointerEvent = null;
  let revealObserver = null;
  let destroyed = false;
  let enabled = false;
  const surfaceListeners = new Map();
  const numberAnimations = new Map();
  const observedReveals = new Set();

  function select(rootNode, selector) {
    if (!rootNode || !rootNode.querySelectorAll) return [];
    const nodes = Array.from(rootNode.querySelectorAll(selector));
    if (rootNode.matches?.(selector)) nodes.unshift(rootNode);
    return nodes;
  }

  function clamp(value, minimum, maximum) {
    return Math.min(maximum, Math.max(minimum, value));
  }

  function isTaskItem(element) {
    return Boolean(element.closest?.(".task-item"));
  }

  function makeVisible(element) {
    element.classList?.add("motion-visible");
  }

  function resetSurface(surface) {
    const listeners = surfaceListeners.get(surface);
    surface.classList?.remove("motion-surface-active");
    surface.style?.setProperty("--motion-x", "50%");
    surface.style?.setProperty("--motion-y", "50%");
    surface.style?.setProperty("--motion-rx", "0deg");
    surface.style?.setProperty("--motion-ry", "0deg");
    if (listeners?.backgroundImage !== undefined) {
      surface.style.backgroundImage = listeners.backgroundImage;
      listeners.backgroundImage = undefined;
      listeners.baseBackgroundImage = undefined;
    }
  }

  function scheduleFrame() {
    if (!enabled || document.hidden || frameId !== null || typeof requestAnimationFrame !== "function") return;
    frameId = requestAnimationFrame(runFrame);
  }

  function updateScrollState() {
    const scrollY = Math.max(0, window.scrollY || window.pageYOffset || 0);
    const documentHeight = Math.max(document.body?.scrollHeight || 0, document.documentElement?.scrollHeight || 0);
    const scrollRange = Math.max(0, documentHeight - window.innerHeight);
    const progress = scrollRange ? clamp(scrollY / scrollRange, 0, 1) : 0;

    for (const element of select(document, PARALLAX_SELECTOR)) {
      const strength = clamp(Number.parseFloat(element.getAttribute("data-motion-parallax")) || 0, 0, 1);
      const offset = (progress * 2 - 1) * strength * MAX_PARALLAX;
      element.style.setProperty("--motion-parallax-offset", `${offset.toFixed(2)}px`);
    }

    const progressElement = document.querySelector?.("#scroll-progress");
    progressElement?.style.setProperty("--motion-scroll-progress", String(progress));
    const topbar = document.querySelector?.("#topbar");
    topbar?.style.setProperty("--motion-scroll-progress", String(progress));
    document.dispatchEvent(new CustomEvent("motion:scroll-frame", { detail: { scrollY, progress } }));
  }

  function updateSurface(surface, event) {
    const bounds = surface.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const x = clamp((event.clientX - bounds.left) / bounds.width, 0, 1);
    const y = clamp((event.clientY - bounds.top) / bounds.height, 0, 1);
    const rotateX = clamp((0.5 - y) * 2 * MAX_TILT, -MAX_TILT, MAX_TILT);
    const rotateY = clamp((x - 0.5) * 2 * MAX_TILT, -MAX_TILT, MAX_TILT);

    surface.classList.add("motion-surface-active");
    surface.style.setProperty("--motion-x", `${(x * 100).toFixed(1)}%`);
    surface.style.setProperty("--motion-y", `${(y * 100).toFixed(1)}%`);
    surface.style.setProperty("--motion-rx", `${rotateX.toFixed(1)}deg`);
    surface.style.setProperty("--motion-ry", `${rotateY.toFixed(1)}deg`);
    const listeners = surfaceListeners.get(surface);
    if (typeof listeners?.baseBackgroundImage === "string") {
      surface.style.backgroundImage = `radial-gradient(circle at ${(x * 100).toFixed(1)}% ${(y * 100).toFixed(1)}%, rgba(0, 161, 155, .11), transparent 38%), ${listeners.baseBackgroundImage}`;
    }
  }

  function updateNumbers(timestamp) {
    let hasPendingAnimation = false;
    for (const [element, animation] of numberAnimations) {
      if (animation.startedAt === null) animation.startedAt = timestamp;
      const progress = clamp((timestamp - animation.startedAt) / NUMBER_DURATION, 0, 1);
      element.textContent = String(Math.round(animation.start + (animation.target - animation.start) * progress));
      if (progress === 1) {
        numberAnimations.delete(element);
      } else {
        hasPendingAnimation = true;
      }
    }
    return hasPendingAnimation;
  }

  function runFrame(timestamp) {
    frameId = null;
    if (document.hidden || destroyed || !enabled) return;
    try {
      if (scrollDirty) updateScrollState();
      if (activeSurface && pointerEvent) updateSurface(activeSurface, pointerEvent);
      const hasPendingNumbers = updateNumbers(timestamp);
      scrollDirty = false;
      pointerEvent = null;
      if (hasPendingNumbers) scheduleFrame();
    } catch (error) {
      failOpen();
    }
  }

  function observeReveals(rootNode) {
    const reveals = select(rootNode, REVEAL_SELECTOR).filter((element) => !isTaskItem(element));
    const groupOrders = new Map();
    for (const element of reveals) {
      const explicitOrder = Number.parseInt(element.getAttribute("data-motion-order"), 10);
      const group = element.getAttribute("data-motion-group") || "__default";
      const groupOrder = groupOrders.get(group) || 0;
      const order = Number.isFinite(explicitOrder) ? explicitOrder : groupOrder;
      element.style.setProperty("--motion-order", String(order));
      groupOrders.set(group, groupOrder + 1);
      if (!element.classList.contains("motion-visible")) {
        if (revealObserver && !observedReveals.has(element)) {
          observedReveals.add(element);
          revealObserver.observe(element);
        } else if (!revealObserver) {
          makeVisible(element);
        }
      }
    }
  }

  function addSurfaceListeners(rootNode) {
    if (!finePointer || reduced) return;
    for (const surface of select(rootNode, SURFACE_SELECTOR)) {
      if (surfaceListeners.has(surface) || isTaskItem(surface)) continue;
      const enter = (event) => {
        activeSurface = surface;
        beginSurfaceSheen(surface);
        pointerEvent = event;
        scheduleFrame();
      };
      const move = (event) => {
        if (activeSurface !== surface) activeSurface = surface;
        beginSurfaceSheen(surface);
        pointerEvent = event;
        scheduleFrame();
      };
      const leave = () => {
        if (activeSurface === surface) {
          activeSurface = null;
          pointerEvent = null;
        }
        resetSurface(surface);
      };
      surface.addEventListener("pointerenter", enter);
      surface.addEventListener("pointermove", move);
      surface.addEventListener("pointerleave", leave);
      surfaceListeners.set(surface, { enter, move, leave });
    }
  }

  function beginSurfaceSheen(surface) {
    const listeners = surfaceListeners.get(surface);
    if (!listeners || listeners.backgroundImage !== undefined) return;
    const computedStyle = window.getComputedStyle?.(surface);
    if (!computedStyle || typeof computedStyle.backgroundImage !== "string") return;
    listeners.backgroundImage = surface.style.backgroundImage || "";
    listeners.baseBackgroundImage = computedStyle.backgroundImage;
  }

  function refresh(rootNode = document) {
    if (destroyed) return;
    if (!enabled) {
      for (const element of select(rootNode, REVEAL_SELECTOR)) makeVisible(element);
      return;
    }
    observeReveals(rootNode);
    addSurfaceListeners(rootNode);
    scrollDirty = true;
    scheduleFrame();
  }

  function setNumber(element, value) {
    if (!element) return;
    numberAnimations.delete(element);
    const numericValue = typeof value === "number"
      ? value
      : typeof value === "string" && /^-?\d+$/.test(value.trim())
        ? Number(value)
        : Number.NaN;
    if (!enabled || reduced || !Number.isInteger(numericValue)) {
      element.textContent = String(value);
      return;
    }
    const currentText = element.textContent.trim();
    const currentValue = /^-?\d+$/.test(currentText) ? Number.parseInt(currentText, 10) : numericValue;
    if (currentValue === numericValue) {
      element.textContent = String(numericValue);
      return;
    }
    numberAnimations.set(element, { start: currentValue, target: numericValue, startedAt: null });
    scheduleFrame();
  }

  function cancelFrame() {
    if (frameId !== null && typeof cancelAnimationFrame === "function") cancelAnimationFrame(frameId);
    frameId = null;
  }

  function resetAllSurfaces() {
    activeSurface = null;
    pointerEvent = null;
    for (const surface of surfaceListeners.keys()) resetSurface(surface);
  }

  function resetParallax() {
    for (const element of select(document, PARALLAX_SELECTOR)) {
      element.style.setProperty("--motion-parallax-offset", "0px");
    }
  }

  function onScroll() {
    scrollDirty = true;
    scheduleFrame();
  }

  function onVisibilityChange() {
    if (document.hidden) {
      cancelFrame();
      resetAllSurfaces();
      numberAnimations.clear();
      return;
    }
    scrollDirty = true;
    scheduleFrame();
  }

  function removeGlobalListeners() {
    window.removeEventListener?.("scroll", onScroll);
    window.removeEventListener?.("resize", onScroll);
    document.removeEventListener?.("visibilitychange", onVisibilityChange);
  }

  function removeSurfaceListeners() {
    for (const [surface, listeners] of surfaceListeners) {
      surface.removeEventListener("pointerenter", listeners.enter);
      surface.removeEventListener("pointermove", listeners.move);
      surface.removeEventListener("pointerleave", listeners.leave);
      resetSurface(surface);
    }
    surfaceListeners.clear();
  }

  function disconnectRevealObserver() {
    revealObserver?.disconnect();
    revealObserver = null;
    observedReveals.clear();
  }

  function destroy() {
    if (destroyed) return;
    destroyed = true;
    enabled = false;
    cancelFrame();
    disconnectRevealObserver();
    removeGlobalListeners();
    removeSurfaceListeners();
    numberAnimations.clear();
    resetParallax();
    root.classList.remove("motion-ready", "motion-enabled", "motion-fine-pointer", "motion-reduced");
  }

  function failOpen() {
    destroyed = true;
    enabled = false;
    cancelFrame();
    resetAllSurfaces();
    resetParallax();
    disconnectRevealObserver();
    removeGlobalListeners();
    removeSurfaceListeners();
    numberAnimations.clear();
    for (const element of select(document, REVEAL_SELECTOR)) makeVisible(element);
    root.classList.remove("motion-ready", "motion-enabled", "motion-fine-pointer", "motion-reduced");
  }

  try {
    const reducedQuery = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
    const finePointerQuery = window.matchMedia ? window.matchMedia("(hover: hover) and (pointer: fine)") : null;
    reduced = reducedQuery ? reducedQuery.matches : true;
    finePointer = finePointerQuery ? finePointerQuery.matches : false;
    if (reduced) {
      root.classList.add("motion-reduced");
      for (const element of select(document, REVEAL_SELECTOR)) makeVisible(element);
    } else if (typeof IntersectionObserver === "function" && typeof requestAnimationFrame === "function") {
      revealObserver = new IntersectionObserver((entries) => {
        try {
          for (const entry of entries) {
            if (!entry.isIntersecting) continue;
            makeVisible(entry.target);
            observedReveals.delete(entry.target);
            revealObserver.unobserve(entry.target);
          }
        } catch (error) {
          failOpen();
        }
      }, { threshold: 0.12 });
      enabled = true;
      root.classList.add("motion-ready");
      root.classList.add("motion-enabled");
      if (finePointer) root.classList.add("motion-fine-pointer");
      window.addEventListener("scroll", onScroll, { passive: true });
      window.addEventListener("resize", onScroll, { passive: true });
      document.addEventListener("visibilitychange", onVisibilityChange);
      refresh();
    } else {
      for (const element of select(document, REVEAL_SELECTOR)) makeVisible(element);
    }
  } catch (error) {
    failOpen();
  }

  window.MotionSystem = { refresh, destroy, setNumber };
})();
