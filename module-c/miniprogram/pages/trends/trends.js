const api = require("../../utils/api.js");

Page({
  data: {
    period: "",
    rising: [],
    falling: [],
    new_tags: [],
    agent_insight: "",
    loading: true,
    error: false,
  },

  onLoad() {
    this.fetchTrends();
  },

  onPullDownRefresh() {
    this.fetchTrends();
  },

  onTagTap(e) {
    const tag = e.currentTarget.dataset.tag;
    if (!tag) return;
    wx.navigateTo({
      url: `/pages/history/history?keyword=${encodeURIComponent(tag)}`,
    });
  },

  async fetchTrends() {
    this.setData({ loading: true, error: false });
    try {
      const data = await api.getWeeklyTrends();
      this.setData({
        period: data.period || "",
        rising: data.rising || [],
        falling: data.falling || [],
        new_tags: data.new_tags || [],
        agent_insight: data.agent_insight || "",
        loading: false,
      });
    } catch (err) {
      console.error("fetchTrends failed:", err);
      this.setData({ loading: false, error: true });
      wx.showToast({ title: "加载趋势失败", icon: "none" });
    }
    wx.stopPullDownRefresh();
  },
});
