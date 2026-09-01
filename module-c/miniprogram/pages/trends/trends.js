const api = require("../../utils/api.js");
const app = getApp();

Page({
  data: {
    timeline: [],
    hotTags: [],
    totalEvents: 0,
    weeklyCommentary: "",
    generatedAt: "",
    loading: true,
    expandedDays: {},
    personalizedTags: [],
  },

  onLoad() {
    const tags = wx.getStorageSync('personalizedTags') || [];
    this.setData({ personalizedTags: tags });
    this.fetchTrends();
  },

  onShow() {
    const tags = wx.getStorageSync('personalizedTags') || [];
    if (tags.join(',') !== (this.data.personalizedTags || []).join(',')) {
      this.setData({ personalizedTags: tags });
      this.fetchTrends();
    }
  },

  onPullDownRefresh() {
    this.fetchTrends();
  },

  async fetchTrends() {
    this.setData({ loading: true });
    const timeout = setTimeout(() => {
      if (this.data.loading) this.setData({ loading: false });
    }, 15000);

    try {
      const openid = app.globalData.openid || wx.getStorageSync('openid') || 'anonymous';
      const tags = this.data.personalizedTags;
      const data = await api.getWeeklyTrends(tags, openid);

      const expandedDays = {};
      if (data.daily_timeline && data.daily_timeline.length > 0) {
        expandedDays[data.daily_timeline[0].date] = true;
      }

      this.setData({
        timeline: data.daily_timeline || [],
        hotTags: data.hot_tags || [],
        totalEvents: data.total_events || 0,
        weeklyCommentary: data.weekly_commentary || '',
        generatedAt: data.generated_at || '',
        expandedDays,
        loading: false,
      });
    } catch (e) {
      console.error("fetchTrends failed:", e);
      this.setData({ loading: false });
    }
    clearTimeout(timeout);
    wx.stopPullDownRefresh();
  },

  onDayToggle(e) {
    const date = e.currentTarget.dataset.date;
    const key = date;
    this.setData({
      [`expandedDays.${key}`]: !this.data.expandedDays[key],
    });
  },

  onGoGenerate() {
    wx.switchTab({ url: '/pages/index/index' });
  },
});
