const api = require("../../utils/api.js");

Page({
  data: {
    messages: [],        // [{role, content, sources}]
    inputValue: "",
    loading: false,
    scrollToId: "",
    suggestions: [
      "今日AI领域有哪些大事？",
      "最近有哪些重要的开源项目发布？",
      "今天科技行业有什么重要新闻？",
      "最近AI融资方面有什么动向？",
    ],
  },

  onLoad() {
    this._initSuggestions();
  },

  async _initSuggestions() {
    try {
      const resp = await api.getChatSuggestions();
      if (resp.suggestions && resp.suggestions.length > 0) {
        this.setData({ suggestions: resp.suggestions });
      }
    } catch (e) {
      // 使用默认推荐，无需处理
    }
  },

  onInput(e) {
    this.setData({ inputValue: e.detail.value });
  },

  onTopicTap(e) {
    const topic = e.currentTarget.dataset.topic;
    this.setData({ inputValue: topic });
    this._doSend(topic);
  },

  async onSend() {
    const msg = this.data.inputValue.trim();
    if (!msg || this.data.loading) return;
    this._doSend(msg);
  },

  async _doSend(msg) {
    // 添加用户消息
    const messages = [...this.data.messages, { role: "user", content: msg, sources: [] }];
    this.setData({
      messages,
      inputValue: "",
      loading: true,
      scrollToId: "",
    });

    // 滚动到底部
    this._scrollToBottom();

    try {
      const resp = await api.chatSend(msg);
      const aiMsg = {
        role: "assistant",
        content: resp.reply || "抱歉，出了点问题。",
        sources: resp.sources || [],
      };
      this.setData({
        messages: [...this.data.messages, aiMsg],
        loading: false,
      });
    } catch (e) {
      console.error("Chat send failed:", e);
      this.setData({
        messages: [
          ...this.data.messages,
          {
            role: "assistant",
            content: "抱歉，网络出了点问题，请稍后再试。",
            sources: [],
          },
        ],
        loading: false,
      });
    }

    this._scrollToBottom();
  },

  _scrollToBottom() {
    setTimeout(() => {
      this.setData({ scrollToId: "msg-bottom" });
    }, 100);
  },

  onSourceTap(e) {
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
