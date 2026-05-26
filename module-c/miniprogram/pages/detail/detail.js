// ============================================================
// Detail Page — Full Briefing View
// ============================================================
const api = require('../../utils/api');

Page({
  data: {
    // ---- Briefing data ----
    briefing: null,
    tlDrList: [],
    keyTakeaways: [],
    sections: [],

    // ---- Collapsed state for each section ----
    sectionCollapsed: {},

    // ---- UI state ----
    loading: true,
    error: null,
  },

  onLoad(options) {
    const { id, type } = options;

    if (!id && !type) {
      this.setData({
        loading: false,
        error: '缺少简报参数',
      });
      return;
    }

    this.setData({ id, type });
    this.fetchDetail(id, type);
  },

  onShareAppMessage() {
    const { briefing } = this.data;
    return {
      title: briefing
        ? `AI资讯${briefing.type === 'morning' ? '早报' : '晚报'} — ${briefing.date}`
        : 'AI资讯简报',
      path: `/pages/detail/detail?type=${this.data.type}`,
    };
  },

  // ---- Fetch ----

  async fetchDetail(id, type) {
    this.setData({ loading: true, error: null });

    try {
      // Try to get from cache first
      let data = this._getFromCache(type);

      if (!data || (id && data.id !== id)) {
        data = await api.getLatestBriefing(type || 'morning');
      }

      const tlDrList = this._parseList(data.tl_dr);
      const keyTakeaways = this._parseList(data.key_takeaways);
      const sections = this._parseSections(data.sections);

      // Initialize collapse state: first section expanded, rest collapsed
      const collapsed = {};
      sections.forEach((_, idx) => {
        collapsed[idx] = idx !== 0;
      });

      // Pre-parse scores for display
      sections.forEach((section) => {
        (section.items || []).forEach((item) => {
          item.scoreDisplay = this._formatScore(item.score);
        });
      });

      this.setData({
        briefing: data,
        tlDrList,
        keyTakeaways,
        sections,
        sectionCollapsed: collapsed,
        loading: false,
      });
    } catch (err) {
      console.error('[Detail] fetchDetail error:', err);
      this.setData({
        loading: false,
        error: err.message || '加载失败',
      });
    }
  },

  _getFromCache(type) {
    const app = getApp();
    return type === 'morning'
      ? app.globalData.latestMorning
      : app.globalData.latestEvening;
  },

  _parseList(raw) {
    if (!raw) return [];
    if (Array.isArray(raw)) return raw;
    if (typeof raw === 'string') {
      try {
        const parsed = JSON.parse(raw.replace(/'/g, '"'));
        return Array.isArray(parsed) ? parsed : [];
      } catch {
        return raw
          .split(/\n|•|-|\d+\./)
          .map((s) => s.trim())
          .filter(Boolean);
      }
    }
    return [];
  },

  _parseSections(raw) {
    if (!raw) return [];
    if (Array.isArray(raw)) return raw;

    // If stored as JSONB from PostgreSQL, it's already parsed
    // If stored as string, try to parse
    if (typeof raw === 'string') {
      try {
        return JSON.parse(raw);
      } catch {
        return [];
      }
    }
    return [];
  },

  /**
   * Format score into star display.
   * Score range assumed 0-10, mapped to 0-5 stars.
   */
  _formatScore(score) {
    if (score == null || isNaN(score)) return { stars: 0, text: 'N/A' };

    const numScore = Number(score);
    const stars = Math.round((numScore / 10) * 5 * 2) / 2; // nearest 0.5

    const full = Math.floor(stars);
    const half = stars - full >= 0.5 ? 1 : 0;
    const empty = 5 - full - half;

    return {
      stars,
      full,
      half,
      empty,
      text: numScore.toFixed(1),
    };
  },

  // ---- Event Handlers ----

  /** Toggle section collapse */
  onSectionToggle(e) {
    const index = e.currentTarget.dataset.index;
    const { sectionCollapsed } = this.data;
    const newCollapsed = { ...sectionCollapsed };
    newCollapsed[index] = !newCollapsed[index];
    this.setData({ sectionCollapsed: newCollapsed });
  },

  /** Open item URL */
  onItemUrlTap(e) {
    const { url } = e.currentTarget.dataset;
    if (!url) return;

    // Use wx.setClipboardData as a safety fallback
    wx.showModal({
      title: '打开外部链接',
      content: `是否打开以下链接？\n${url}`,
      confirmText: '打开',
      cancelText: '复制',
      success(res) {
        if (res.confirm) {
          // In a real miniprogram, URLs must be in the whitelist.
          // Use web-view or copy as fallback.
          wx.setClipboardData({
            data: url,
            success() {
              wx.showToast({ title: '链接已复制', icon: 'none' });
            },
          });
        } else if (res.cancel) {
          wx.setClipboardData({
            data: url,
            success() {
              wx.showToast({ title: '链接已复制', icon: 'none' });
            },
          });
        }
      },
    });
  },

  /** Share button */
  onShareTap() {
    wx.showShareMenu({
      withShareTicket: true,
      menus: ['shareAppMessage', 'shareTimeline'],
    });
  },
});
