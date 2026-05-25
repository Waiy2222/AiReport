const api = require("../../utils/api.js");
const { formatDate, timeAgo } = require("../../utils/date.js");

Page({
  data: {
    list: [],
    page: 1,
    size: 20,
    total: 0,
    keyword: "",
    loading: false,
    noMore: false,
  },

  onLoad() {
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
        tlDrPreview: (item.tl_dr || []).slice(0, 3),
      }));
      const list =
        this.data.page === 1 ? items : [...this.data.list, ...items];
      this.setData({
        list,
        total: data.total,
        loading: false,
        noMore: list.length >= data.total,
      });
    } catch (err) {
      this.setData({ loading: false });
      wx.showToast({ title: "加载失败", icon: "none" });
    }
    wx.stopPullDownRefresh();
  },

  onItemTap(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/detail/detail?id=${id}` });
  },
});
