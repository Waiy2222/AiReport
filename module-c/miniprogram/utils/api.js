const config = require("./config.js");
const app = getApp();

function request(url, method = "GET", data = null) {
  const baseUrl = app.globalData.baseUrl || config.baseUrl;
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${baseUrl}${url}`,
      method,
      data,
      header: {
        "Content-Type": "application/json",
      },
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject({ statusCode: res.statusCode, message: res.data });
        }
      },
      fail(err) {
        reject({ error: true, message: err.errMsg });
      },
    });
  });
}

module.exports = {
  getLatestBriefing(type) {
    return request(`/api/briefings/latest?type=${type}`);
  },

  getBriefingHistory(page = 1, size = 20, keyword = "", filters = {}) {
    let url = `/api/briefings/history?page=${page}&size=${size}`;
    if (keyword) url += `&keyword=${encodeURIComponent(keyword)}`;
    if (filters.type) url += `&type=${encodeURIComponent(filters.type)}`;
    if (filters.dateFrom) url += `&date_from=${encodeURIComponent(filters.dateFrom)}`;
    if (filters.dateTo) url += `&date_to=${encodeURIComponent(filters.dateTo)}`;
    if (filters.tag) url += `&tag=${encodeURIComponent(filters.tag)}`;
    return request(url);
  },

  getBriefingDetail(id) {
    return request(`/api/briefings/${id}`);
  },

  subscribe(openid, morningEnabled = true, eveningEnabled = true) {
    return request("/api/subscribe", "POST", {
      openid,
      morning_enabled: morningEnabled,
      evening_enabled: eveningEnabled,
    });
  },

  unsubscribe(openid) {
    return request("/api/unsubscribe", "POST", { openid });
  },

  // Phase 2 新增接口
  getTags() {
    return request("/api/tags");
  },

  getPreferences(openid) {
    return request(`/api/user/preferences?openid=${encodeURIComponent(openid)}`);
  },

  setPreferences(openid, tags) {
    return request("/api/user/preferences", "POST", { openid, tags });
  },

  getUserProfile(openid) {
    return request(`/api/user/${encodeURIComponent(openid)}/profile`);
  },

  reportBehavior(data) {
    return request("/api/behavior", "POST", data);
  },

  // Phase 3 新增: 信源健康度 API
  getSourcesHealth() {
    return request("/api/sources/health");
  },

  getSourcesRecommendations(status = "pending") {
    return request(`/api/sources/recommendations?status=${encodeURIComponent(status)}`);
  },

  approveSource(sourceId) {
    return request(`/api/sources/approve?source_id=${encodeURIComponent(sourceId)}`, "POST");
  },

  // Phase 3 趋势接口
  getWeeklyTrends(tags, openid) {
    const params = [];
    if (tags && tags.length) params.push(`tags=${tags.join(',')}`);
    if (openid) params.push(`openid=${openid}`);
    const qs = params.length ? `?${params.join('&')}` : '';
    return request(`/api/trends/weekly${qs}`);
  },

  getTagTrend(tag) {
    return request(`/api/trends/tag/${encodeURIComponent(tag)}`);
  },


  // 个性化简报
  generateBriefing(openid, interestText, tags, type) {
    return request("/api/briefings/generate", "POST", {
      openid: openid || "anonymous",
      interest_text: interestText,
      tags: tags || [],
      type: type || "morning",
    });
  },

  getGenerateStatus(taskId) {
    return request(`/api/briefings/generate/${encodeURIComponent(taskId)}`);
  },

  getMyLatestBriefing(openid, type) {
    return request(
      `/api/briefings/my/latest?openid=${encodeURIComponent(openid || "anonymous")}&type=${encodeURIComponent(type || "morning")}`
    );
  },

  getMyBriefings(openid, page, size) {
    const p = page || 1;
    const s = size || 20;
    return request(
      `/api/briefings/my?openid=${encodeURIComponent(openid || "anonymous")}&page=${p}&size=${s}`
    );
  },

  // 视频生成
  generateVideo(keyword, openid) {
    return request("/api/videos/generate", "POST", {
      keyword: keyword || "",
      openid: openid || "anonymous",
    });
  },

  getVideoStatus(videoId) {
    return request(`/api/videos/status/${encodeURIComponent(videoId)}`);
  },

  getVideoList(page, size) {
    const p = page || 1;
    const s = size || 10;
    return request(`/api/videos/list?page=${p}&size=${s}`);
  },

  getVideoFileUrl(videoId) {
    const baseUrl = app.globalData.baseUrl || config.baseUrl;
    return `${baseUrl}/api/videos/${encodeURIComponent(videoId)}/file`;
  },

  getVideoCoverUrl(videoId) {
    const baseUrl = app.globalData.baseUrl || config.baseUrl;
    return `${baseUrl}/api/videos/${encodeURIComponent(videoId)}/cover`;
  },

};
