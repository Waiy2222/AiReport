const api = require("../../utils/api.js");
const { formatFullDate } = require("../../utils/date.js");
const app = getApp();

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

function getCurrentType() {
  const hour = new Date().getHours();
  return hour < 12 ? "morning" : "evening";
}

Page({
  data: {
    briefing: null,
    sectionsExpanded: {},
    dateText: "",
    timeText: "",
    typeLabel: "",    // "早间报道" or "晚间报道"
    typeEmoji: "",    // "☀️" or "🌙"
    loading: true,
    headlineItem: {},
    totalItems: 0,
  },

  onLoad() {
    if (!app.globalData.activeTagSet) app.globalData.activeTagSet = {};
    this.fetchMyBriefing();
  },

  onShow() {
    this.fetchMyBriefing();
  },

  onPullDownRefresh() {
    this.fetchMyBriefing();
  },

  async fetchMyBriefing() {
    const type = getCurrentType();

    this.setData({
      loading: true,
      typeLabel: type === "morning" ? "早间报道" : "晚间报道",
      typeEmoji: type === "morning" ? "☀️" : "🌙",
    });

    try {
      // 优先显示通用简报，404 则尝试另一时段
      let data = null;
      let actualType = type;
      try {
        data = await api.getLatestBriefing(type);
      } catch (e) {
        const fallbackType = type === "morning" ? "evening" : "morning";
        try {
          data = await api.getLatestBriefing(fallbackType);
          actualType = fallbackType;
          this.setData({
            typeLabel: fallbackType === "morning" ? "早间报道" : "晚间报道",
            typeEmoji: fallbackType === "morning" ? "☀️" : "🌙",
          });
        } catch (e2) {
          // 通用简报也没有，尝试专属简报
          const openid = app.globalData.openid || wx.getStorageSync("openid") || "anonymous";
          data = await api.getMyLatestBriefing(openid, type);
          actualType = type;
        }
      }

      cacheActiveTags(data);

      const expanded = {};
      (data.sections || []).forEach((s, i) => { expanded[i] = i < 3; });

      let headlineItem = {};
      const allItems = [];
      (data.sections || []).forEach(s => (s.items || []).forEach(i => allItems.push(i)));
      for (const it of allItems) {
        if ((it.image_url && !headlineItem.image_url) || (it.score || 0) > (headlineItem.score || 0)) {
          headlineItem = it;
        }
      }

      let timeText = "";
      if (data.generated_at) {
        const d = new Date(data.generated_at);
        const now = new Date();
        const diffMin = Math.floor((now - d) / 60000);
        if (diffMin < 1) timeText = "刚刚更新";
        else if (diffMin < 60) timeText = `${diffMin}分钟前更新`;
        else if (diffMin < 1440) timeText = `${Math.floor(diffMin / 60)}小时前更新`;
        else timeText = `${Math.floor(diffMin / 1440)}天前更新`;
      }

      // 更新活标签 + 个性化标签到本地存储
      const tags = data.interest_tags || [];
      if (tags.length > 0) {
        wx.setStorageSync('personalizedTags', tags);
        const existingLive = wx.getStorageSync('liveTags') || [];
        const merged = [...new Set([...tags, ...existingLive])].slice(0, 10);
        wx.setStorageSync('liveTags', merged);
      }

      this.setData({
        briefing: data,
        headlineItem,
        totalItems: allItems.length,
        dateText: formatFullDate(data.date),
        timeText,
        sectionsExpanded: expanded,
        loading: false,
      });
    } catch (err) {
      console.error("fetchMyBriefing failed:", err);
      this.setData({ loading: false, briefing: null });
    }
    wx.stopPullDownRefresh();
  },

  onSectionToggle(e) {
    const idx = String(e.currentTarget.dataset.index);
    this.setData({ [`sectionsExpanded.${idx}`]: !this.data.sectionsExpanded[idx] });
  },

  onCardTap(e) {
    const id = this.data.briefing && this.data.briefing.id;
    if (id) wx.navigateTo({ url: `/pages/detail/detail?id=${id}` });
  },

  onArticleTap() {
    const id = this.data.briefing && this.data.briefing.id;
    if (id) wx.navigateTo({ url: `/pages/detail/detail?id=${id}` });
  },

  onMiniImageError(e) {
    const { section, index } = e.currentTarget.dataset;
    this.setData({ [`briefing.sections[${section}].items[${index}]._imgHide`]: true });
  },

  onHeadImageError() {
    this.setData({ 'headlineItem._headImgHide': true });
  },
});
