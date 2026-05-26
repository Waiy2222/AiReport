// ============================================================
// API Helper Module — Module C WeChat Mini Program
// Base URL can be overridden via globalData or storage
// ============================================================

const DEFAULT_BASE_URL = 'http://localhost:8003';

/**
 * Get the current base URL from app globalData or fall back to default.
 */
function getBaseUrl() {
  const app = getApp();
  if (app && app.globalData && app.globalData.apiBaseUrl) {
    return app.globalData.apiBaseUrl;
  }
  return DEFAULT_BASE_URL;
}

/**
 * Unified request wrapper.
 * Automatically shows/hides loading, handles HTTP errors, and parses responses.
 *
 * @param {string}   path    — API path, e.g. "/api/briefings/latest"
 * @param {object}   options — { method, data, loading, contentType }
 * @returns {Promise<any>}
 */
function request(path, options = {}) {
  const {
    method = 'GET',
    data = null,
    loading = true,
    contentType = 'application/json',
  } = options;

  const baseUrl = getBaseUrl();
  const url = baseUrl.replace(/\/+$/, '') + '/' + path.replace(/^\/+/, '');

  if (loading) {
    wx.showLoading({ title: '加载中...', mask: true });
  }

  return new Promise((resolve, reject) => {
    wx.request({
      url,
      method,
      data,
      header: {
        'Content-Type': contentType,
      },
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          const msg =
            (res.data && res.data.detail) ||
            (res.data && res.data.message) ||
            `请求失败 (${res.statusCode})`;
          wx.showToast({ title: msg, icon: 'none', duration: 2500 });
          reject(new Error(msg));
        }
      },
      fail(err) {
        const msg = err.errMsg || '网络请求失败，请检查网络连接';
        wx.showToast({ title: msg, icon: 'none', duration: 2500 });
        reject(err);
      },
      complete() {
        if (loading) {
          wx.hideLoading();
        }
      },
    });
  });
}

// ---- Public API functions ----

/**
 * Get the latest briefing for the specified type.
 * @param {"morning"|"evening"} type
 * @returns {Promise<object>} { id, type, date, tl_dr, sections, key_takeaways, generated_at }
 */
function getLatestBriefing(type) {
  return request('/api/briefings/latest', {
    data: { type },
    loading: true,
  });
}

/**
 * Get paginated briefing history.
 * @param {number} page — page number (1-based)
 * @param {number} size — items per page (max 100)
 * @returns {Promise<object>} { page, size, total, items: [{id, type, date, tl_dr, generated_at}] }
 */
function getHistory(page = 1, size = 20) {
  return request('/api/briefings/history', {
    data: { page, size },
    loading: page === 1,
  });
}

/**
 * Subscribe to push notifications.
 * @param {string} openid
 * @param {boolean} morningEnabled
 * @param {boolean} eveningEnabled
 * @returns {Promise<object>} { status, openid }
 */
function subscribe(openid, morningEnabled = true, eveningEnabled = true) {
  return request('/api/subscribe', {
    method: 'POST',
    data: {
      openid,
      morning_enabled: morningEnabled,
      evening_enabled: eveningEnabled,
    },
  });
}

/**
 * Unsubscribe from push notifications.
 * @param {string} openid
 * @returns {Promise<object>} { status, openid }
 */
function unsubscribe(openid) {
  return request('/api/unsubscribe', {
    method: 'POST',
    data: { openid },
  });
}

module.exports = {
  getBaseUrl,
  getLatestBriefing,
  getHistory,
  subscribe,
  unsubscribe,
  request,
};
