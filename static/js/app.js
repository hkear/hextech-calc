/**
 * 海克斯增幅计算器 - 前端主逻辑
 */
const App = {
  // 状态
  state: {
    champions: [],
    allAugments: [],
    selectedChampion: null,
    augmentSlots: [null, null, null, null],
    pickerSlot: -1,
    pickerTier: 'all',
    isCalculating: false,
    results: null,
  },

  // 常量
  TIER_MAP: { silver: '白银', gold: '黄金', prismatic: '棱彩' },
  TIER_COLORS: { silver: '#c0d0e0', gold: '#ffd700', prismatic: '#ff44ff' },
  TIER_CLASS: { silver: 'tier-silver', gold: 'tier-gold', prismatic: 'tier-prismatic' },

  // ──── 初始化 ────
  async init() {
    await this.loadVersion();
    await this.loadChampions();
    await this.loadAugments();
    this.bindEvents();
  },

  async fetchJSON(url, opts = {}) {
    const r = await fetch(url, opts);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  },

  async loadVersion() {
    try {
      const d = await this.fetchJSON('/api/version');
      const vText = `v${d.engine_version} | 英雄${d.champion_count} | 增幅${d.augment_count}(${d.augment_curated}手工+${d.augment_inferred}推理) | ${d.ddragon_version}`;
      document.getElementById('versionBadge').textContent = vText;
      document.getElementById('footerVersion').textContent = `${d.ddragon_version} | 增幅DB: ${d.augment_db_version}`;
      document.getElementById('footerChamps').textContent = d.champion_count || '-';
      document.getElementById('footerAugments').textContent = `${d.augment_count} (${d.augment_curated}手工/${d.augment_inferred}推理)`;
    } catch(e) {
      document.getElementById('versionBadge').textContent = '版本加载失败';
    }
  },

  async loadChampions() {
    try {
      const d = await this.fetchJSON('/api/champions');
      this.state.champions = d.champions;
      this.renderChampionGrid();
    } catch(e) {
      document.getElementById('championGrid').innerHTML = `<div class="loading">加载失败: ${e.message}</div>`;
    }
  },

  async loadAugments() {
    try {
      const d = await this.fetchJSON('/api/augments?limit=200');
      this.state.allAugments = d.augments;
    } catch(e) {
      console.error('加载增幅失败:', e);
    }
  },

  // ──── 事件绑定 ────
  bindEvents() {
    // 英雄搜索
    document.getElementById('championSearch').addEventListener('input', () => this.renderChampionGrid());
    // 品阶过滤
    document.querySelectorAll('#roleFilter .filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#roleFilter .filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.renderChampionGrid();
      });
    });
    // 换英雄
    document.getElementById('changeChampion').addEventListener('click', () => this.deselectChampion());
    // 增幅搜索
    document.getElementById('augmentSearch').addEventListener('input', () => {
      const term = document.getElementById('augmentSearch').value.trim();
      if (term.length >= 1) {
        this.filterAugmentSlots(term);
      } else {
        this.resetAugmentFilter();
      }
    });
    // 增幅品阶过滤
    document.querySelectorAll('.augment-tier-filter .tier-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.augment-tier-filter .tier-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
      });
    });
    // 随机增幅
    document.getElementById('randomAugments').addEventListener('click', () => this.pickRandomAugments());
    // 计算按钮
    document.getElementById('btnCalculate').addEventListener('click', () => this.calculate());
  },

  // ──── 英雄网格 ────
  renderChampionGrid() {
    const grid = document.getElementById('championGrid');
    const searchTerm = document.getElementById('championSearch').value.trim().toLowerCase();
    const activeTag = document.querySelector('#roleFilter .filter-btn.active')?.dataset?.tag || 'all';

    let filtered = this.state.champions;
    if (searchTerm) {
      filtered = filtered.filter(c => c.search_key.toLowerCase().includes(searchTerm));
    }
    if (activeTag !== 'all') {
      filtered = filtered.filter(c => c.tags.includes(activeTag));
    }

    if (filtered.length === 0) {
      grid.innerHTML = '<div class="loading">未找到匹配英雄</div>';
      return;
    }

    grid.innerHTML = filtered.map(c => `
      <div class="champ-card" data-id="${c.id}" onclick="App.selectChampion('${c.id}')">
        <img src="https://ddragon.leagueoflegends.com/cdn/16.12.1/img/champion/${c.id}.png"
             alt="${c.name}" loading="lazy"
             onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect fill=%22%231a2332%22 width=%22100%22 height=%22100%22/><text x=%2250%22 y=%2255%22 text-anchor=%22middle%22 fill=%22%2360a5fa%22 font-size=%2230%22>${c.name[0]}</text></svg>'">
        <span class="champ-label">${c.name}</span>
      </div>
    `).join('');
  },

  async selectChampion(championId) {
    this.state.selectedChampion = championId;
    document.querySelectorAll('.champ-card').forEach(c => c.classList.remove('selected'));
    document.querySelector(`.champ-card[data-id="${championId}"]`)?.classList.add('selected');
    document.getElementById('championGrid').style.display = 'none';
    document.getElementById('championSearch').value = '';

    // 加载详情
    try {
      const d = await this.fetchJSON(`/api/champion/${championId}`);
      document.getElementById('selectedChampion').style.display = 'flex';
      document.getElementById('champIcon').src = `https://ddragon.leagueoflegends.com/cdn/16.12.1/img/champion/${championId}.png`;
      document.getElementById('champName').textContent = d.name;
      document.getElementById('champTitle').textContent = d.title;

      // 技能展示
      this.renderSkills(d.skills);
      this.state.championDetail = d;
      this.updateCalculateButton();
    } catch(e) {
      alert('英雄数据加载失败: ' + e.message);
    }
  },

  deselectChampion() {
    this.state.selectedChampion = null;
    this.state.championDetail = null;
    document.getElementById('selectedChampion').style.display = 'none';
    document.getElementById('skillsDisplay').style.display = 'none';
    document.getElementById('championGrid').style.display = 'grid';
    document.querySelectorAll('.champ-card').forEach(c => c.classList.remove('selected'));
    this.updateCalculateButton();
  },

  renderSkills(skills) {
    const row = document.getElementById('skillsRow');
    const order = ['passive', 'q', 'w', 'e', 'r'];
    const labels = { passive: '被动', q: 'Q', w: 'W', e: 'E', r: 'R' };
    const ultKeys = ['r'];

    row.innerHTML = order.map(key => {
      const sk = skills[key];
      if (!sk) return '';
      const isUlt = ultKeys.includes(key);
      return `
        <div class="skill-item ${isUlt ? 'ultimate' : ''}">
          <img src="${sk.icon || ''}" alt="${sk.name}" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect fill=%22%231a2332%22 width=%22100%22 height=%22100%22/><text x=%2250%22 y=%2255%22 text-anchor=%22middle%22 fill=%22%2360a5fa%22 font-size=%2230%22>${labels[key]}</text></svg>'">
          <span class="skill-label">${labels[key]} ${sk.name}</span>
        </div>
      `;
    }).join('');

    document.getElementById('skillsDisplay').style.display = 'block';
  },

  // ──── 增幅选择 ────
  openAugmentPicker(slot) {
    if (!this.state.selectedChampion) return;
    this.state.pickerSlot = slot;
    document.getElementById('augmentPicker').style.display = 'flex';
    this.renderPickerList();
  },

  closeAugmentPicker() {
    document.getElementById('augmentPicker').style.display = 'none';
    this.state.pickerSlot = -1;
  },

  renderPickerList() {
    const list = document.getElementById('pickerList');
    const search = document.getElementById('pickerSearch').value.trim().toLowerCase();
    const tier = this.state.pickerTier;

    let items = this.state.allAugments;
    if (tier !== 'all') items = items.filter(a => a.tier === tier);
    if (search) items = items.filter(a =>
      a.name.toLowerCase().includes(search) || (a.description || '').toLowerCase().includes(search)
    );

    // 排除已选的
    const selected = this.state.augmentSlots.filter(s => s !== null).map(s => s.id);
    items = items.filter(a => !selected.includes(a.id));

    if (items.length === 0) {
      list.innerHTML = '<div class="loading">没有更多增幅了</div>';
      return;
    }

    list.innerHTML = items.map(a => {
      const tierName = this.TIER_MAP[a.tier] || a.tier;
      const tierColor = this.TIER_COLORS[a.tier] || '#888';
      return `
        <div class="picker-item" onclick="App.pickAugment('${a.id}')">
          <span class="picker-tier-dot" style="background:${tierColor}"></span>
          <div>
            <div class="picker-name">${a.name}</div>
            <div class="picker-desc">${a.tier === 'silver' ? '🥈' : a.tier === 'gold' ? '🥇' : '💎'} ${tierName} · ${(a.description || '').substring(0, 60)}</div>
          </div>
        </div>
      `;
    }).join('');
  },

  filterPickerTier(tier) {
    this.state.pickerTier = tier;
    document.querySelectorAll('.picker-filter .tier-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`.picker-filter .tier-btn[data-tier="${tier}"]`)?.classList.add('active');
    this.renderPickerList();
  },

  filterPickerList() {
    this.renderPickerList();
  },

  pickAugment(augmentId) {
    const slot = this.state.pickerSlot;
    if (slot < 0 || slot > 3) return;

    const aug = this.state.allAugments.find(a => a.id === augmentId);
    if (!aug) return;

    this.state.augmentSlots[slot] = aug;
    this.renderAugmentSlots();
    this.closeAugmentPicker();
    this.updateCalculateButton();
  },

  removeAugment(slot) {
    this.state.augmentSlots[slot] = null;
    this.renderAugmentSlots();
    this.updateCalculateButton();
  },

  renderAugmentSlots() {
    const container = document.getElementById('augmentSlots');
    container.innerHTML = this.state.augmentSlots.map((aug, i) => {
      if (!aug) {
        return `
          <div class="augment-slot empty" data-slot="${i}" onclick="App.openAugmentPicker(${i})">
            <span class="slot-placeholder">+ 选择增幅</span>
          </div>
        `;
      }
      const tierClass = this.TIER_CLASS[aug.tier] || '';
      const tierName = this.TIER_MAP[aug.tier] || aug.tier;
      const tierIcon = aug.tier === 'silver' ? '🥈' : aug.tier === 'gold' ? '🥇' : '💎';
      return `
        <div class="augment-slot filled ${tierClass}" data-slot="${i}">
          <button class="aug-remove" onclick="App.removeAugment(${i})">✕</button>
          <span class="aug-tier-badge">${tierIcon} ${tierName}</span>
          <span class="aug-name">${aug.name}</span>
          <span class="aug-desc">${(aug.description || '').substring(0, 60)}</span>
        </div>
      `;
    }).join('');
  },

  filterAugmentSlots(term) {
    term = term.toLowerCase();
    this.state.allAugments.forEach(a => {
      a._hidden = !a.name.toLowerCase().includes(term) && !(a.description || '').toLowerCase().includes(term);
    });
    // Refresh augment picker if open
    if (document.getElementById('augmentPicker').style.display === 'flex') {
      this.renderPickerList();
    }
  },

  resetAugmentFilter() {
    this.state.allAugments.forEach(a => a._hidden = false);
  },

  pickRandomAugments() {
    if (!this.state.selectedChampion) return;

    // Pick 4 random augments, avoid duplicates
    const available = [...this.state.allAugments];
    const selected = [];
    for (let i = 0; i < 4 && available.length > 0; i++) {
      const idx = Math.floor(Math.random() * available.length);
      selected.push(available[idx]);
      available.splice(idx, 1);
    }

    this.state.augmentSlots = selected;
    this.renderAugmentSlots();
    this.updateCalculateButton();
  },

  // ──── 计算逻辑 ────
  updateCalculateButton() {
    const btn = document.getElementById('btnCalculate');
    const hasChamp = !!this.state.selectedChampion;
    const hasAugs = this.state.augmentSlots.some(a => a !== null);
    btn.disabled = !(hasChamp && hasAugs);
    if (!hasChamp) btn.textContent = '🚀 请先选择英雄';
    else if (!hasAugs) btn.textContent = '🚀 请选择至少1个增幅';
    else btn.textContent = '🚀 开始计算';
  },

  async calculate() {
    if (this.state.isCalculating) return;

    const augmentIds = this.state.augmentSlots.filter(a => a !== null).map(a => a.id);
    if (!this.state.selectedChampion || augmentIds.length === 0) return;

    this.state.isCalculating = true;
    const btn = document.getElementById('btnCalculate');
    btn.textContent = '⏳ 计算中...';
    btn.disabled = true;

    try {
      const result = await this.fetchJSON('/api/calculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          champion_id: this.state.selectedChampion,
          augment_ids: augmentIds,
        }),
      });

      this.state.results = result;
      this.renderResults(result);
    } catch(e) {
      alert('计算失败: ' + e.message);
    } finally {
      this.state.isCalculating = false;
      this.updateCalculateButton();
    }
  },

  renderResults(result) {
    document.getElementById('emptyState').style.display = 'none';
    const area = document.getElementById('resultsArea');
    area.style.display = 'block';

    // 排名
    this.renderRanking(result.ranking);
    // 矩阵
    this.renderMatrix(result);
    // 详情
    this.renderDetails(result);

    // 滚动到结果区
    area.scrollIntoView({ behavior: 'smooth', block: 'start' });
  },

  renderRanking(ranking) {
    const list = document.getElementById('rankingList');
    const tierIcon = { silver: '🥈', gold: '🥇', prismatic: '💎' };

    list.innerHTML = ranking.map((r, i) => `
      <div class="rank-card rank-${i}">
        <div class="rank-num">#${i + 1}</div>
        <div class="rank-name">${r.name}</div>
        <div class="rank-score">${r.total_score}</div>
        <div class="rank-rec">${r.recommendation}</div>
      </div>
    `).join('');
  },

  renderMatrix(result) {
    const skills = result.skills;
    const augResults = result.results;
    const order = ['passive', 'q', 'w', 'e', 'r'];
    const labels = { passive: '被动', q: 'Q', w: 'W', e: 'E', r: 'R' };

    // Header
    const thead = document.getElementById('matrixHeader');
    const tierIcon = { silver: '🥈', gold: '🥇', prismatic: '💎' };
    const tierNames = { silver: '白银', gold: '黄金', prismatic: '棱彩' };

    let headerHtml = '<tr><th>技能</th>';
    for (const [aid, augR] of Object.entries(augResults)) {
      const tierName = tierNames[augR.augment_tier] || '';
      headerHtml += `<th>${augR.augment_name}<span class="tier-label">${tierIcon[augR.augment_tier] || ''} ${tierName}</span></th>`;
    }
    headerHtml += '</tr>';
    thead.innerHTML = headerHtml;

    // Body
    const tbody = document.getElementById('matrixBody');
    let bodyHtml = '';

    for (const sk of order) {
      const skInfo = skills[sk];
      if (!skInfo) continue;
      const skName = `${labels[sk]} ${skInfo.name}`;

      bodyHtml += `<tr><td>${skName}</td>`;

      for (const [aid, augR] of Object.entries(augResults)) {
        const boost = augR.skill_boosts[sk];
        if (!boost) {
          bodyHtml += '<td><span class="boost-value" style="color:#666">—</span></td>';
          continue;
        }

        const pct = boost.boost_percent;
        const match = boost.match_score;
        const desc = boost.description || '';

        // Color based on percentage
        let color = '#666';
        if (pct > 40) color = '#22c55e';
        else if (pct > 20) color = '#60a5fa';
        else if (pct > 5) color = '#f59e0b';
        else if (pct > 0) color = '#8899aa';

        // Match dots
        const dots = Math.round(match * 5);
        let dotsHtml = '<div class="match-dots">';
        for (let d = 0; d < 5; d++) {
          dotsHtml += `<span class="dot ${d < dots ? (d === dots - 1 && match % 0.2 > 0.05 ? 'half' : 'filled') : 'empty'}"></span>`;
        }
        dotsHtml += '</div>';

        bodyHtml += `<td>
          <div class="boost-value" style="color:${color}">${pct > 0 ? '+' : ''}${pct}%</div>
          <div class="boost-desc">${desc.substring(0, 30)}</div>
          ${dotsHtml}
        </td>`;
      }
      bodyHtml += '</tr>';
    }

    tbody.innerHTML = bodyHtml;
  },

  renderDetails(result) {
    const grid = document.getElementById('detailsGrid');
    const tierNames = { silver: '白银', gold: '黄金', prismatic: '棱彩' };
    const tierColors = { silver: '#c0d0e0', gold: '#ffd700', prismatic: '#ff44ff' };
    const order = ['passive', 'q', 'w', 'e', 'r'];
    const labels = { passive: '被', q: 'Q', w: 'W', e: 'E', r: 'R' };

    let html = '';
    for (const [aid, augR] of Object.entries(result.results)) {
      const tierColor = tierColors[augR.augment_tier] || '#888';

      // Skill boosts for this augment
      let boostsHtml = '';
      for (const sk of order) {
        const skInfo = result.skills[sk];
        if (!skInfo) continue;
        const boost = augR.skill_boosts[sk];
        if (!boost) continue;
        const pct = boost.boost_percent;
        if (pct <= 0 && !boost.description.includes('明显') && boost.description !== '无效果') continue;

        const color = pct > 20 ? '#22c55e' : pct > 5 ? '#f59e0b' : '#8899aa';
        boostsHtml += `<div class="detail-boost-item">
          <span class="boost-skill-name">${labels[sk]} ${skInfo.name}</span>
          <span class="boost-pct" style="color:${color}">${pct > 0 ? '+' : ''}${pct}%</span>
          <span class="boost-detail-text">${boost.description}</span>
        </div>`;
      }

      html += `
        <div class="detail-card" style="border-top: 3px solid ${tierColor}">
          <div class="detail-header">
            <span class="detail-name">${augR.augment_name}</span>
            <span class="detail-tier-badge" style="background:${tierColor}22; color:${tierColor}">
              ${tierNames[augR.augment_tier] || ''}
            </span>
          </div>
          <div class="detail-desc">${augR.augment_description}</div>
          <div class="detail-stats">
            ${Object.entries(augR.stat_boosts || {}).map(([k, v]) => {
              let display = `${k}: ${typeof v === 'boolean' ? '✓' : typeof v === 'number' ? (v > 1 ? v : (v * 100).toFixed(0) + '%') : v}`;
              return `<span class="stat-tag">${display}</span>`;
            }).join('')}
          </div>
          <div class="detail-boosts">${boostsHtml || '<div style="color:#666;font-size:12px">该增幅对此英雄无明显直接增益</div>'}</div>
        </div>
      `;
    }

    grid.innerHTML = html;
  },
};

// ──── 启动 ────
document.addEventListener('DOMContentLoaded', () => App.init());
