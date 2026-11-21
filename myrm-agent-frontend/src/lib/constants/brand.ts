/**
 * [INPUT]
 * - 无
 *
 * [OUTPUT]
 * - OFFICIAL_SITE_URL: 官网根地址。
 * - OFFICIAL_DOWNLOAD_URL: 官网下载页。
 * - OFFICIAL_DOCS_URL: 文档站根地址，带 `/docs` 前缀的规范形态，页面路径直接拼在其后。
 *
 * [POS]
 * 前端里官方品牌地址（官网根、下载页、文档站根）的定义处。只放真实可达的官方地址；占位、示例与虚构的主机用保留域名
 * （`example.com` 系），不取这里的值，免得拼出看似官方、实际不存在的链接。
 */

export const OFFICIAL_SITE_URL = 'https://myrmagent.ai';

export const OFFICIAL_DOWNLOAD_URL = `${OFFICIAL_SITE_URL}/download`;

export const OFFICIAL_DOCS_URL = 'https://docs.myrmagent.ai/docs';
