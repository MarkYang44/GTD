(() => {
  'use strict';

  function init() {
    const root = document.documentElement;
    const toolbar = document.getElementById('lmu-tools');
    if (!root.classList.contains('lmu-page') || !toolbar) return;
    const byId = id => document.getElementById(id);
    const search = byId('lmu-search');
    const classFilter = byId('lmu-class');
    const carFilter = byId('lmu-car');
    const favoriteFilter = byId('lmu-favorites');
    const reset = byId('lmu-reset');
    const results = byId('lmu-results');
    const empty = byId('lmu-empty');
    const storageNote = byId('lmu-storage-note');
    const bar = byId('lmu-compare-bar');
    const selection = byId('lmu-selection');
    const openCompare = byId('lmu-open-compare');
    const feedback = byId('lmu-compare-feedback');
    const dialog = byId('lmu-compare-dialog');
    const grid = byId('lmu-compare-grid');
    const catalog = toolbar.dataset.mode === 'cars';
    const cards = Array.from(document.querySelectorAll('article.circuit-card'));
    const recommendations = new Map();
    const circuitSlugs = new Set((toolbar.dataset.circuitSlugs || '').split(' ').filter(Boolean));
    const carSlugs = new Set((toolbar.dataset.carSlugs || '').split(' ').filter(Boolean));
    const tr = (zh, en) => root.dataset.guideLanguage === 'en' ? en : zh;
    const normalize = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
    const selected = new Set();
    const storageKey = 'gtd_lmu_favorites_v1';
    let favorites = {circuits: [], cars: []};
    let storageUnavailable = false;
    let limitReached = false;
    let returnFocus = null;

    cards.forEach(card => {
      if (card.dataset.circuit) circuitSlugs.add(card.dataset.circuit);
      card.querySelectorAll('li.recommendation[data-key]').forEach(node => {
        carSlugs.add(node.dataset.car);
        recommendations.set(node.dataset.key, {node, card});
      });
    });

    function parseFavorites(value) {
      let parsed;
      try { parsed = JSON.parse(value); } catch (_) { parsed = null; }
      return {
        circuits: Array.isArray(parsed?.circuits) ? [...new Set(parsed.circuits.filter(slug => circuitSlugs.has(slug)))] : [],
        cars: Array.isArray(parsed?.cars) ? [...new Set(parsed.cars.filter(slug => carSlugs.has(slug)))] : [],
      };
    }

    function translateOptions() {
      toolbar.querySelectorAll('option[data-i18n-text-zh]').forEach(option => {
        option.textContent = tr(option.dataset.i18nTextZh, option.dataset.i18nTextEn);
      });
    }

    function renderStorageNote() {
      storageNote.hidden = !storageUnavailable;
      storageNote.textContent = tr('浏览器无法保存收藏；本次浏览仍可使用收藏。', 'Favorites cannot be saved in this browser; they still work for this visit.');
    }

    try {
      favorites = parseFavorites(window.localStorage.getItem(storageKey));
    } catch (_) {
      storageUnavailable = true;
    }

    function saveFavorites() {
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(favorites));
        storageUnavailable = false;
      } catch (_) {
        storageUnavailable = true;
      }
      renderStorageNote();
    }

    function carName(item) {
      return item.node.querySelector('h4').textContent.trim();
    }

    function contextName(item) {
      return catalog ? `${carName(item)} · ${item.node.dataset.class}` : `${item.card.dataset.name} · ${carName(item)} · ${item.node.dataset.class}`;
    }

    function renderActions() {
      document.querySelectorAll('[data-favorite-circuit], [data-favorite-car]').forEach(button => {
        const circuit = button.hasAttribute('data-favorite-circuit');
        const slug = circuit ? button.dataset.favoriteCircuit : button.dataset.favoriteCar;
        const active = favorites[circuit ? 'circuits' : 'cars'].includes(slug);
        const label = active ? tr('取消收藏', 'Remove favorite') : tr('收藏', 'Favorite');
        button.textContent = active ? '★' : '☆';
        button.setAttribute('aria-pressed', String(active));
        button.title = label;
        const name = circuit ? button.closest('.circuit-card').dataset.name : carName(recommendations.get(button.closest('[data-key]').dataset.key));
        button.setAttribute('aria-label', `${label}: ${name}`);
      });
      document.querySelectorAll('[data-compare]').forEach(button => {
        const active = selected.has(button.dataset.compare);
        button.setAttribute('aria-pressed', String(active));
        button.textContent = active ? tr('移出对比', 'Remove from comparison') : tr('加入对比', 'Add to comparison');
      });
    }

    function filterCards() {
      const previousFocus = document.activeElement?.closest('.circuit-card') ? document.activeElement : null;
      document.dispatchEvent(new CustomEvent('gtd:lmu-filterchange'));
      const query = normalize(search.value);
      let circuitCount = 0;
      let recommendationCount = 0;
      cards.forEach(card => {
        const circuitMatches = normalize(card.dataset.search || card.dataset.name).includes(query)
          && (favoriteFilter.value !== 'circuits' || favorites.circuits.includes(card.dataset.circuit));
        let visible = 0;
        card.querySelectorAll('li.recommendation[data-key]').forEach(node => {
          const matches = circuitMatches
            && (!classFilter.value || classFilter.value === node.dataset.class)
            && (!carFilter.value || carFilter.value === node.dataset.car)
            && (favoriteFilter.value !== 'cars' || favorites.cars.includes(node.dataset.car));
          node.hidden = !matches;
          if (matches) visible += 1;
        });
        card.querySelectorAll('.recommendation-group').forEach(group => {
          group.hidden = !Array.from(group.querySelectorAll('li.recommendation[data-key]')).some(node => !node.hidden);
        });
        card.hidden = visible === 0;
        if (visible) circuitCount += 1;
        recommendationCount += visible;
      });
      results.textContent = catalog ? tr(`${circuitCount} 台车型`, `${circuitCount} cars`) : tr(`${circuitCount} 条赛道 · ${recommendationCount} 条推荐`, `${circuitCount} circuits · ${recommendationCount} recommendations`);
      empty.hidden = circuitCount !== 0;
      if (previousFocus && !previousFocus.getClientRects().length) favoriteFilter.focus();
    }

    function updateCarOptions() {
      Array.from(carFilter.options).forEach(option => {
        option.disabled = !!(option.value && classFilter.value && option.dataset.class !== classFilter.value);
      });
      if (carFilter.selectedOptions[0]?.disabled) carFilter.value = '';
    }

    function removeButton(key) {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.removeCompare = key;
      button.textContent = tr('移除', 'Remove');
      button.setAttribute('aria-label', `${tr('移除', 'Remove')}: ${contextName(recommendations.get(key))}`);
      return button;
    }

    function renderDialog() {
      const focusedKey = dialog.contains(document.activeElement) ? document.activeElement.dataset.removeCompare : null;
      grid.replaceChildren();
      selected.forEach(key => {
        const item = recommendations.get(key);
        const article = document.createElement('article');
        article.className = 'lmu-compare-card';
        const context = document.createElement('p');
        context.className = 'lmu-compare-context';
        context.textContent = catalog ? item.node.dataset.class : `${item.card.dataset.name} · ${item.node.dataset.class}`;
        article.append(context);
        Array.from(item.node.children).forEach(child => {
          if (child.matches('.lmu-card-actions, [data-lmu-enhance]')) return;
          const clone = child.cloneNode(true);
          clone.removeAttribute('id');
          clone.querySelectorAll('.lmu-card-actions, [data-lmu-enhance]').forEach(node => node.remove());
          clone.querySelectorAll('[id]').forEach(node => node.removeAttribute('id'));
          article.append(clone);
        });
        article.append(removeButton(key));
        grid.append(article);
      });
      if (focusedKey) {
        const target = Array.from(grid.querySelectorAll('[data-remove-compare]')).find(button => button.dataset.removeCompare === focusedKey);
        (target || grid.querySelector('[data-remove-compare]') || byId('lmu-close-compare')).focus();
      }
    }

    function restoreFocus() {
      const candidate = returnFocus;
      returnFocus = null;
      if (candidate?.isConnected && !candidate.disabled && candidate.getClientRects().length) {
        candidate.focus();
      } else {
        (selection.querySelector('button') || reset).focus();
      }
    }

    function renderComparison() {
      const focusedKey = selection.contains(document.activeElement) ? document.activeElement.dataset.removeCompare : null;
      selection.replaceChildren();
      selected.forEach(key => {
        const li = document.createElement('li');
        const name = document.createElement('span');
        name.textContent = contextName(recommendations.get(key));
        li.append(name, removeButton(key));
        selection.append(li);
      });
      bar.hidden = selected.size === 0;
      root.classList.toggle('has-lmu-comparison', selected.size > 0);
      openCompare.textContent = tr(`并排对比 (${selected.size}/3)`, `Compare (${selected.size}/3)`);
      openCompare.disabled = selected.size < 2;
      feedback.textContent = limitReached
        ? tr('最多对比 3 项，请先移除一项。', 'Compare up to 3 items. Remove one before adding another.')
        : tr(`已选 ${selected.size}/3 项，至少选择 2 项开始对比。`, `${selected.size}/3 items selected. Select at least 2 to compare.`);
      if (dialog.open && selected.size < 2) {
        dialog.close();
      } else if (dialog.open) {
        renderDialog();
      }
      if (focusedKey) {
        const target = Array.from(selection.querySelectorAll('button')).find(button => button.dataset.removeCompare === focusedKey);
        (target || selection.querySelector('button') || reset).focus();
      }
      renderActions();
    }

    function changeSelection(key, removeOnly = false) {
      if (!recommendations.has(key)) return;
      limitReached = false;
      if (selected.has(key)) selected.delete(key);
      else if (!removeOnly && selected.size < 3) selected.add(key);
      else if (!removeOnly) limitReached = true;
      renderComparison();
    }

    document.addEventListener('click', event => {
      const button = event.target.closest('button');
      if (!button) return;
      if (button.hasAttribute('data-favorite-circuit') || button.hasAttribute('data-favorite-car')) {
        const circuit = button.hasAttribute('data-favorite-circuit');
        const type = circuit ? 'circuits' : 'cars';
        const slug = circuit ? button.dataset.favoriteCircuit : button.dataset.favoriteCar;
        if (!(circuit ? circuitSlugs : carSlugs).has(slug)) return;
        favorites[type] = favorites[type].includes(slug) ? favorites[type].filter(value => value !== slug) : [...favorites[type], slug];
        saveFavorites();
        renderActions();
        filterCards();
        if (!button.getClientRects().length) favoriteFilter.focus();
      } else if (button.hasAttribute('data-compare')) {
        changeSelection(button.dataset.compare);
      } else if (button.hasAttribute('data-remove-compare')) {
        changeSelection(button.dataset.removeCompare, true);
      }
    });

    search.addEventListener('input', filterCards);
    classFilter.addEventListener('change', () => { updateCarOptions(); filterCards(); });
    carFilter.addEventListener('change', filterCards);
    favoriteFilter.addEventListener('change', filterCards);
    reset.addEventListener('click', () => {
      search.value = '';
      classFilter.value = '';
      carFilter.value = '';
      favoriteFilter.value = '';
      updateCarOptions();
      filterCards();
    });
    byId('lmu-clear-compare').addEventListener('click', () => {
      selected.clear();
      limitReached = false;
      renderComparison();
      if (!dialog.open) reset.focus();
    });
    openCompare.addEventListener('click', () => {
      if (selected.size < 2 || dialog.open) return;
      returnFocus = document.activeElement;
      renderDialog();
      dialog.showModal();
      byId('lmu-close-compare').focus();
    });
    byId('lmu-close-compare').addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', restoreFocus);
    window.addEventListener('storage', event => {
      if (event.key !== storageKey && event.key !== null) return;
      try {
        if (event.storageArea && event.storageArea !== window.localStorage) return;
      } catch (_) { return; }
      favorites = parseFavorites(event.newValue);
      renderActions();
      filterCards();
    });
    window.addEventListener('pageshow', event => {
      if (!event.persisted) return;
      try {
        favorites = parseFavorites(window.localStorage.getItem(storageKey));
      } catch (_) { storageUnavailable = true; }
      renderStorageNote();
      renderActions();
      filterCards();
    });
    document.addEventListener('gtd:languagechange', () => {
      translateOptions();
      renderStorageNote();
      renderComparison();
      filterCards();
    });

    translateOptions();
    toolbar.hidden = false;
    document.querySelectorAll('[data-lmu-enhance]').forEach(node => { node.hidden = false; });
    renderStorageNote();
    updateCarOptions();
    renderComparison();
    filterCards();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
