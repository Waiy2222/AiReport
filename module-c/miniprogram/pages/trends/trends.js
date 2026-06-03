const api = require("../../utils/api.js");

Page({
  data: {
    period: "",
    rising: [],
    falling: [],
    new_tags: [],
    agent_insight: "",
    generatedAt: "",
    totalTags: 0,
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
      const rising = data.rising || [];
      const falling = data.falling || [];
      const newTags = data.new_tags || [];

      // 计算活跃标签总数
      const allTagNames = new Set();
      [...rising, ...falling, ...newTags].forEach(item => {
        allTagNames.add(item.tag);
      });
      const totalTags = allTagNames.size;

      // 格式化生成时间
      let generatedAt = "";
      if (data.generated_at) {
        const d = new Date(data.generated_at);
        generatedAt = `更新于 ${d.toLocaleString("zh-CN", { hour12: false })}`;
      }

      this.setData({
        period: data.period || "",
        rising,
        falling,
        new_tags: newTags,
        agent_insight: data.agent_insight || "",
        generatedAt,
        totalTags,
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
