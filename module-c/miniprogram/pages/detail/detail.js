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

Page({
  data: {
    briefing: null,
    dateText: "",
    typeText: "",
    sectionsExpanded: {},
    loading: true,
    hasFilter: false,
  },

  onLoad(options) {
    const id = options.id;
    if (id) {
      this.fetchDetail(id);
    }
  },

  async fetchDetail(id) {
    try {
      const data = await api.getBriefingDetail(id);
      const tags = app.globalData.userTags || wx.getStorageSync("userTags") || [];
      const filtered = filterByTags(data, tags);
      const expanded = {};
      (filtered.sections || []).forEach((s, i) => {
        expanded[i] = true;
      });
      this.setData({
        briefing: filtered,
        dateText: formatFullDate(data.date),
        typeText: data.type === "morning" ? "早报" : "晚报",
        sectionsExpanded: expanded,
        loading: false,
        hasFilter: tags.length > 0,
      });
    } catch (err) {
      this.setData({ loading: false });
      wx.showToast({ title: "简报不存在", icon: "none" });
    }
  },

  onSectionToggle(e) {
    const idx = e.currentTarget.dataset.index;
    const key = String(idx);
    this.setData({
      [`sectionsExpanded.${key}`]: !this.data.sectionsExpanded[key],
    });
  },

  onLinkTap(e) {
    const url = e.currentTarget.dataset.url;
    if (url) {
      wx.setClipboardData({
        data: url,
        success() {
          wx.showToast({ title: "链接已复制", icon: "success" });
        },
      });
    }
  },

  // 图片加载失败自动隐藏
  onImageError(e) {
    const { section, index } = e.currentTarget.dataset;
    const path = `briefing.sections[${section}].items[${index}]._imgHide`;
    this.setData({ [path]: true });
  },
});
