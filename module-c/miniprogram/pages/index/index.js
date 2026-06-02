const api = require("../../utils/api.js");
const { formatFullDate } = require("../../utils/date.js");
const app = getApp();

// 按用户标签过滤简报内容
function filterByTags(briefing, userTags) {
  if (!userTags || userTags.length === 0) return briefing;
  const tagSet = new Set(userTags);
  const filteredSections = [];
  for (const section of briefing.sections || []) {
    const matched = (section.items || []).filter(item =>
      (item.tags || []).some(t => tagSet.has(t))
    );
    if (matched.length > 0) {
      filteredSections.push({ ...section, items: matched });
    }
  }
  if (filteredSections.length === 0) return briefing;
  return { ...briefing, sections: filteredSections };
}

// 从简报数据提取所有标签，存到全局
function cacheActiveTags(briefing) {
  if (!briefing) return;
  const tagSet = app.globalData.activeTagSet || {};
  (briefing.sections || []).forEach(sec => {
    (sec.items || []).forEach(item => {
      (item.tags || []).forEach(t => { tagSet[t] = true; });
    });
  });
  app.globalData.activeTagSet = tagSet;
}

Page({
  data: {
    currentTab: "morning",
    briefing: null,
    dateText: "",
    loading: true,
    activeTags: [],
  },

  onLoad() {
    // 初始化全局 activeTagSet
    if (!app.globalData.activeTagSet) app.globalData.activeTagSet = {};
    this.fetchLatest("morning");
  },

  onShow() {
    const tags = app.globalData.userTags || wx.getStorageSync("userTags") || [];
    if (tags.join(",") !== (this.data.activeTags || []).join(",")) {
      this.setData({ activeTags: tags });
    }
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
      // 顺便缓存标签供"我的"页使用
      cacheActiveTags(data);
      const tags = app.globalData.userTags || wx.getStorageSync("userTags") || [];
      const filtered = filterByTags(data, tags);
      this.setData({
        briefing: filtered,
        dateText: formatFullDate(data.date),
        loading: false,
        activeTags: tags,
      });
    } catch (err) {
      this.setData({ loading: false });
      wx.showToast({ title: "加载失败", icon: "none" });
    }
    wx.stopPullDownRefresh();
  },

  applyFilter(tags) {
    this.setData({ activeTags: tags });
  },

  onCardTap(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/detail/detail?id=${id}` });
  },
});
