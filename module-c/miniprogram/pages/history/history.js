// ============================================================
// History Page — Paginated Briefing Archives
// ============================================================
const api = require('../../utils/api');

Page({
  data: {
    // ---- Data ----
    items: [],
    page: 1,
    size: 20,
    total: 0,

    // ---- UI State ----
    loading: true,
    loadingMore: false,
    hasMore: true,
    error: null,
  },

  onLoad() {
    this.fetchHistory();
  },

  onPullDownRefresh() {
    this.setData({ page: 1, hasMore: true, items: [] });
    this.fetchHistory().finally(() => wx.stopPullDownRefresh());
  },

  onReachBottom() {
    if (!this.data.hasMore || this.data.loadingMore) return;
    this.loadMore();
  },

  // ---- Fetch ----

  async fetchHistory() {
    const { page, size } = this.data;
    this.setData({ loading: true, error: null });

    try {
      const data = await api.getHistory(page, size);

      const items = (data.items || []).map((item) => ({
        ...item,
        tlDrPreview: this._previewTlDr(item.tl_dr),
      }));

      this.setData({
        items,
        total: data.total || 0,
        page,
        hasMore: items.length >= size,
        loading: false,
      });
    } catch (err) {
      console.error('[History] fetch error:', err);
      this.setData({
        loading: false,
        error: err.message || '加载失败',
      });
    }
  },

  async loadMore() {
    const nextPage = this.data.page + 1;
    const { size } = this.data;

    this.setData({ loadingMore: true });

    try {
      const data = await api.getHistory(nextPage, size);

      const newItems = (data.items || []).map((item) => ({
        ...item,
        tlDrPreview: this._previewTlDr(item.tl_dr),
      }));

      this.setData({
        items: [...this.data.items, ...newItems],
        page: nextPage,
        hasMore: newItems.length >= size,
        loadingMore: false,
      });
    } catch (err) {
      console.error('[History] loadMore error:', err);
      this.setData({ loadingMore: false });
    }
  },

  // ---- Helpers ----

  /**
   * Produce a short preview string from tl_dr data.
   */
  _previewTlDr(raw) {
    if (!raw) return '';

    let list = [];
    if (Array.isArray(raw)) {
      list = raw;
    } else if (typeof raw === 'string') {
      try {
        list = JSON.parse(raw.replace(/'/g, '"'));
      } catch {
        list = raw
          .split(/\n|•|-|\d+\./)
          .map((s) => s.trim())
          .filter(Boolean);
      }
    }

    if (!Array.isArray(list) || list.length === 0) return '';

    // Take first 2 points for preview
    return list.slice(0, 2).join(' | ');
  },

  /**
   * Format ISO date string to a friendly date.
   */
  formatDate(dateStr) {
    if (!dateStr) return '';
    // If already a date string like "2025-01-15"
    if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
      return dateStr;
    }
    // ISO string to date only
    return dateStr.slice(0, 10);
  },

  // ---- Event Handlers ----

  onItemTap(e) {
    const { id, type } = e.currentTarget.dataset;
    if (!id) return;

    wx.navigateTo({
      url: `/pages/detail/detail?id=${id}&type=${type}`,
      fail(err) {
        console.error('Navigate to detail failed:', err);
      },
    });
  },
});
