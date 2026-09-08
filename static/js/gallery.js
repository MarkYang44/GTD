(() => {
  'use strict';
  const gallery = document.querySelector('.gallery');
  const track = gallery?.querySelector('.gallery-grid');
  if (!track) return;
  const slides = Array.from(track.querySelectorAll('.shot'));
  if (slides.length < 2) return;
  let current = 0;
  let frame = 0;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const controls = document.createElement('div');
  controls.className = 'gallery-controls';
  const button = (text, zh, en) => {
    const node = document.createElement('button');
    node.type = 'button';
    node.textContent = text;
    node.dataset.i18nAriaLabelZh = zh;
    node.dataset.i18nAriaLabelEn = en;
    node.setAttribute('aria-controls', track.id);
    return node;
  };
  const previous = button('‹', '上一张', 'Previous image');
  const next = button('›', '下一张', 'Next image');
  const dots = document.createElement('div');
  dots.className = 'gallery-dots';
  const count = document.createElement('span');
  count.className = 'gallery-count';
  count.setAttribute('aria-live', 'polite');
  count.setAttribute('aria-atomic', 'true');
  const dotButtons = slides.map((slide, index) => {
    const dot = button('', `查看第 ${index + 1} 张图片`, `View image ${index + 1}`);
    dot.addEventListener('click', () => go(index));
    dots.append(dot);
    return dot;
  });
  controls.append(previous, dots, next, count);
  gallery.append(controls);
  function update() {
    previous.disabled = current === 0;
    next.disabled = current === slides.length - 1;
    dotButtons.forEach((dot, index) => dot.setAttribute('aria-current', String(index === current)));
    const value = `${current + 1} / ${slides.length}`;
    if (count.textContent !== value) count.textContent = value;
  }
  function go(index, instant = false) {
    current = Math.max(0, Math.min(slides.length - 1, index));
    track.scrollTo({left: current * track.clientWidth, behavior: instant || reduced.matches ? 'instant' : 'smooth'});
    update();
  }
  previous.addEventListener('click', () => go(current - 1));
  next.addEventListener('click', () => go(current + 1));
  track.addEventListener('keydown', event => {
    const targets = {ArrowLeft: current - 1, ArrowRight: current + 1, Home: 0, End: slides.length - 1};
    if (!(event.key in targets)) return;
    event.preventDefault();
    go(targets[event.key]);
  });
  track.addEventListener('scroll', () => {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      current = Math.max(0, Math.min(slides.length - 1, Math.round(track.scrollLeft / track.clientWidth)));
      update();
    });
  }, {passive: true});
  new ResizeObserver(() => go(current, true)).observe(track);
  function language() {
    const en = document.documentElement.dataset.guideLanguage === 'en';
    controls.querySelectorAll('button').forEach(node => node.setAttribute('aria-label', en ? node.dataset.i18nAriaLabelEn : node.dataset.i18nAriaLabelZh));
  }
  document.addEventListener('gtd:languagechange', language);
  language();
  update();
})();
