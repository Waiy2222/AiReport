const app = getApp();

function request(url, method = "GET", data = null) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${app.globalData.baseUrl}${url}`,
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

  getBriefingHistory(page = 1, size = 20, keyword = "") {
    let url = `/api/briefings/history?page=${page}&size=${size}`;
    if (keyword) url += `&keyword=${encodeURIComponent(keyword)}`;
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
};
