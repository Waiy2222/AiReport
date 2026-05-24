const api = require("../../utils/api.js");
const { formatFullDate } = require("../../utils/date.js");

Page({
  data: {
    currentTab: "morning",
    briefing: null,
    dateText: "",
    loading: true,
  },

  onLoad() {
    this.fetchLatest("morning");
  },

  onPullDownRefresh() {
    this.fetchLatest(this.data.currentTab);
  },

  onTabTap(e) {
    const type = e.currentTarget.dataset.type;
    if (type === this.data.currentTab) return;
    this.setData({ currentTab: type });
    this.fetchLatest(type);
  },

  async fetchLatest(type) {
    this.setData({ loading: true });
    try {
      const data = await api.getLatestBriefing(type);
      this.setData({
        briefing: data,
        dateText: formatFullDate(data.date),
        loading: false,
      });
    } catch (err) {
      this.setData({ loading: false });
      wx.showToast({ title: "加载失败", icon: "none" });
    }
    wx.stopPullDownRefresh();
  },

  onCardTap(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/detail/detail?id=${id}` });
  },
});
