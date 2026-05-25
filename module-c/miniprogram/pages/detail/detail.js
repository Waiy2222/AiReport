const api = require("../../utils/api.js");
const { formatFullDate } = require("../../utils/date.js");

Page({
  data: {
    briefing: null,
    dateText: "",
    typeText: "",
    sectionsExpanded: {},
    loading: true,
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
      const expanded = {};
      data.sections.forEach((s, i) => {
        expanded[i] = true;
      });
      this.setData({
        briefing: data,
        dateText: formatFullDate(data.date),
        typeText: data.type === "morning" ? "早报" : "晚报",
        sectionsExpanded: expanded,
        loading: false,
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
});
