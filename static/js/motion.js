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
  const revealSettlers = new Map();

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

  function settleReveal(element) {
    const listener = revealSettlers.get(element);
    if (listener) {
      element.removeEventListener?.("transitionend", listener);
      revealSettlers.delete(element);
    }
    element.classList?.add("motion-settled");
  }

  function hasRevealTransition(element) {
    const style = window.getComputedStyle?.(element);
    if (!style || typeof style.transitionDuration !== "string") return false;
    return style.transitionDuration.split(",").some((duration) => Number.parseFloat(duration) > 0);
  }

  function revealElement(element) {
    if (!element) throw new Error("Missing motion reveal target");
    if (element.classList?.contains("motion-settled")) return;
    makeVisible(element);
    if (!enabled || !hasRevealTransition(element)) {
      settleReveal(element);
      return;
    }
    if (revealSettlers.has(element)) return;
    const onceTransitionEnd = (event) => {
      if (event.target !== element || !["opacity", "transform"].includes(event.propertyName)) return;
      settleReveal(element);
    };
    revealSettlers.set(element, onceTransitionEnd);
    element.addEventListener?.("transitionend", onceTransitionEnd);
  }

  function resetSurface(surface) {
    const listeners = surfaceListeners.get(surface);
    surface.classList?.remove("motion-surface-active");
    surface.classList?.remove("motion-surface-fallback");
    surface.style?.setProperty("--motion-x", "50%");
    surface.style?.setProperty("--motion-y", "50%");
    surface.style?.setProperty("--motion-rx", "0deg");
    surface.style?.setProperty("--motion-ry", "0deg");
    if (listeners?.baseBackgroundCaptured) {
      if (listeners.baseBackgroundValue) {
        surface.style?.setProperty("--motion-base-background", listeners.baseBackgroundValue);
      } else {
        surface.style?.removeProperty?.("--motion-base-background");
      }
      listeners.baseBackgroundCaptured = false;
      listeners.baseBackgroundValue = "";
    }
  }

  function scheduleFrame() {
    if (destroyed || document.hidden || frameId !== null) return;
    if (typeof requestAnimationFrame !== "function") {
      runFrame(0);
      return;
    }
    frameId = requestAnimationFrame(runFrame);
  }

  function updateScrollState() {
    const scrollY = Math.max(0, window.scrollY || window.pageYOffset || 0);
    const documentHeight = Math.max(document.body?.scrollHeight || 0, document.documentElement?.scrollHeight || 0);
    const scrollRange = Math.max(0, documentHeight - window.innerHeight);
    const progress = scrollRange ? clamp(scrollY / scrollRange, 0, 1) : 0;

    if (enabled) {
      for (const element of select(document, PARALLAX_SELECTOR)) {
        const strength = clamp(Number.parseFloat(element.getAttribute("data-motion-parallax")) || 0, 0, 1);
        const offset = (progress * 2 - 1) * strength * MAX_PARALLAX;
        element.style.setProperty("--motion-parallax-offset", `${offset.toFixed(2)}px`);
      }
    }

    const progressElement = document.querySelector?.("#scroll-progress");
    progressElement?.style.setProperty("--motion-scroll-progress", String(progress));
    const topbar = document.querySelector?.("#topbar");
    topbar?.style.setProperty("--motion-scroll-progress", String(progress));
    topbar?.classList?.toggle("is-scrolled", scrollY > 12);
    document.dispatchEvent(new CustomEvent("motion:scroll-frame", { detail: { scrollY, progress } }));
  }

  function updateSurface(surface, event) {
    const bounds = surface.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const x = clamp((event.clientX - bounds.left) / bounds.width, 0, 1);
    const y = clamp((event.clientY - bounds.top) / bounds.height, 0, 1);
    const rotateX = clamp((0.5 - y) * 2 * MAX_TILT, -MAX_TILT, MAX_TILT);
    const rotateY = clamp((x - 0.5) * 2 * MAX_TILT, -MAX_TILT, MAX_TILT);

    surface.style.setProperty("--motion-x", `${(x * 100).toFixed(1)}%`);
    surface.style.setProperty("--motion-y", `${(y * 100).toFixed(1)}%`);
    surface.style.setProperty("--motion-rx", `${rotateX.toFixed(1)}deg`);
    surface.style.setProperty("--motion-ry", `${rotateY.toFixed(1)}deg`);
  }

  function updateNumbers(timestamp) {
    let hasPendingAnimation = false;
    for (const [element, animation] of numberAnimations) {
      if (animation.startedAt === null) animation.startedAt = timestamp;
      const progress = clamp((timestamp - animation.startedAt) / NUMBER_DURATION, 0, 1);
      element.textContent = formatNumber(
        Math.round(animation.start + (animation.target - animation.start) * progress),
        animation.minimumDigits,
      );
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
    if (document.hidden || destroyed) return;
    try {
      if (scrollDirty) updateScrollState();
      if (enabled && activeSurface && pointerEvent) updateSurface(activeSurface, pointerEvent);
      const hasPendingNumbers = enabled && updateNumbers(timestamp);
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
          revealElement(element);
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
        prepareSurface(surface);
        pointerEvent = event;
        scheduleFrame();
      };
      const move = (event) => {
        if (activeSurface !== surface) activeSurface = surface;
        prepareSurface(surface);
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

  function prepareSurface(surface) {
    const listeners = surfaceListeners.get(surface);
    if (!listeners) return;
    surface.classList?.add("motion-surface-active");
    if (surface.querySelector?.("[data-motion-sheen]") || listeners.baseBackgroundCaptured) return;
    const computedStyle = window.getComputedStyle?.(surface);
    if (!computedStyle || typeof computedStyle.backgroundImage !== "string") return;
    listeners.baseBackgroundCaptured = true;
    listeners.baseBackgroundValue = surface.style?.getPropertyValue?.("--motion-base-background") || "";
    surface.style?.setProperty("--motion-base-background", computedStyle.backgroundImage);
    surface.classList?.add("motion-surface-fallback");
  }

  function refresh(rootNode = document) {
    if (destroyed) return;
    if (!enabled) {
      for (const element of select(rootNode, REVEAL_SELECTOR)) revealElement(element);
    } else {
      observeReveals(rootNode);
      addSurfaceListeners(rootNode);
    }
    scrollDirty = true;
    scheduleFrame();
  }

  function setNumber(element, value) {
    if (!element) return;
    numberAnimations.delete(element);
    const numericText = typeof value === "string" && /^-?\d+$/.test(value.trim())
      ? value.trim()
      : null;
    const numericValue = typeof value === "number"
      ? value
      : numericText !== null
        ? Number(numericText)
        : Number.NaN;
    if (!enabled || reduced || !Number.isInteger(numericValue)) {
      element.textContent = String(value);
      return;
    }
    const currentText = element.textContent.trim();
    const currentValue = /^-?\d+$/.test(currentText) ? Number.parseInt(currentText, 10) : numericValue;
    const minimumDigits = numericText ? numericText.replace("-", "").length : 0;
    if (currentValue === numericValue) {
      element.textContent = formatNumber(numericValue, minimumDigits);
      return;
    }
    numberAnimations.set(element, {
      start: currentValue,
      target: numericValue,
      minimumDigits,
      startedAt: null,
    });
    scheduleFrame();
  }

  function formatNumber(value, minimumDigits = 0) {
    const sign = value < 0 ? "-" : "";
    return sign + String(Math.abs(value)).padStart(minimumDigits, "0");
  }

  function cancelFrame() {
    if (frameId !== null && typeof cancelAnimationFrame === "function") cancelAnimationFrame(frameId);
    frameId = null;
  }

  function completeNumberAnimations() {
    for (const [element, animation] of numberAnimations) {
      element.textContent = formatNumber(animation.target, animation.minimumDigits);
    }
    numberAnimations.clear();
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
      completeNumberAnimations();
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

  function removeRevealSettlers() {
    for (const [element, listener] of revealSettlers) {
      element.removeEventListener?.("transitionend", listener);
    }
    revealSettlers.clear();
  }

  function destroy() {
    if (destroyed) return;
    destroyed = true;
    enabled = false;
    cancelFrame();
    disconnectRevealObserver();
    removeRevealSettlers();
    removeGlobalListeners();
    removeSurfaceListeners();
    completeNumberAnimations();
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
    removeRevealSettlers();
    removeGlobalListeners();
    removeSurfaceListeners();
    completeNumberAnimations();
    for (const element of select(document, REVEAL_SELECTOR)) revealElement(element);
    root.classList.remove("motion-ready", "motion-enabled", "motion-fine-pointer", "motion-reduced");
  }

  try {
    const reducedQuery = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
    const finePointerQuery = window.matchMedia ? window.matchMedia("(hover: hover) and (pointer: fine)") : null;
    reduced = reducedQuery ? reducedQuery.matches : true;
    finePointer = finePointerQuery ? finePointerQuery.matches : false;
    if (reduced) {
      root.classList.add("motion-reduced");
      for (const element of select(document, REVEAL_SELECTOR)) revealElement(element);
    } else if (typeof IntersectionObserver === "function" && typeof requestAnimationFrame === "function") {
      revealObserver = new IntersectionObserver((entries) => {
        try {
          for (const entry of entries) {
            if (!entry.isIntersecting) continue;
            revealElement(entry.target);
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
    } else {
      for (const element of select(document, REVEAL_SELECTOR)) revealElement(element);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    document.addEventListener("visibilitychange", onVisibilityChange);
    refresh();
  } catch (error) {
    failOpen();
  }

  window.MotionSystem = { refresh, destroy, setNumber };
})();
