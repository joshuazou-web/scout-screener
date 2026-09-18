import { api } from './api.js';

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const LEVEL = { good: 'p-good', warn: 'p-warn', bad: 'p-bad', idle: 'p-idle' };
const L1_LABEL = { pass: '成立', unk: '待核实', fail: '不成立' };

const ui = (() => { try { return JSON.parse(localStorage.getItem('scout-ui')) || {}; } catch { return {}; } })();
const S = { C: null, items: [], sel: null, filter: ui.filter || '全部', tab: ui.tab || 'pool', suggest: {}, busy: false };
const cur = () => S.items.find((i) => i.id === S.sel);

function toast(msg, bad) {
  const t = $('#toast');
  t.textContent = msg; t.className = 'toast' + (bad ? ' bad' : ''); t.hidden = false;
  clearTimeout(toast.h); toast.h = setTimeout(() => (t.hidden = true), 3000);
}

async function persist(p) {
  try {
    const saved = await api.update(p);
    S.items = S.items.map((i) => (i.id === saved.id ? saved : i));
  } catch (e) { toast(e.message, true); }
  render();
}

// ---------- 项目池 ----------
function renderStats() {
  const n = S.items.length, c = (k) => S.items.filter((i) => i.final.stage === k).length;
  const l1 = S.items.filter((i) => S.C.l1.every((c) => i.l1[c.key].v === 'pass')).length;
  $('#stats').innerHTML = [['访谈', n], ['过第一层', l1], ['建议推荐', c('建议推荐')], ['已推荐', c('已推荐')]]
    .map(([k, v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`).join('');
}

const FILTERS = {
  '全部': () => true,
  '待处理': (s) => ['待补访谈', '复筛中', '建议推荐'].includes(s),
  '建议推荐': (s) => s === '建议推荐',
  '已推荐': (s) => s === '已推荐',
  '未通过': (s) => ['初筛未通过', '不推荐'].includes(s),
};

function renderList() {
  $('#filters').innerHTML = Object.keys(FILTERS)
    .map((f) => `<button class="chip" aria-pressed="${S.filter === f}" data-f="${f}">${f}</button>`).join('');
  const items = S.items.filter((i) => FILTERS[S.filter](i.final.stage));
  $('#list').innerHTML = items.length ? items.map((it) => `
    <button class="item" data-id="${it.id}" aria-current="${S.sel === it.id}">
      <span class="name"><span>${esc(it.name) || '未命名'}${it.example ? '<span class="ex">示例</span>' : ''}</span>
      <span class="pill ${LEVEL[it.final.level]}">${it.final.stage}</span></span>
      <span class="meta">${esc(it.track)} · ${esc(it.date)}${it.missing.length ? ` · <span class="warnx">缺证据 ${it.missing.length}</span>` : ''}</span>
    </button>`).join('') : '<div class="empty">这个筛选下没有项目</div>';
}

const seg = (attr, key, cur, opts) => `<div class="seg" role="group">${opts.map(([v, l, cls]) =>
  `<button class="${cls}" aria-pressed="${cur === v}" data-${attr}="${key}" data-v="${v}">${l}</button>`).join('')}</div>`;

function critRow(c, layer, it) {
  const s = it[layer][c.key];
  const control = layer === 'l1'
    ? seg('l1', c.key, s.v, [['pass', '成立', 'v-pass'], ['unk', '待核实', 'v-unk'], ['fail', '不成立', 'v-fail']])
    : seg('l2', c.key, s.v, [1, 2, 3, 4, 5].map((n) => [n, n, 'v-n']));
  const noEv = (layer === 'l1' ? s.v !== 'unk' : s.v > 0) && !s.e.trim();
  const anchors = c.anchors ? `<div class="q">${Object.entries(c.anchors).map(([k, v]) => `${k} 分：${esc(v)}`).join(' · ')}</div>` : '';
  return `<div class="crit"><div><div class="t">${c.title}${layer === 'l2' ? ` <span class="w">${Math.round(c.weight * 100)}%</span>` : ''}</div>
    <div class="q">${esc(c.question)}</div>${anchors}</div>
    <div>${control}${noEv ? '<span class="nodev">缺证据</span>' : ''}
    <textarea id="e-${c.key}" data-e="${layer}:${c.key}" placeholder="访谈原话 / 看到的材料">${esc(s.e)}</textarea></div></div>`;
}

function renderSuggest(it) {
  const sg = S.suggest[it.id];
  if (!sg) return '';
  const all = [...S.C.l1, ...S.C.l2];
  const fmt = (x) => (x.layer === 'l1' ? L1_LABEL[x.v] : x.v ? `${x.v} 分` : '未判断');
  return `<div class="suggest">
    <div class="note">${sg.mode === 'llm' ? 'AI 建议（引用已校验，均能在原文找到）' : '关键词候选句（未下判断）'}${sg.warning ? ` · ${esc(sg.warning)}` : ''}</div>
    ${all.map((c) => { const x = sg.items[c.key]; if (!x) return ''; return `
      <div class="sg-row"><b>${c.title}</b><span class="sg-v">${fmt(x)}</span>
      <span class="sg-q">${x.quote ? '“' + esc(x.quote) + '”' : '<i>无引用</i>'}${x.reason ? `<br><small>${esc(x.reason)}</small>` : ''}</span>
      <button class="btn small" data-adopt="${c.key}" ${x.quote ? '' : 'disabled'}>采纳</button></div>`; }).join('')}
    <div class="decide"><button class="btn small" data-adopt="*">全部采纳有引用的</button><button class="btn small" data-adopt="-">收起</button></div>
  </div>`;
}

function renderDetail() {
  const it = cur();
  if (!it) { $('#detail').innerHTML = '<div class="panel empty">左边选一个项目，或新建一条访谈记录</div>'; return; }
  const ev = it.eval;
  const field = (k, label, type = 'text') => `<label class="f">${label}<input id="f-${k}" type="${type}" data-field="${k}" value="${esc(it[k])}"></label>`;
  $('#detail').innerHTML = `<div class="panel">
    <div class="row">${field('name', '项目名')}${field('track', '赛道')}${field('stage', '阶段')}${field('contact', '来源')}${field('date', '访谈日期', 'date')}</div>
    <label class="f">一句话描述（给谁、解决什么、怎么收钱）<textarea id="f-pitch" data-field="pitch">${esc(it.pitch)}</textarea></label>

    <details class="tx" ${it.transcript ? 'open' : ''}><summary>访谈转写 · 用 AI 抽取证据</summary>
      <textarea id="f-transcript" data-field="transcript" placeholder="粘贴访谈速记或录音转写" style="min-height:110px">${esc(it.transcript)}</textarea>
      <div class="decide"><button class="btn" id="extract" ${S.busy ? 'disabled' : ''}>${S.busy ? '抽取中…' : '抽取证据'}</button>
      <span class="note">AI 只给建议，采纳后才写入下面的判断</span></div>
      ${renderSuggest(it)}
    </details>

    <div><h2>第一层 · 硬门槛 <small>任一项“不成立”直接淘汰</small></h2>${S.C.l1.map((c) => critRow(c, 'l1', it)).join('')}</div>
    <div><h2>第二层 · 打分 <small>加权 ≥ ${S.C.rec_line} 且每项 ≥ ${S.C.min_dim} 才建议推荐</small></h2>${S.C.l2.map((c) => critRow(c, 'l2', it)).join('')}</div>

    <div class="verdict">
      <div class="big">系统建议：<span class="pill ${LEVEL[ev.level]}">${ev.stage}</span>
        ${ev.total != null ? `<span class="score">${ev.total.toFixed(2)} / 5</span>` : ''}</div>
      <div class="why">${esc(ev.text)}${it.missing.length ? `<br>⚠ 以下判断还没有证据：${it.missing.join('、')}` : ''}</div>
      <div class="note">系统只给建议，推不推荐由你决定：</div>
      <div class="decide">
        <button class="btn primary" data-dec="rec" aria-pressed="${it.decision === 'rec'}">推荐给投资团队</button>
        <button class="btn" data-dec="hold" aria-pressed="${it.decision === 'hold'}">暂缓，继续跟进</button>
        <button class="btn" data-dec="no" aria-pressed="${it.decision === 'no'}">不推荐</button>
        ${it.decision ? '<button class="btn" data-dec="">撤销决定</button>' : ''}
        <button class="btn danger" id="del">删除记录</button>
      </div>
    </div></div>`;
}

// ---------- 其他页签 ----------
const bars = (rows, max, color) => `<div class="bars">${rows.map(([k, v]) =>
  `<div class="bar"><span>${esc(k)}</span><div class="track"><div class="fill" style="width:${(v / max) * 100}%;${color ? 'background:' + color : ''}"></div></div><span class="n">${v}</span></div>`).join('')}</div>`;

async function renderReview() {
  const r = await api.report();
  $('#v-review').innerHTML = `<div class="two">
    <div class="panel"><h2>筛选漏斗</h2>${bars(r.funnel, Math.max(1, r.funnel[0][1]))}</div>
    <div class="panel"><h2>未通过原因 <small>共 ${r.rejected} 个项目</small></h2>
      ${r.reasons.length ? bars(r.reasons, Math.max(...r.reasons.map((x) => x[1])), 'var(--bad)') : '<div class="empty">还没有未通过的项目</div>'}
      <div class="note">出现最多的原因，就是下一轮初筛时最先要问的问题。</div></div>
    <div class="panel"><h2>初筛清单 <small>可直接复制</small></h2><pre class="out">${esc(r.checklist)}</pre></div></div>`;
}

function renderTemplate() {
  const block = (c) => `<h3>${c.title}</h3><ol>${c.question.split('？').filter((s) => s.trim()).map((s) => `<li>${esc(s.trim())}？</li>`).join('')}</ol>`;
  $('#v-template').innerHTML = `<div class="panel tpl"><h2>访谈模板 <small>每个问题对应一条筛选标准，边问边记原话</small></h2>
    <h3>开场</h3><ol><li>用一句话说：你在帮谁解决什么问题？</li><li>你为什么是做这件事的人？</li></ol>
    ${[...S.C.l1, ...S.C.l2].map(block).join('')}
    <h3>收尾</h3><ol><li>接下来 4 周你打算验证什么？怎么算验证成功？</li><li>还能介绍哪位用户或同行给我聊聊？</li></ol></div>`;
}

async function renderData() {
  const all = await api.exportAll();
  $('#v-data').innerHTML = `<div class="panel"><h2>完整数据 JSON <small>也可以用命令行：python -m scout.cli export out.json</small></h2>
    <textarea id="json" class="mono" style="min-height:260px">${esc(JSON.stringify(all, null, 1))}</textarea>
    <div class="decide"><button class="btn primary" id="imp">用上面的 JSON 覆盖导入</button><button class="btn" id="reset">恢复示例数据</button></div></div>`;
}

function render() {
  try { localStorage.setItem('scout-ui', JSON.stringify({ tab: S.tab, filter: S.filter })); } catch {}
  renderStats();
  document.querySelectorAll('.tab').forEach((b) => b.setAttribute('aria-selected', b.dataset.tab === S.tab));
  ['pool', 'review', 'template', 'data'].forEach((t) => ($('#v-' + t).hidden = S.tab !== t));
  const run = { pool: () => { renderList(); renderDetail(); }, review: renderReview, template: renderTemplate, data: renderData }[S.tab];
  Promise.resolve(run()).catch((e) => toast(e.message, true));
}

async function reload() {
  S.items = await api.list();
  if (!cur()) S.sel = S.items[0]?.id ?? null;
  render();
}

// ---------- 交互 ----------
document.addEventListener('click', async (e) => {
  const t = e.target.closest('button');
  if (!t) return;
  const it = cur(), d = t.dataset;
  if (d.tab) { S.tab = d.tab; return render(); }
  if (d.f) { S.filter = d.f; return render(); }
  if (d.id) { S.sel = d.id; return render(); }
  if (d.l1 && it) { it.l1[d.l1].v = d.v; return persist(it); }
  if (d.l2 && it) { const v = +d.v; it.l2[d.l2].v = it.l2[d.l2].v === v ? 0 : v; return persist(it); }
  if (d.dec !== undefined && it) { it.decision = d.dec; return persist(it); }
  if (d.adopt && it) {
    const sg = S.suggest[it.id];
    if (d.adopt === '-') { delete S.suggest[it.id]; return render(); }
    const keys = d.adopt === '*' ? Object.keys(sg.items) : [d.adopt];
    keys.forEach((k) => { const x = sg.items[k]; if (!x?.quote) return;
      it[x.layer][k] = { v: sg.mode === 'llm' ? x.v : it[x.layer][k].v, e: x.quote }; });
    toast(`已采纳 ${keys.filter((k) => sg.items[k]?.quote).length} 条证据`);
    return persist(it);
  }
  try {
    if (t.id === 'add') {
      const p = await api.create({});
      S.items.unshift(p); S.sel = p.id; S.filter = '全部'; render(); $('#f-name')?.focus();
    } else if (t.id === 'del' && it && confirm(`删除「${it.name || '未命名'}」？`)) {
      await api.remove(it.id); S.sel = null; await reload();
    } else if (t.id === 'extract' && it) {
      it.transcript = $('#f-transcript').value;
      S.busy = true; render();
      try { S.suggest[it.id] = await api.extract(it.id, it.transcript); } finally { S.busy = false; }
      render();
    } else if (t.id === 'imp') {
      const r = await api.importAll(JSON.parse($('#json').value));
      toast(`已导入 ${r.count} 个项目`); S.sel = null; await reload();
    } else if (t.id === 'reset' && confirm('清空当前数据并恢复示例？')) {
      await api.resetSample(); toast('已恢复示例数据'); S.sel = null; await reload();
    }
  } catch (err) { S.busy = false; toast(err instanceof SyntaxError ? 'JSON 格式不对，检查后重试' : err.message, true); render(); }
});

// 打字时只改内存，失焦（change）时保存并重绘，避免输入框丢焦点
document.addEventListener('input', (e) => {
  const it = cur(), el = e.target;
  if (!it) return;
  if (el.dataset.field) it[el.dataset.field] = el.value;
  else if (el.dataset.e) { const [layer, k] = el.dataset.e.split(':'); it[layer][k].e = el.value; }
});
document.addEventListener('change', (e) => {
  if (e.target.closest('#detail') && (e.target.dataset.field || e.target.dataset.e)) persist(cur());
});

(async () => {
  try { S.C = await api.criteria(); await reload(); }
  catch (e) { document.body.innerHTML = `<div class="wrap empty">连不上后端：${esc(e.message)}。请先运行 python -m scout.server</div>`; }
})();
