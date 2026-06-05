const api = require("../../utils/api.js");

Page({
  data: {
    period: "",
    timeline: [],
    hotTags: [],
    totalEvents: 0,
    weeklyCommentary: "",
    generatedAt: "",
    loading: true,
    error: false,
    expandedDays: {},  // 记录哪些天展开了
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

  onEventTap(e) {
    const url = e.currentTarget.dataset.url;
    if (!url) return;
    // 复制链接到剪贴板
    wx.setClipboardData({
      data: url,
      success: () => wx.showToast({ title: "链接已复制", icon: "success" }),
    });
  },

  // 折叠/展开某天的事件
  onDayToggle(e) {
    const date = e.currentTarget.dataset.date;
    const expanded = { ...this.data.expandedDays };
    expanded[date] = !expanded[date];
    this.setData({ expandedDays: expanded });
  },

  async fetchTrends() {
    this.setData({ loading: true, error: false });
    try {
      const data = await api.getWeeklyTrends();
      const timeline = data.daily_timeline || [];
      const hotTags = data.hot_tags || [];

      // 默认展开今天和昨天
      const expandedDays = {};
      if (timeline.length > 0) expandedDays[timeline[timeline.length - 1].date] = true;
      if (timeline.length > 1) expandedDays[timeline[timeline.length - 2].date] = true;

      let generatedAt = "";
      if (data.generated_at) {
        const d = new Date(data.generated_at);
        generatedAt = `更新于 ${d.toLocaleString("zh-CN", { hour12: false })}`;
      }

      this.setData({
        period: data.period || "",
        timeline,
        hotTags,
        totalEvents: data.total_events || 0,
        weeklyCommentary: data.weekly_commentary || "",
        generatedAt,
        expandedDays,
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
