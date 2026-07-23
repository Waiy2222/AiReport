const api = require("../../utils/api.js");
const { formatDate, timeAgo } = require("../../utils/date.js");

Page({
  data: {
    list: [],
    page: 1,
    size: 20,
    total: 0,
    keyword: "",
    morningCount: 0,
    eveningCount: 0,
    loading: false,
    noMore: false,

    // 筛选
    filterType: "",    // "" | "morning" | "evening"
    filterTag: "",     // 标签筛选
    tags: [],          // 可用标签列表
    showTagPicker: false,
    briefType: "",     // "" | "personalized" | "general" — 简报类型筛选
  },

  onLoad(options) {
    if (options && options.keyword) {
      this.setData({ keyword: decodeURIComponent(options.keyword) });
    }
    this.fetchTags();
    this.fetchList();
  },

  onPullDownRefresh() {
    this.setData({ page: 1, list: [], noMore: false });
    this.fetchList();
  },

  onReachBottom() {
    if (this.data.noMore || this.data.loading) return;
    this.setData({ page: this.data.page + 1 });
    if (this.data.briefType === "personalized") {
      this._fetchMyBriefings();
    } else {
      this.fetchList();
    }
  },

  onSearchInput(e) {
    this.setData({ keyword: e.detail.value });
  },

  onSearch() {
    this.setData({ page: 1, list: [], noMore: false });
    this.fetchList();
  },

  onClear() {
    this.setData({ keyword: "", page: 1, list: [], noMore: false });
    this.fetchList({ keyword: "" });
  },

  // 类型筛选
  onFilterType(e) {
    const t = e.currentTarget.dataset.type;
    const newType = this.data.filterType === t ? "" : t;
    this.setData({ filterType: newType, page: 1, list: [], noMore: false });
    this.fetchList({ filterType: newType });
  },

  // 标签筛选
  onSelectTag(e) {
    const t = e.currentTarget.dataset.tag;
    const newTag = this.data.filterTag === t ? "" : t;
    console.log('[history] onSelectTag:', t, '→ newTag:', newTag);
    this.setData({ filterTag: newTag, page: 1, list: [], noMore: false });
    this.fetchList({ filterTag: newTag });
  },

  // 清除所有筛选
  onClearFilters() {
    this.setData({
      filterType: "",
      filterTag: "",
      keyword: "",
      briefType: "",
      page: 1,
      list: [],
      noMore: false,
    });
    this.fetchList({ filterType: "", filterTag: "", keyword: "" });
  },

  // 简报类型筛选（专属/通用）
  onFilterBriefType(e) {
    var t = e.currentTarget.dataset.btype;
    var newType = this.data.briefType === t ? "" : t;
    this.setData({ briefType: newType, page: 1, list: [], noMore: false });
    if (newType === "personalized") {
      this._fetchMyBriefings();
    } else {
      this.fetchList();
    }
  },

  async _fetchMyBriefings() {
    this.setData({ loading: true });
    try {
      var openid = getApp().globalData.openid || "anonymous";
      var data = await api.getMyBriefings(openid, this.data.page, this.data.size);
      var items = (data.items || []).map(function (item) {
        return {
          id: item.id,
          type: item.type,
          date: item.date,
          dateText: formatDate(item.date),
          timeAgoText: timeAgo(item.generated_at),
          isPersonalized: true,
          interestText: item.interest_text || "",
          interestTags: item.interest_tags || [],
          tlDrPreview: [],
          tags: item.interest_tags || [],
        };
      });
      this.setData({
        list: items,
        total: data.total,
        loading: false,
        noMore: items.length >= data.total,
      });
    } catch (e) {
      console.error("fetch my briefings failed:", e);
      this.setData({ loading: false });
    }
  },

  async fetchTags() {
    try {
      const data = await api.getTags();
      if (data && data.tags) {
        this.setData({ tags: data.tags });
      }
    } catch (err) {
      // 标签加载失败不影响主流程
    }
  },

  async fetchList(overrides = {}) {
    // 如果已切换到专属简报，走专属接口
    if (this.data.briefType === "personalized") {
      return this._fetchMyBriefings();
    }

    this.setData({ loading: true });

    // 使用显式传入的 filter 值（优先），回退到 this.data
    const filterType = overrides.filterType !== undefined ? overrides.filterType : this.data.filterType;
    const filterTag = overrides.filterTag !== undefined ? overrides.filterTag : this.data.filterTag;
    const keyword = overrides.keyword !== undefined ? overrides.keyword : this.data.keyword;

    const filters = {
      type: filterType,
      dateFrom: "",
      dateTo: "",
      tag: filterTag,
    };

    console.log('[history] fetchList filters:', JSON.stringify(filters), 'keyword:', keyword);

    try {
      const data = await api.getBriefingHistory(
        this.data.page,
        this.data.size,
        keyword,
        filters
      );

      const items = data.items.map((item) => ({
        ...item,
        dateText: formatDate(item.date),
        timeAgoText: timeAgo(item.generated_at),
        tlDrPreview: (item.tl_dr || []).slice(0, 4),
        // Extract unique tags from sections
        tags: [...new Set(
          (item.sections || [])
            .map(s => s.tag)
            .filter(t => t && t !== '综合')
        )].slice(0, 5),
      }));

      const list =
        this.data.page === 1 ? items : [...this.data.list, ...items];

      let morningCount = this.data.morningCount;
      let eveningCount = this.data.eveningCount;
      if (this.data.page === 1 && !this.data.keyword) {
        morningCount = Math.round(data.total * 0.55);
        eveningCount = data.total - morningCount;
      }

      this.setData({
        list,
        total: data.total,
        morningCount,
        eveningCount,
        loading: false,
        noMore: list.length >= data.total,
      });
    } catch (err) {
      console.error("fetchList failed:", err);
      this.setData({ loading: false });
      wx.showToast({ title: "加载失败", icon: "none" });
    }
    wx.stopPullDownRefresh();
  },

  onItemTap(e) {
    const id = e.currentTarget.dataset.id;
    if (id) {
      wx.navigateTo({ url: `/pages/detail/detail?id=${id}` });
    }
  },
});
