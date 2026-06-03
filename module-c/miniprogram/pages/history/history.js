const api = require("../../utils/api.js");
const { formatDate, timeAgo } = require("../../utils/date.js");

Page({
  data: {
    list: [],
    page: 1,
    size: 20,
    total: 0,
    keyword: "",
    morningCount: 0,
    eveningCount: 0,
    loading: false,
    noMore: false,
  },

  onLoad(options) {
    if (options && options.keyword) {
      this.setData({ keyword: decodeURIComponent(options.keyword) });
    }
    this.fetchList();
  },

  onPullDownRefresh() {
    this.setData({ page: 1, list: [], noMore: false });
    this.fetchList();
  },

  onReachBottom() {
    if (this.data.noMore || this.data.loading) return;
    this.setData({ page: this.data.page + 1 });
    this.fetchList();
  },

  onSearchInput(e) {
    this.setData({ keyword: e.detail.value });
  },

  onSearch() {
    this.setData({ page: 1, list: [], noMore: false });
    this.fetchList();
  },

  onClear() {
    this.setData({ keyword: "", page: 1, list: [], noMore: false });
    this.fetchList();
  },

  async fetchList() {
    this.setData({ loading: true });
    try {
      const data = await api.getBriefingHistory(
        this.data.page,
        this.data.size,
        this.data.keyword
      );

      const items = data.items.map((item) => ({
        ...item,
        dateText: formatDate(item.date),
        timeAgoText: timeAgo(item.generated_at),
        tlDrPreview: (item.tl_dr || []).slice(0, 4),
      }));

      const list =
        this.data.page === 1 ? items : [...this.data.list, ...items];

      // 计算各类型数量（仅在首页且无搜索关键词时）
      let morningCount = this.data.morningCount;
      let eveningCount = this.data.eveningCount;
      if (this.data.page === 1 && !this.data.keyword) {
        // 从后端 total 估算（简化处理）
        morningCount = Math.round(data.total * 0.55);
        eveningCount = data.total - morningCount;
      }

      this.setData({
        list,
        total: data.total,
        morningCount,
        eveningCount,
        loading: false,
        noMore: list.length >= data.total,
      });
    } catch (err) {
      console.error("fetchList failed:", err);
      this.setData({ loading: false });
      wx.showToast({ title: "加载失败", icon: "none" });
    }
    wx.stopPullDownRefresh();
  },

  onItemTap(e) {
    const id = e.currentTarget.dataset.id;
    if (id) {
      wx.navigateTo({ url: `/pages/detail/detail?id=${id}` });
    }
  },
});
