/**
 * 环境配置 — 上线前修改 ENV 和 PROD_BASE_URL
 *
 * 切换步骤：
 *   1. 将 ENV 改为 'production'
 *   2. 将 PROD_BASE_URL 改为你的 HTTPS 域名
 *   3. 在微信公众平台配置服务器域名白名单
 */

const ENV = "development"; // 'development' | 'production'

const DEV_BASE_URL = "http://localhost:8003";
const PROD_BASE_URL = "https://vcast.asia"; // 生产环境域名

const baseUrl = ENV === "production" ? PROD_BASE_URL : DEV_BASE_URL;

module.exports = {
  ENV,
  baseUrl,
  DEV_BASE_URL,
  PROD_BASE_URL,
};
