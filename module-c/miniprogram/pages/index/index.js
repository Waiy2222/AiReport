// ============================================================
// Index Page — Today's Briefing
// ============================================================
const api = require('../../utils/api');

Page({
  data: {
    // ---- Tab state ----
    activeTab: 'morning', // 'morning' | 'evening'

    // ---- Briefing data ----
    briefing: null,
    tlDrList: [],       // parsed tl_dr array
    keyTakeaways: [],   // parsed key_takeaways

    // ---- Subscribe state ----
    isSubscribed: false,
    showSubscribeCard: false,

    // ---- UI state ----
    loading: true,
    error: null,
    refreshing: false,
  },

  // ---- Lifecycle ----

  onLoad() {
    this._loadFromCache();
    this.fetchBriefing();
  },

  onShow() {
    // Sync subscription status from globalData
    const app = getApp();
    this.setData({
      isSubscribed: app.globalData.isSubscribed,
    });
  },

  onPullDownRefresh() {
    this.setData({ refreshing: true });
    this.fetchBriefing()
      .finally(() => {
        wx.stopPullDownRefresh();
        this.setData({ refreshing: false });
      });
  },

  // ---- Data Fetching ----

  async fetchBriefing() {
    const { activeTab } = this.data;

    this.setData({ loading: true, error: null });

    try {
      const data = await api.getLatestBriefing(activeTab);
      const tlDrList = this._parseList(data.tl_dr);
      const keyTakeaways = this._parseList(data.key_takeaways);

      this.setData({
        briefing: data,
        tlDrList,
        keyTakeaways,
        loading: false,
        error: null,
      });

      // Cache to globalData
      const app = getApp();
      if (activeTab === 'morning') {
        app.globalData.latestMorning = data;
      } else {
        app.globalData.latestEvening = data;
      }
    } catch (err) {
      console.error('[Index] fetchBriefing error:', err);
      this.setData({
        loading: false,
        error: err.message || '加载失败',
      });
    }
  },

  /**
   * Try to load briefing from in-memory cache for instant display.
   */
  _loadFromCache() {
    const app = getApp();
    const { activeTab } = this.data;
    const cached =
      activeTab === 'morning'
        ? app.globalData.latestMorning
        : app.globalData.latestEvening;

    if (cached) {
      this.setData({
        briefing: cached,
        tlDrList: this._parseList(cached.tl_dr),
        keyTakeaways: this._parseList(cached.key_takeaways),
        loading: false,
      });
    }
  },

  // ---- Helpers ----

  /**
   * Normalize tl_dr / key_takeaways to an array.
   * Backend may send JSON array, Python list string, or already an array.
   */
  _parseList(raw) {
    if (!raw) return [];
    if (Array.isArray(raw)) return raw;
    if (typeof raw === 'string') {
      try {
        const parsed = JSON.parse(raw.replace(/'/g, '"'));
        return Array.isArray(parsed) ? parsed : [];
      } catch {
        // Fallback: split by common delimiters
        return raw
          .split(/\n|•|-|\d+\./)
          .map((s) => s.trim())
          .filter(Boolean);
      }
    }
    return [];
  },

  // ---- Event Handlers ----

  /** Switch morning / evening tab */
  onTabTap(e) {
    const tab = e.currentTarget.dataset.tab;
    if (tab === this.data.activeTab) return;

    this.setData({ activeTab: tab });
    this._loadFromCache();
    this.fetchBriefing();
  },

  /** Navigate to detail page */
  onBriefingTap() {
    const { briefing } = this.data;
    if (!briefing) return;

    wx.navigateTo({
      url: `/pages/detail/detail?id=${briefing.id}&type=${briefing.type}`,
      fail(err) {
        console.error('Navigate to detail failed:', err);
        wx.showToast({ title: '页面跳转失败', icon: 'none' });
      },
    });
  },

  /** Tap a TL;DR item */
  onTlDrTap(e) {
    const index = e.currentTarget.dataset.index;
    const { tlDrList } = this.data;
    if (tlDrList[index]) {
      wx.showToast({ title: tlDrList[index], icon: 'none', duration: 3000 });
    }
  },

  /** Subscribe button */
  async onSubscribeTap() {
    const app = getApp();
    const { openid, morningEnabled, eveningEnabled } = app.globalData;

    try {
      wx.showLoading({ title: '订阅中...', mask: true });
      await api.subscribe(openid, morningEnabled, eveningEnabled);
      app.setSubscription(true, morningEnabled, eveningEnabled);

      this.setData({
        isSubscribed: true,
        showSubscribeCard: false,
      });

      wx.showToast({ title: '订阅成功！', icon: 'success' });
    } catch (err) {
      console.error('[Index] subscribe error:', err);
    } finally {
      wx.hideLoading();
    }
  },

  /** Navigate to history */
  onHistoryTap() {
    wx.switchTab({ url: '/pages/history/history' });
  },
});
