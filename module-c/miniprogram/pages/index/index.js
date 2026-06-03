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
    totalItems: 0,
    headlineItem: {},
    stats: {},
    sectionsExpanded: {},
    loading: true,
    activeTags: [],
  },

  onLoad() {
    if (!app.globalData.activeTagSet) app.globalData.activeTagSet = {};
    this.fetchLatest("morning");
  },

  onShow() {
    const tags = app.globalData.userTags || wx.getStorageSync("userTags") || [];
    if (tags.join(",") !== (this.data.activeTags || []).join(",")) {
      this.setData({ activeTags: tags });
      // 重新应用过滤
      const type = this.data.currentTab;
      this.fetchLatest(type);
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
      cacheActiveTags(data);

      const tags = app.globalData.userTags || wx.getStorageSync("userTags") || [];
      const filtered = filterByTags(data, tags);

      // 展开前2个 section，其余折叠
      const expanded = {};
      (filtered.sections || []).forEach((s, i) => {
        expanded[i] = i < 2;
      });

      // 计算总条目数
      const totalItems = (filtered.sections || []).reduce(
        (sum, s) => sum + (s.items || []).length, 0
      );

      // 提取头条对应的原始 item（用于显示标签和分数）
      let headlineItem = {};
      const hlIndex = (filtered.headline || {}).item_index;
      if (hlIndex != null) {
        for (const sec of filtered.sections || []) {
          for (const it of sec.items || []) {
            if (it.score >= 8) { headlineItem = it; break; }
          }
          if (headlineItem.title) break;
        }
        if (!headlineItem.title) {
          const allItems = [];
          (filtered.sections || []).forEach(s => (s.items || []).forEach(i => allItems.push(i)));
          headlineItem = allItems[hlIndex] || allItems[0] || {};
        }
      }

      // 提取统计信息
      const rawStats = data.raw_stats || {};
      const stats = {
        fetched: rawStats.fetched || 0,
        scored: rawStats.scored || 0,
        passed: rawStats.passed || 0,
        final_count: rawStats.final_count || totalItems,
        dedup_url_removed: rawStats.dedup_url_removed || 0,
        dedup_semantic_removed: rawStats.dedup_semantic_removed || 0,
        headline_title: (rawStats.headline || {}).title || "",
      };

      this.setData({
        briefing: filtered,
        dateText: formatFullDate(data.date),
        totalItems,
        headlineItem,
        stats,
        sectionsExpanded: expanded,
        loading: false,
        activeTags: tags,
      });
    } catch (err) {
      console.error("fetchLatest failed:", err);
      this.setData({ loading: false });
      wx.showToast({ title: "加载失败", icon: "none" });
    }
    wx.stopPullDownRefresh();
  },

  onSectionToggle(e) {
    const idx = e.currentTarget.dataset.index;
    const key = String(idx);
    this.setData({
      [`sectionsExpanded.${key}`]: !this.data.sectionsExpanded[key],
    });
  },

  onCardTap(e) {
    const id = e.currentTarget.dataset.id || (this.data.briefing && this.data.briefing.id);
    if (id) {
      wx.navigateTo({ url: `/pages/detail/detail?id=${id}` });
    }
  },

  onArticleTap(e) {
    const id = this.data.briefing && this.data.briefing.id;
    if (id) {
      wx.navigateTo({ url: `/pages/detail/detail?id=${id}` });
    }
  },

  onMiniImageError(e) {
    const { section, index } = e.currentTarget.dataset;
    const path = `briefing.sections[${section}].items[${index}]._imgHide`;
    this.setData({ [path]: true });
  },
});
