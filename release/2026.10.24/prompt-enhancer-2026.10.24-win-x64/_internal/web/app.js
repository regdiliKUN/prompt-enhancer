/* 提示词增强器 - 前端逻辑（原生 JS，无构建、无外部依赖） */

const els = {};
const state = {
  cfg: {},
  presets: [],
  preset: 'general',
  models: [],
  model: '',
  api: '',
  busy: false,
  lastSource: '',
  controller: null,
  timer: null,
  scBusy: false,
  splitRatio: 0.5,
};

const $ = (id) => document.getElementById(id);

function init() {
  [
    'statusPill', 'statusText', 'presets', 'modelSelect', 'temperature', 'maxTokens',
    'input', 'output', 'inCount', 'outMeta', 'outHint', 'extra', 'extraToggle',
    'btnOptimize', 'btnClearIn', 'btnClearOut', 'btnCompare', 'btnIterate', 'btnCopy',
    'historyDrawer', 'settingsDrawer', 'btnHistory', 'btnSettings', 'btnCloseHistory',
    'btnCloseSettings', 'historySearch', 'historyList', 'btnClearHistory',
    'cfgEndpoint', 'cfgApi', 'cfgTimeout', 'cfgModel', 'cfgApiKey', 'cfgSystem',
    'btnTestConn', 'testResult', 'modelHints', 'btnResetSystem', 'btnSaveConfig',
    'diffModal', 'diffBody', 'btnCloseDiff', 'scrim', 'toast',
    'btnShortcut', 'btnShortcutText', 'scBanner', 'scBannerText', 'btnBannerCreate',
    'btnBannerHide', 'splitter',
  ].forEach((id) => { els[id] = $(id); });

  bindEvents();
  loadConfig().catch((e) => {
    // 页面先于后端就绪（如程序还在启动中）：给出提示并自动重试
    setStatus('err', friendlyFetchError(e) + '；稍后自动重试…');
    setTimeout(() => loadConfig().catch(() => {}), 3000);
  });
}

/* ------------------------------------------------------------------ 事件 */
function bindEvents() {
  els.btnOptimize.addEventListener('click', () => optimize());
  els.btnClearIn.addEventListener('click', () => { els.input.value = ''; updateCount(); saveUiStateDebounced(); els.input.focus(); });
  els.btnClearOut.addEventListener('click', () => { els.output.value = ''; els.outMeta.textContent = '等待优化'; });
  els.btnCopy.addEventListener('click', () => {
    if (!els.output.value.trim()) return toast('结果为空，无可复制内容');
    copyText(els.output.value);
  });
  els.btnIterate.addEventListener('click', () => {
    if (!els.output.value.trim()) return toast('当前没有可迭代优化的结果');
    els.input.value = els.output.value.trim();
    els.output.value = '';
    updateCount();
    optimize();
  });
  els.btnCompare.addEventListener('click', showDiff);

  els.input.addEventListener('input', () => { updateCount(); saveUiStateDebounced(); });
  els.extraToggle.addEventListener('change', () => els.extra.classList.toggle('hidden', !els.extraToggle.checked));
  els.modelSelect.addEventListener('change', () => {
    state.model = els.modelSelect.value;
    persist({ model: state.model });
  });
  const persistParams = () => persist({
    temperature: parseFloat(els.temperature.value) || 0.3,
    max_tokens: parseInt(els.maxTokens.value, 10) || 1024,
  });
  els.temperature.addEventListener('change', persistParams);
  els.maxTokens.addEventListener('change', persistParams);

  els.btnHistory.addEventListener('click', () => { openDrawer('history'); loadHistory(); });
  els.btnSettings.addEventListener('click', () => { fillSettings(); openDrawer('settings'); });
  els.btnCloseHistory.addEventListener('click', closeDrawers);
  els.btnCloseSettings.addEventListener('click', closeDrawers);
  els.scrim.addEventListener('click', closeDrawers);
  els.btnClearHistory.addEventListener('click', async () => {
    if (!confirm('确定清空全部历史记录？该操作不可撤销。')) return;
    await fetch('/api/history', { method: 'DELETE' });
    loadHistory();
    toast('历史记录已清空');
  });
  els.historySearch.addEventListener('input', debounce(loadHistory, 220));
  els.btnCloseDiff.addEventListener('click', () => els.diffModal.classList.add('hidden'));
  els.diffModal.addEventListener('click', (e) => { if (e.target === els.diffModal) els.diffModal.classList.add('hidden'); });

  els.btnTestConn.addEventListener('click', testConnection);
  els.btnResetSystem.addEventListener('click', async () => {
    const r = await (await fetch('/api/system-template/default')).json();
    els.cfgSystem.value = r.system_template;
    toast('已恢复默认优化规则模板');
  });
  els.btnSaveConfig.addEventListener('click', saveConfig);

  /* 一键启动 / 桌面快捷方式 */
  els.btnShortcut.addEventListener('click', () => createShortcut(true));
  els.btnBannerCreate.addEventListener('click', () => createShortcut(true));
  els.btnBannerHide.addEventListener('click', () => els.scBanner.classList.add('hidden'));

  /* 界面 / 窗口状态持久化 */
  initSplitter();
  els.extra.addEventListener('input', saveUiStateDebounced);
  els.extraToggle.addEventListener('change', saveUiStateDebounced);
  window.addEventListener('resize', debounce(persistStateNow, 800));
  window.addEventListener('beforeunload', () => {
    try {
      navigator.sendBeacon('/api/state',
        new Blob([JSON.stringify({ state: collectState() })], { type: 'application/json' }));
    } catch (_) { /* 忽略 */ }
  });

  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); optimize(); }
    if (e.key === 'Escape') { closeDrawers(); els.diffModal.classList.add('hidden'); }
  });
}

/* ------------------------------------------------------------------ 配置 */
async function loadConfig() {
  const cfg = await (await fetch('/api/config')).json();
  state.cfg = cfg;
  state.presets = cfg._presets || [];
  state.model = cfg.model || '';
  els.temperature.value = cfg.temperature;
  els.maxTokens.value = cfg.max_tokens;
  renderPresets(cfg._presets || []);
  await loadUiState();
  probeModels();
  refreshShortcut();
}

/* ------------------------------------------------- 一键启动 / 桌面快捷方式 */
async function refreshShortcut() {
  try {
    const r = await (await fetch('/api/shortcut')).json();
    updateShortcutUI(r);
  } catch (_) { /* 后端未就绪时忽略，probeModels 会统一提示 */ }
}

function updateShortcutUI(r) {
  if (r.status === 'name_taken' || (r.exists && !r.owned)) {
    // 桌面上有同名但非本产品创建的快捷方式：入口保留，横幅给出解释
    els.scBanner.classList.remove('hidden');
    els.scBannerText.textContent = r.message ||
      '桌面已有同名快捷方式，但它不是本程序创建的，本程序不会改动它。';
    els.btnShortcutText.textContent = '一键启动（桌面快捷方式被同名文件占用）';
    return;
  }
  if (r.exists && r.owned && !r.matches && r.target_valid) {
    // 本程序创建、但指向另一个可用安装（如同时装了包体和源码目录）：入口保留、不覆盖
    els.scBanner.classList.add('hidden');
    els.btnShortcutText.textContent = '一键启动（桌面图标指向另一个安装，不会覆盖）';
  } else if (r.exists && r.matches) {
    els.scBanner.classList.add('hidden');
    els.btnShortcutText.textContent = '一键启动（桌面快捷方式已就绪）';
  } else {
    els.scBanner.classList.remove('hidden');
    els.scBannerText.textContent = r.message ||
      '桌面快捷方式尚未创建 —— 点击右上角「一键启动」即可在桌面创建快捷方式并启动程序。';
    els.btnShortcutText.textContent = '一键启动 · 创建桌面快捷方式';
  }
}

async function createShortcut(launch) {
  if (state.scBusy) return;
  state.scBusy = true;
  els.btnShortcut.disabled = true;
  els.btnShortcutText.textContent = '正在创建…';
  // 加超时，避免后端无响应时按钮一直卡在「正在创建…」
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 90000);
  try {
    const res = await fetch('/api/shortcut', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ create: true, launch: !!launch }),
      signal: ctrl.signal,
    });
    const r = await res.json();
    if (r.status === 'created') toast('已创建：' + r.message);
    else if (r.status === 'updated') toast('已更新：' + r.message);
    else if (r.status === 'exists') toast('快捷方式已存在，未重复创建');
    else if (r.status === 'exists_other') toast('桌面已有本应用的快捷方式（指向其他位置），未做改动');
    else if (r.status === 'name_taken') toast('桌面已有同名快捷方式但非本程序创建，为保护你的快捷方式未做改动');
    else if (r.status === 'failed') toast('创建失败：' + r.message);
    else toast(r.message || '操作完成');
    if (r.launch) {
      if (r.launch.ok) toast(r.launch.message);
      else toast(r.launch.message || '启动失败，请手动双击桌面快捷方式');
    }
  } catch (e) {
    toast(e.name === 'AbortError'
      ? '创建超时：桌面快捷方式操作未在预期时间内完成，可稍后重试或手动创建'
      : '创建失败：' + friendlyFetchError(e));
  } finally {
    clearTimeout(timer);
    state.scBusy = false;
    els.btnShortcut.disabled = false;
    refreshShortcut();
  }
}

/* ------------------------------------------------- 界面 / 窗口状态持久化 */
async function loadUiState() {
  try {
    const r = await (await fetch('/api/state')).json();
    const s = r.state || {};
    if (s.preset && state.presets.some((p) => p.key === s.preset)) {
      state.preset = s.preset;
      renderPresets(state.presets);
    }
    if (typeof s.split_ratio === 'number') applySplit(s.split_ratio);
    if (s.extra) els.extra.value = s.extra;
    if (s.extra_enabled) {
      els.extraToggle.checked = true;
      els.extra.classList.remove('hidden');
    }
    if (s.draft) {
      els.input.value = s.draft;
      updateCount();
    }
  } catch (_) { /* 忽略 */ }
}

function collectState() {
  return {
    preset: state.preset,
    extra: els.extra.value.slice(0, 2000),
    extra_enabled: els.extraToggle.checked,
    split_ratio: state.splitRatio,
    draft: els.input.value.slice(0, 8000),
    window: {
      w: window.innerWidth, h: window.innerHeight,
      x: window.screenX, y: window.screenY,
      dpr: window.devicePixelRatio,
    },
  };
}

let stateSaveTimer = null;
function saveUiStateDebounced() {
  clearTimeout(stateSaveTimer);
  stateSaveTimer = setTimeout(persistStateNow, 500);
}

function persistStateNow() {
  fetch('/api/state', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ state: collectState() }),
  }).catch(() => {});
}

/* ------------------------------------------------- 左右分栏拖动 */
function applySplit(ratio) {
  if (typeof ratio !== 'number' || !isFinite(ratio)) return;
  state.splitRatio = Math.min(0.8, Math.max(0.2, ratio));
  if (window.innerWidth <= 900) return;
  const ws = els.splitter.parentElement;
  ws.style.gridTemplateColumns =
    (state.splitRatio * 100).toFixed(2) + 'fr 10px ' + ((1 - state.splitRatio) * 100).toFixed(2) + 'fr';
}

function initSplitter() {
  let dragging = false;
  els.splitter.addEventListener('mousedown', (e) => {
    dragging = true;
    els.splitter.classList.add('active');
    e.preventDefault();
  });
  window.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const ws = els.splitter.parentElement;
    const rect = ws.getBoundingClientRect();
    const usable = rect.width - 10 - 36; // 减去分栏宽度与左右内边距
    if (usable <= 0) return;
    applySplit((e.clientX - rect.left - 18 - 5) / usable);
  });
  window.addEventListener('mouseup', () => {
    if (dragging) {
      dragging = false;
      els.splitter.classList.remove('active');
      saveUiStateDebounced();
    }
  });
}

let probeFailCount = 0;
let probeRetryTimer = null;

async function probeModels() {
  clearTimeout(probeRetryTimer);
  if (probeFailCount === 0) setStatus('busy', '正在检测推理服务…');
  try {
    const r = await (await fetch('/api/models')).json();
    probeFailCount = 0;
    state.api = r.api || '';
    if (r.ok) {
      state.models = r.models || [];
      if (!state.model && state.models.length) state.model = state.models[0];
      renderModelOptions();
      setStatus('ok', `模型就绪：${state.model || '未选择'}`);
    } else {
      state.models = [];
      renderModelOptions();
      setStatus('err', '模型未就绪：' + r.message);
    }
  } catch (e) {
    // 到这一步说明连本工具自己的后端都访问不到（程序已退出 / 正在重启），
    // 与推理服务无关；指数退避自动重试，后端恢复后状态会自动变回就绪。
    probeFailCount += 1;
    setStatus('err', '无法连接本工具的后端服务（程序可能已退出或正在重启），请重新启动提示词增强器；将自动重试…');
    const delay = Math.min(30000, 2000 * Math.pow(2, probeFailCount - 1));
    probeRetryTimer = setTimeout(probeModels, delay);
  }
}

function renderModelOptions() {
  const list = state.models.slice();
  if (state.model && !list.includes(state.model)) list.unshift(state.model);
  els.modelSelect.innerHTML = list.length
    ? list.map((m) => `<option value="${esc(m)}"${m === state.model ? ' selected' : ''}>${esc(m)}</option>`).join('')
    : '<option value="">未检测到模型</option>';
  els.modelSelect.value = state.model || '';
}

function renderPresets(presets) {
  els.presets.innerHTML = presets.map((p) => {
    const active = p.key === state.preset ? ' active' : '';
    return `<button class="chip${active}" data-key="${p.key}" title="${esc(p.desc)}">${esc(p.name)}</button>`;
  }).join('');
  els.presets.querySelectorAll('.chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      state.preset = chip.dataset.key;
      renderPresets(state.presets);
      saveUiStateDebounced();
    });
  });
}

/* ------------------------------------------------------------------ 状态 */
function friendlyFetchError(e) {
  // 浏览器 fetch 的网络层错误信息是英文原文（如 "Failed to fetch"），翻译成可读提示。
  // 注意：这类错误表示「页面连不上本工具自己的后端服务」，与推理服务是否在线无关。
  const msg = (e && e.message) || '';
  if (e && e.name === 'AbortError') return '请求超时';
  if (/failed to fetch|networkerror|load failed/i.test(msg)) {
    return '无法连接本工具的后端服务（程序可能已退出或正在重启），请重新启动提示词增强器';
  }
  return msg || '未知错误';
}

function setStatus(kind, text) {
  els.statusPill.className = 'pill pill-' + kind;
  els.statusText.textContent = text;
}

let toastTimer = null;
function toast(msg) {
  els.toast.textContent = msg;
  els.toast.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => els.toast.classList.add('hidden'), 2200);
}

function updateCount() {
  els.inCount.textContent = `${els.input.value.length} 字`;
}

/* ------------------------------------------------------------------ 优化 */
async function optimize() {
  if (state.busy) { stopOptimize(); return; }
  const raw = els.input.value.trim();
  if (!raw) return toast('请先输入需要优化的原始提示词');
  if (!state.model) {
    toast('尚未选择模型，请在设置中连接推理服务并选择模型');
    fillSettings();
    openDrawer('settings');
    return;
  }

  state.busy = true;
  state.lastSource = raw;
  els.output.value = '';
  els.btnOptimize.innerHTML = '停止生成';
  setStatus('busy', '推理中…');
  els.outMeta.textContent = '生成中…';

  const started = performance.now();
  const tick = setInterval(() => {
    els.outMeta.textContent = `模型加载 / 生成中… ${((performance.now() - started) / 1000).toFixed(1)}s`;
  }, 300);

  state.controller = new AbortController();
  try {
    const res = await fetch('/api/optimize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: raw,
        preset: state.preset,
        extra: els.extraToggle.checked ? els.extra.value : '',
        model: state.model,
        temperature: parseFloat(els.temperature.value),
        max_tokens: parseInt(els.maxTokens.value, 10),
      }),
      signal: state.controller.signal,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ message: '请求失败' }));
      throw new Error(err.message || '请求失败');
    }

    await readSSE(res, {
      onMeta: (d) => { state.api = d.api; },
      onStatus: (d) => { els.outMeta.textContent = d.text; },
      onDelta: (d) => {
        els.output.value += d.text;
        els.output.scrollTop = els.output.scrollHeight;
      },
      onDone: (d) => {
        if (!els.output.value.trim()) els.output.value = d.text || '';
        const secs = ((performance.now() - started) / 1000).toFixed(1);
        els.outMeta.textContent = `${d.model} · 耗时 ${secs}s${d.history_id ? ' · 已存入历史' : ''}`;
      },
      onError: (d) => { throw new Error(d.message); },
    });
    setStatus('ok', `模型就绪：${state.model}`);
  } catch (e) {
    if (e.name === 'AbortError') {
      els.outMeta.textContent = '已手动停止';
      setStatus('ok', `模型就绪：${state.model}`);
    } else {
      els.outMeta.textContent = '优化失败';
      const msg = friendlyFetchError(e);
      els.outMeta.textContent = /后端服务/.test(msg) ? '后端服务未连接' : '优化失败';
      setStatus('err', '推理失败：' + msg);
      toast(msg);
    }
  } finally {
    clearInterval(tick);
    state.busy = false;
    state.controller = null;
    els.btnOptimize.innerHTML = '一键优化 <kbd>Ctrl+Enter</kbd>';
  }
}

function stopOptimize() {
  if (state.controller) state.controller.abort();
}

async function readSSE(res, handlers) {
  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = 'message';
      const dataLines = [];
      block.split('\n').forEach((line) => {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
      });
      if (!dataLines.length) continue;
      let payload = {};
      try { payload = JSON.parse(dataLines.join('\n')); } catch (_) { continue; }
      if (event === 'delta' && handlers.onDelta) handlers.onDelta(payload);
      else if (event === 'status' && handlers.onStatus) handlers.onStatus(payload);
      else if (event === 'meta' && handlers.onMeta) handlers.onMeta(payload);
      else if (event === 'done' && handlers.onDone) handlers.onDone(payload);
      else if (event === 'error' && handlers.onError) handlers.onError(payload);
    }
  }
}

/* ------------------------------------------------------------------ 对比 */
function showDiff() {
  const before = state.lastSource || '';
  const after = els.output.value;
  if (!before || !after) return toast('需要有一次优化结果与对应原文才能对比');
  const a = before.split('\n');
  const b = after.split('\n');
  const diffs = diffLines(a, b);
  const add = diffs.filter((d) => d[0] === 'add').length;
  const del = diffs.filter((d) => d[0] === 'del').length;
  const html = diffs.map(([kind, text]) => {
    if (kind === 'add') return `<div class="diff-line diff-add">+ ${esc(text)}</div>`;
    if (kind === 'del') return `<div class="diff-line diff-del">- ${esc(text)}</div>`;
    return `<div class="diff-line diff-eq">  ${esc(text)}</div>`;
  }).join('');
  els.diffBody.innerHTML =
    `<div class="diff-stat">新增 ${add} 行 / 删除 ${del} 行 · 「-」为原文，「+」为优化后</div>` + html;
  els.diffModal.classList.remove('hidden');
}

function diffLines(a, b) {
  const n = a.length, m = b.length;
  const dp = [];
  for (let i = 0; i <= n; i++) dp.push(new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const out = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { out.push(['eq', a[i]]); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push(['del', a[i]]); i++; }
    else { out.push(['add', b[j]]); j++; }
  }
  while (i < n) out.push(['del', a[i++]]);
  while (j < m) out.push(['add', b[j++]]);
  return out;
}

/* ------------------------------------------------------------------ 历史 */
async function loadHistory() {
  const q = els.historySearch.value.trim();
  const r = await (await fetch('/api/history?q=' + encodeURIComponent(q))).json();
  const items = r.items || [];
  if (!items.length) {
    els.historyList.innerHTML = '<div class="empty">暂无记录</div>';
    return;
  }
  els.historyList.innerHTML = items.map((it) => {
    const time = esc(it.created_at || '');
    const tag = esc(it.preset || '通用');
    const model = esc(it.model || '');
    const src = esc((it.source || '').slice(0, 220));
    const res = esc((it.result || '').slice(0, 260));
    return `<div class="hist" data-id="${it.id}">
      <div class="hist-top"><span>${time}</span><span class="tag">${tag}</span><span>${model}</span></div>
      <div class="label">原文</div><pre>${src}</pre>
      <div class="label">优化结果</div><pre>${res}</pre>
      <div class="hist-actions">
        <button class="btn tiny" data-act="source">复用原文</button>
        <button class="btn tiny" data-act="result">复用结果</button>
        <button class="btn tiny ghost" data-act="delete">删除</button>
      </div>
    </div>`;
  }).join('');

  els.historyList.querySelectorAll('.hist').forEach((node) => {
    const id = node.dataset.id;
    node.querySelectorAll('button[data-act]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const item = items.find((x) => String(x.id) === id);
        const act = btn.dataset.act;
        if (act === 'source') { els.input.value = item.source || ''; updateCount(); closeDrawers(); toast('原文已载入输入区'); }
        else if (act === 'result') { els.output.value = item.result || ''; closeDrawers(); toast('结果已载入输出区'); }
        else if (act === 'delete') {
          await fetch('/api/history/' + id, { method: 'DELETE' });
          loadHistory();
        }
      });
    });
  });
}

/* ------------------------------------------------------------------ 设置 */
function openDrawer(which) {
  closeDrawers();
  const el = which === 'history' ? els.historyDrawer : els.settingsDrawer;
  el.classList.add('open');
  els.scrim.classList.remove('hidden');
}

function closeDrawers() {
  els.historyDrawer.classList.remove('open');
  els.settingsDrawer.classList.remove('open');
  els.scrim.classList.add('hidden');
}

function fillSettings() {
  const c = state.cfg;
  els.cfgEndpoint.value = c.endpoint || '';
  els.cfgApi.value = c.api || 'auto';
  els.cfgModel.value = c.model || '';
  els.cfgApiKey.value = c.api_key || '';
  els.cfgTimeout.value = c.timeout || 180;
  els.cfgSystem.value = c.system_template || '';
  els.testResult.textContent = '—';
  els.modelHints.innerHTML = '';
}

async function testConnection() {
  els.testResult.textContent = '检测中…';
  els.modelHints.innerHTML = '';
  try {
    const res = await fetch('/api/models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        endpoint: els.cfgEndpoint.value.trim(),
        api: els.cfgApi.value,
        timeout: parseFloat(els.cfgTimeout.value) || 6,
      }),
    });
    const r = await res.json();
    if (r.ok) {
      els.testResult.textContent = `已连接（${r.api === 'ollama' ? 'Ollama' : 'OpenAI 兼容'}），发现 ${r.models.length} 个模型`;
      els.modelHints.innerHTML = r.models.map((m) => `<button class="chip" data-m="${esc(m)}">${esc(m)}</button>`).join('');
      els.modelHints.querySelectorAll('.chip').forEach((chip) => {
        chip.addEventListener('click', () => { els.cfgModel.value = chip.dataset.m; });
      });
      if (!els.cfgModel.value.trim() && r.models.length) els.cfgModel.value = r.models[0];
    } else {
      els.testResult.textContent = '未就绪：' + r.message;
    }
  } catch (e) {
    els.testResult.textContent = '检测失败：' + e.message;
  }
}

async function persist(patch) {
  const r = await (await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })).json();
  Object.assign(state.cfg, r.config || patch);
}

async function saveConfig() {
  const body = {
    endpoint: els.cfgEndpoint.value.trim(),
    api: els.cfgApi.value,
    model: els.cfgModel.value.trim(),
    api_key: els.cfgApiKey.value.trim(),
    timeout: parseFloat(els.cfgTimeout.value) || 180,
    temperature: parseFloat(els.temperature.value),
    max_tokens: parseInt(els.maxTokens.value, 10),
    system_template: els.cfgSystem.value,
  };
  const r = await (await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })).json();
  Object.assign(state.cfg, r.config || body);
  state.model = body.model;
  renderModelOptions();
  await probeModels();
  toast('设置已保存');
}

/* ------------------------------------------------------------------ 工具 */
function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => toast('已复制到剪贴板'), () => fallbackCopy(text));
  } else {
    fallbackCopy(text);
  }
}

function fallbackCopy(text) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); toast('已复制到剪贴板'); } catch (_) { toast('复制失败，请手动选择复制'); }
  document.body.removeChild(ta);
}

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function debounce(fn, ms) {
  let t;
  return function (...args) { clearTimeout(t); t = setTimeout(() => fn.apply(this, args), ms); };
}

init();
