#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SHEIN每日热点资讯收集脚本
每天定时执行，爬取SHEIN相关新闻并推送到钉钉群

使用方法:
1. 配置钉钉机器人参数
2. 设置定时任务: crontab -e
   0 9 * * * /usr/bin/python3 /path/to/shein_daily_news.py >> /path/to/shein_cron.log 2>&1
3. 手动测试: python3 shein_daily_news.py
"""

import os
import requests
import json
import time
import hmac
import hashlib
import base64
import re
import http.client
from datetime import datetime, timedelta
from urllib.parse import quote_plus, urlencode, quote
from difflib import SequenceMatcher
from xml.etree import ElementTree as ET

# 修复 Business of Fashion 等返回过多 headers 的问题
http.client._MAXHEADERS = 200

# ==================== 配置区域 ====================
# 钉钉机器人配置（从环境变量读取，也支持直接设置）
ACCESS_TOKEN = os.environ.get("DINGTALK_ACCESS_TOKEN", "")
SECRET = os.environ.get("DINGTALK_SECRET", "")

# 推送时间显示
PUSH_TIME = "上午10:00"

# 新闻源配置 - RSS源（经过验证可用的源）
# region: "cn" 国内源（优先抓取），"intl" 海外源
RSS_SOURCES = {
    # ==================== 国内源 ====================
    # Google News 中文定向搜索（直接命中 SHEIN/希音，聚合新华、新浪、雨果等国内媒体）
    "google_news_shein_cn": {
        "name": "Google新闻(SHEIN中文)",
        "rss_url": "https://news.google.com/rss/search?q=SHEIN+%E5%B8%8C%E9%9F%B3&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "keywords": ["SHEIN", "希音", "shein"],
        "region": "cn"
    },
    "google_news_chuhai": {
        "name": "Google新闻(中国企业出海)",
        "rss_url": "https://news.google.com/rss/search?q=%E4%B8%AD%E5%9B%BD%E4%BC%81%E4%B8%9A%E5%87%BA%E6%B5%B7+SHEIN&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "keywords": ["SHEIN", "希音", "shein"],
        "region": "cn"
    },
    "google_news_kuajing": {
        "name": "Google新闻(跨境电商SHEIN)",
        "rss_url": "https://news.google.com/rss/search?q=%E8%B7%A8%E5%A2%83%E7%94%B5%E5%95%86+SHEIN&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "keywords": ["SHEIN", "希音", "shein"],
        "region": "cn"
    },

    # 科技创业媒体（保留，有时有深度报道）
    "36kr": {
        "name": "36氪",
        "rss_url": "https://36kr.com/feed",
        "keywords": ["SHEIN", "希音", "shein"],
        "region": "cn"
    },

    # 财经商业媒体
    "jiebian": {
        "name": "界面新闻",
        "rss_url": "https://a.jiemian.com/index.php?m=article&a=rss",
        "keywords": ["SHEIN", "希音", "shein"],
        "region": "cn"
    },
    "tmtpost": {
        "name": "钛媒体",
        "rss_url": "https://www.tmtpost.com/rss.xml",
        "keywords": ["SHEIN", "希音", "shein"],
        "region": "cn"
    },

    # 跨境电商垂直媒体
    "ennews": {
        "name": "亿恩网",
        "rss_url": "https://www.ennews.com/rss",
        "keywords": ["SHEIN", "希音", "shein"],
        "region": "cn"
    },

    # ==================== 海外源 ====================
    # 时尚/零售英文媒体（SHEIN 命中率相对较高）
    "retail_dive": {
        "name": "Retail Dive",
        "rss_url": "https://www.retaildive.com/feeds/news/",
        "keywords": ["SHEIN", "希音", "shein"],
        "region": "intl"
    },
    "modern_retail": {
        "name": "Modern Retail",
        "rss_url": "https://www.modernretail.co/feed/",
        "keywords": ["SHEIN", "希音", "shein"],
        "region": "intl"
    },
    "bof": {
        "name": "Business of Fashion",
        "rss_url": "https://www.businessoffashion.com/feed/",
        "keywords": ["SHEIN", "希音", "shein"],
        "region": "intl"
    },
    "glossy": {
        "name": "Glossy",
        "rss_url": "https://www.glossy.co/feed/",
        "keywords": ["SHEIN", "希音", "shein"],
        "region": "intl"
    },
    "pymnts_ecommerce": {
        "name": "PYMNTS ECommerce",
        "rss_url": "https://www.pymnts.com/category/news/ecommerce/feed/",
        "keywords": ["SHEIN", "希音", "shein"],
        "region": "intl"
    },

    # Google News 英文聚合（SHEIN+Temu 关税/监管话题命中率高）
    "google_news_shein_temu": {
        "name": "Google新闻(SHEIN+Temu)",
        "rss_url": "https://news.google.com/rss/search?q=SHEIN+Temu",
        "keywords": ["SHEIN", "希音", "shein"],
        "region": "intl"
    },

    # ==================== 关键事件专项查询（兜底重大事件） ====================
    # 中文：调查/监管/上市
    "google_news_shein_diaocha_cn": {
        "name": "Google新闻(SHEIN+调查)",
        "rss_url": "https://news.google.com/rss/search?q=SHEIN+%E8%B0%83%E6%9F%A5&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "keywords": ["SHEIN", "希音", "shein"],
        "region": "cn"
    },
    "google_news_shein_jianguan_cn": {
        "name": "Google新闻(SHEIN+监管)",
        "rss_url": "https://news.google.com/rss/search?q=SHEIN+%E7%9B%91%E7%AE%A1&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "keywords": ["SHEIN", "希音", "shein"],
        "region": "cn"
    },
    "google_news_shein_ipo_cn": {
        "name": "Google新闻(SHEIN+上市)",
        "rss_url": "https://news.google.com/rss/search?q=SHEIN+%E4%B8%8A%E5%B8%82&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "keywords": ["SHEIN", "希音", "shein"],
        "region": "cn"
    },
    # 英文：investigation/regulation/IPO
    "google_news_shein_investigation": {
        "name": "Google News(SHEIN+investigation)",
        "rss_url": "https://news.google.com/rss/search?q=SHEIN+investigation",
        "keywords": ["SHEIN", "希音", "shein"],
        "region": "intl"
    },
    "google_news_shein_regulation": {
        "name": "Google News(SHEIN+regulation)",
        "rss_url": "https://news.google.com/rss/search?q=SHEIN+regulation",
        "keywords": ["SHEIN", "希音", "shein"],
        "region": "intl"
    },
    "google_news_shein_ipo_intl": {
        "name": "Google News(SHEIN+IPO)",
        "rss_url": "https://news.google.com/rss/search?q=SHEIN+IPO",
        "keywords": ["SHEIN", "希音", "shein"],
        "region": "intl"
    }
}

# 新闻API配置（需要申请API Key）
NEWS_APIS = {
    "newsapi": {
        "name": "NewsAPI",
        "enabled": False,  # 默认关闭，需要配置API Key
        "api_key": "",  # 请填写你的API Key
        "endpoint": "https://newsapi.org/v2/everything",
        "params": {
            "q": "SHEIN OR 希音",
            "language": "zh",
            "sortBy": "publishedAt",
            "pageSize": 10
        }
    },
    "gnews": {
        "name": "GNews",
        "enabled": False,  # 免费版有12小时延迟，无法获取实时资讯；升级付费版可重新启用
        "api_key": "86267ec8967fbe9eade57aba05d14224",
        "endpoint": "https://gnews.io/api/v4/search",
        "params": {
            "q": "SHEIN",
            "lang": "zh",
            "max": 10
        }
    }
}

# HTML 页面抓取源（非RSS，需要专用解析器）
HTML_SOURCES = {
    "baijing_newsflash": {
        "name": "白鲸出海7×24h",
        "url": "https://www.baijing.cn/newsflashes_txzq/",
        "keywords": ["SHEIN", "希音", "shein"],
        "region": "cn"
    },
}

# 最大新闻条数
MAX_NEWS_COUNT = 8
# 时间窗口（小时）- 设为36小时，避免重要新闻在两次执行之间因RSS排序漂移被漏抓
TIME_WINDOW_HOURS = 36
# 相似度阈值 - 超过此值的新闻会被合并（综合字符+实体相似度）
SIMILARITY_THRESHOLD = 0.5
# =================================================

DINGTALK_WEBHOOK = "https://oapi.dingtalk.com/robot/send"


def generate_sign(timestamp, secret):
    """生成钉钉签名"""
    if not secret:
        return ""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(secret.encode('utf-8'), string_to_sign.encode('utf-8'), digestmod=hashlib.sha256).digest()
    sign = quote_plus(base64.b64encode(hmac_code))
    return sign


def send_dingtalk_message(title, markdown_text):
    """发送钉钉 Markdown 消息"""
    timestamp = str(round(time.time() * 1000))
    sign = generate_sign(timestamp, SECRET)

    url = f"{DINGTALK_WEBHOOK}?access_token={ACCESS_TOKEN}"
    if sign:
        url += f"&timestamp={timestamp}&sign={sign}"

    headers = {
        "Content-Type": "application/json; charset=utf-8"
    }
    data = {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": markdown_text
        }
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def fetch_rss_news(source_name, source_config):
    """从RSS源获取新闻"""
    news_list = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
            "Referer": "https://www.google.com/",
            "Cache-Control": "max-age=0",
        }

        # 请求带重试（应对不稳定连接）
        response = None
        for attempt in range(2):
            try:
                response = requests.get(source_config["rss_url"], headers=headers, timeout=15)
                break
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt == 0:
                    time.sleep(2)
                else:
                    raise

        if response is None:
            return news_list

        raw_bytes = response.content

        # GBK/GB2312 编码预处理
        enc_match = re.search(rb'encoding=["\']([^"\']+)["\']', raw_bytes[:200])
        if enc_match:
            declared_enc = enc_match.group(1).decode('ascii').lower()
            if declared_enc in ('gbk', 'gb2312', 'gb18030'):
                text_content = raw_bytes.decode(declared_enc, errors='replace')
                text_content = re.sub(r'encoding=["\'][^"\']+["\']', 'encoding="utf-8"', text_content)
                raw_bytes = text_content.encode('utf-8')

        # 解析RSS（三层 fallback）
        root = None
        # 第一层：直接解析
        try:
            root = ET.fromstring(raw_bytes)
        except ET.ParseError:
            pass

        # 第二层：清理控制字符后重试
        if root is None:
            try:
                cleaned = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', '', raw_bytes.decode('utf-8', errors='replace'))
                root = ET.fromstring(cleaned.encode('utf-8'))
            except ET.ParseError:
                pass

        # 第三层：截断到根闭合标签（修复 Shopify Atom "junk after document element"）
        if root is None:
            text_for_truncate = raw_bytes.decode('utf-8', errors='replace')
            for closing_tag in ['</feed>', '</rss>']:
                idx = text_for_truncate.rfind(closing_tag)
                if idx != -1:
                    try:
                        truncated = text_for_truncate[:idx + len(closing_tag)]
                        root = ET.fromstring(truncated.encode('utf-8'))
                        break
                    except ET.ParseError:
                        continue

        if root is None:
            print(f"[{datetime.now()}] 获取{source_name}新闻失败: XML解析全部失败")
            return news_list
        
        # 处理不同RSS格式
        items = root.findall('.//item')
        if not items:
            # 尝试Atom格式
            items = root.findall('.//{http://www.w3.org/2005/Atom}entry')
        
        for item in items[:50]:  # 取前50条（Google News 等高频源信息密集，避免重要新闻被新热点挤出）
            # 提取标题
            title_elem = item.find('title')
            if title_elem is None:
                title_elem = item.find('.//{http://www.w3.org/2005/Atom}title')
            
            # 提取链接
            link_elem = item.find('link')
            if link_elem is None:
                link_elem = item.find('.//{http://www.w3.org/2005/Atom}link')
            
            # 提取发布时间
            pub_date_elem = item.find('pubDate')
            if pub_date_elem is None:
                pub_date_elem = item.find('dc:date')
                if pub_date_elem is None:
                    pub_date_elem = item.find('.//{http://www.w3.org/2005/Atom}updated')
            
            # 提取描述（优先 content:encoded，内容更完整）
            content_encoded_elem = item.find('{http://purl.org/rss/1.0/modules/content/}encoded')
            desc_elem = item.find('description')
            if desc_elem is None:
                desc_elem = item.find('.//{http://www.w3.org/2005/Atom}summary')
            
            if title_elem is None:
                continue
                
            title = title_elem.text or ""

            # Google News 标题格式为 "新闻标题 - 媒体名"，去掉尾部媒体名
            # 同时提取媒体来源用于显示
            actual_source = source_config["name"]
            if 'news.google.com' in source_config["rss_url"]:
                # Google News 格式："标题\s*-\s+媒体名"，包括无前导空格的连字符
                m = re.search(r'^(.*?)\s*[-–—]\s+([^-–—\n]+)$', title)
                if m:
                    actual_source = m.group(2).strip()
                    title = m.group(1).strip()
                    # 如果标题中还有中间媒体路径（如 "... - 某某新闻客户端"）一并去除
                    m2 = re.search(r'^(.*?)\s*[-–—]\s+([^-–—\n]+)$', title)
                    if m2:
                        suffix2 = m2.group(2).strip().lower()
                        if not any(k.lower() in suffix2 for k in source_config["keywords"]):
                            title = m2.group(1).strip()
            
            # 获取链接
            link = ""
            if link_elem is not None:
                link = link_elem.text or link_elem.get('href', '')

            # 修正源头数据错误：亿恩网 RSS 返回的链接域名是 www.en.com（错误），
            # 实际应为 www.ennews.com，否则点击 404
            if link and 'www.en.com' in link:
                link = link.replace('http://www.en.com', 'https://www.ennews.com').replace('https://www.en.com', 'https://www.ennews.com')
            
            pub_date = pub_date_elem.text if pub_date_elem is not None else ""

            # 描述优先取 content:encoded，其次取 description
            if content_encoded_elem is not None and content_encoded_elem.text:
                description = content_encoded_elem.text
            elif desc_elem is not None:
                description = desc_elem.text or ""
            else:
                description = ""
            
            # 检查是否包含SHEIN关键词（标题+描述都检查）
            content_to_check = (title + " " + description).lower()
            if not any(keyword.lower() in content_to_check for keyword in source_config["keywords"]):
                continue
            
            # 解析发布时间
            pub_datetime = parse_pub_date(pub_date)
            if pub_datetime is None:
                continue
                
            # 检查是否在时间窗口内
            time_diff = datetime.now() - pub_datetime
            if time_diff > timedelta(hours=TIME_WINDOW_HOURS):
                continue
            
            # 清理 HTML 标签和实体（&nbsp; &amp; 等）
            import html as html_mod
            clean_desc = re.sub(r'<[^>]+>', '', description) if description else ""
            if clean_desc:
                clean_desc = html_mod.unescape(clean_desc)
                clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()

            # Google News 的 description 通常与标题相同或仅有媒体名，如果和 title 重复就清空
            if clean_desc and 'news.google.com' in source_config["rss_url"]:
                # 去掉描述中的媒体名后缀（同标题清理逻辑）
                m_d = re.search(r'^(.*?)\s*[-–—]\s+([^-–—\n]+)$', clean_desc)
                if m_d:
                    clean_desc_body = m_d.group(1).strip()
                    m_d2 = re.search(r'^(.*?)\s*[-–—]\s+([^-–—\n]+)$', clean_desc_body)
                    if m_d2:
                        suf = m_d2.group(2).strip().lower()
                        if not any(k.lower() in suf for k in source_config["keywords"]):
                            clean_desc_body = m_d2.group(1).strip()
                    # 如果清理后与标题一样，不显示描述
                    if clean_desc_body.lower() == title.lower():
                        clean_desc = ""
                    else:
                        clean_desc = clean_desc_body

            # 翻译英文内容
            if is_english_text(title):
                title = translate_to_chinese(title)
                if clean_desc:
                    clean_desc = translate_to_chinese(clean_desc[:200])
            
            news_list.append({
                "title": title.strip(),
                "link": link.strip(),
                "source": actual_source,
                "pub_time": pub_datetime,
                "description": clean_desc.strip()[:200] if clean_desc else "",
                "hours_ago": int(time_diff.total_seconds() / 3600)
            })
            
    except Exception as e:
        print(f"[{datetime.now()}] 获取{source_name}新闻失败: {e}")
    
    return news_list


def fetch_newsapi_news():
    """从NewsAPI获取新闻"""
    news_list = []
    api_config = NEWS_APIS.get("newsapi")
    
    if not api_config or not api_config.get("enabled") or not api_config.get("api_key"):
        return news_list
    
    try:
        # 计算时间范围
        from_date = (datetime.now() - timedelta(hours=TIME_WINDOW_HOURS)).strftime("%Y-%m-%d")
        
        params = api_config["params"].copy()
        params["apiKey"] = api_config["api_key"]
        params["from"] = from_date
        
        response = requests.get(api_config["endpoint"], params=params, timeout=15)
        data = response.json()
        
        if data.get("status") == "ok":
            for article in data.get("articles", [])[:MAX_NEWS_COUNT]:
                pub_datetime = parse_pub_date(article.get("publishedAt", ""))
                if pub_datetime is None:
                    continue
                
                time_diff = datetime.now() - pub_datetime
                if time_diff > timedelta(hours=TIME_WINDOW_HOURS):
                    continue
                
                news_list.append({
                    "title": article.get("title", "").strip(),
                    "link": article.get("url", "").strip(),
                    "source": article.get("source", {}).get("name", "NewsAPI"),
                    "pub_time": pub_datetime,
                    "description": article.get("description", "")[:200] if article.get("description") else "",
                    "hours_ago": int(time_diff.total_seconds() / 3600)
                })
                
    except Exception as e:
        print(f"[{datetime.now()}] 获取NewsAPI新闻失败: {e}")
    
    return news_list


def fetch_gnews_news():
    """从GNews获取新闻（免费版有12小时延迟限制，仅作补充）"""
    news_list = []
    api_config = NEWS_APIS.get("gnews")

    if not api_config or not api_config.get("enabled") or not api_config.get("api_key"):
        return news_list

    try:
        from_date = (datetime.now() - timedelta(hours=TIME_WINDOW_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")

        params = api_config["params"].copy()
        params["token"] = api_config["api_key"]
        params["from"] = from_date

        response = requests.get(api_config["endpoint"], params=params, timeout=15)
        data = response.json()

        # 检测免费版限制提示
        if data.get("information"):
            for k, v in data["information"].items():
                msg = v.get("message", "") if isinstance(v, dict) else str(v)
                if msg:
                    print(f"[{datetime.now()}] GNews提示: {msg[:100]}")

        articles = data.get("articles", [])
        if not articles:
            print(f"[{datetime.now()}] GNews返回0条文章（免费版数据延迟或超出额度），跳过")
            return news_list

        for article in articles[:MAX_NEWS_COUNT]:
            pub_datetime = parse_pub_date(article.get("publishedAt", ""))
            if pub_datetime is None:
                continue

            time_diff = datetime.now() - pub_datetime
            if time_diff > timedelta(hours=TIME_WINDOW_HOURS):
                continue

            title = article.get("title", "").strip()
            description = article.get("description", "")
            if description:
                description = description[:200]

            # 翻译英文内容
            if is_english_text(title):
                title = translate_to_chinese(title)
                if description:
                    description = translate_to_chinese(description[:200])

            news_list.append({
                "title": title,
                "link": article.get("url", "").strip(),
                "source": article.get("source", {}).get("name", "GNews"),
                "pub_time": pub_datetime,
                "description": description or "",
                "hours_ago": int(time_diff.total_seconds() / 3600)
            })

    except Exception as e:
        print(f"[{datetime.now()}] 获取GNews新闻失败: {e}")

    return news_list


def fetch_baijing_news(source_config):
    """从白鲸出海7×24h快讯页面抓取新闻（HTML解析）"""
    news_list = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        response = requests.get(source_config["url"], headers=headers, timeout=15)
        html = response.text

        # 每条快讯是一个 <li class="get_time"> ... </li>
        items = re.findall(
            r'<li\s+class="get_time"[^>]*>(.*?)</li>\s*(?:<!--\s*单快讯\s*-->|$)',
            html, re.DOTALL
        )

        for item_html in items[:15]:
            # 提取时间：<span ...> 2026-03-16 11:43 </span>
            time_match = re.search(
                r'<span[^>]*>\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s*</span>',
                item_html
            )
            # 提取标题和链接：<h3 ...><a href="/newsflashes_txzq/17659">标题</a></h3>
            title_match = re.search(
                r'<h3[^>]*>\s*<a\s+href="(/newsflashes_txzq/\d+)"[^>]*>\s*(.*?)\s*</a>',
                item_html, re.DOTALL
            )
            # 提取描述：<div class="newsflashesText">描述内容</div>
            desc_match = re.search(
                r'<div\s+class="newsflashesText">\s*(.*?)\s*</div>',
                item_html, re.DOTALL
            )
            # 提取来源
            source_match = re.search(r'来源：(.*?)\s*<', item_html)

            if not title_match:
                continue

            title = re.sub(r'<[^>]+>', '', title_match.group(2)).strip()
            link = "https://www.baijing.cn" + title_match.group(1)

            pub_datetime = None
            if time_match:
                pub_datetime = parse_pub_date(time_match.group(1))
            if pub_datetime is None:
                pub_datetime = datetime.now()

            time_diff = datetime.now() - pub_datetime
            if time_diff > timedelta(hours=TIME_WINDOW_HOURS):
                continue

            description = ""
            if desc_match:
                import html
                description = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()
                description = html.unescape(description)
                description = re.sub(r'\s+', ' ', description).strip()[:200]

            # 检查是否包含关键词
            content_to_check = (title + " " + description).lower()
            if not any(kw.lower() in content_to_check for kw in source_config["keywords"]):
                continue

            original_source = source_config["name"]
            if source_match:
                original_source = source_match.group(1).strip()
                original_source = re.sub(r'<[^>]+>', '', original_source)

            news_list.append({
                "title": title,
                "link": link,
                "source": original_source,
                "pub_time": pub_datetime,
                "description": description,
                "hours_ago": int(time_diff.total_seconds() / 3600)
            })

    except Exception as e:
        print(f"[{datetime.now()}] 获取白鲸出海快讯失败: {e}")

    return news_list


# UTC+8 偏移量，用于将带时区信息的 UTC 时间转换为北京时间（本地时间）
_UTC8 = timedelta(hours=8)


def parse_pub_date(pub_date_str):
    """解析发布时间，统一返回北京时间 naive datetime（UTC+8）

    带时区信息（如 GMT/+00:00）的时间统一转为 UTC+8 再去掉 tzinfo；
    无时区信息的字符串（国内媒体通常直接输出北京时间）直接保留。
    这样所有时间都与 datetime.now()（本机 UTC+8）直接可比。
    """
    def _to_local(dt):
        """带 tzinfo 的 datetime 转换为北京时间 naive；无 tzinfo 直接返回"""
        if dt.tzinfo:
            # 转换为 UTC，再加 8 小时得到北京时间，去掉 tzinfo
            utc_naive = dt.utctimetuple()
            import calendar
            ts = calendar.timegm(utc_naive)
            return datetime(1970, 1, 1) + timedelta(seconds=ts) + _UTC8
        return dt

    if not pub_date_str:
        return datetime.now()

    # 带时区格式（GMT / %z）
    tz_formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    ]
    for fmt in tz_formats:
        try:
            dt = datetime.strptime(pub_date_str.strip(), fmt)
            return _to_local(dt)
        except:
            continue

    # 无时区格式（国内媒体，直接视为北京时间）
    local_formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ]
    for fmt in local_formats:
        try:
            return datetime.strptime(pub_date_str.strip(), fmt)
        except:
            continue

    # 尝试提取日期部分
    try:
        match = re.search(r'(\d{4}-\d{2}-\d{2})', pub_date_str)
        if match:
            return datetime.strptime(match.group(1), "%Y-%m-%d")
    except:
        pass

    # 都失败了，返回当前时间（假设是最新的）
    return datetime.now()


def is_english_text(text):
    """检测文本是否为英文（非CJK字符占多数）"""
    if not text:
        return False
    cjk_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return cjk_count / max(len(text), 1) < 0.1


# 翻译时需要保留原文的品牌名（不区分大小写替换，翻译后统一还原为标准写法）
PRESERVE_BRANDS = ["SHEIN", "Temu"]


def translate_to_chinese(text):
    """使用 Google Translate 免费 API 将文本翻译为中文，保留品牌名不翻译"""
    if not text or not is_english_text(text):
        return text
    try:
        # 用占位符替换品牌名，防止被翻译
        placeholders = {}
        modified = text
        for i, brand in enumerate(PRESERVE_BRANDS):
            ph = f"__BRAND{i}__"
            placeholders[ph] = brand
            modified = re.sub(re.escape(brand), ph, modified, flags=re.IGNORECASE)

        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": "zh-CN",
            "dt": "t",
            "q": modified[:500],
        }
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            result = resp.json()
            translated = ''.join(part[0] for part in result[0] if part[0])
            # 还原品牌名
            for ph, brand in placeholders.items():
                translated = translated.replace(ph, brand)
            return translated
    except Exception as e:
        print(f"[{datetime.now()}] 翻译失败: {e}")
    return text


def categorize_news(title, description):
    """对新闻进行分类"""
    text = (title + " " + description).lower()
    
    categories = {
        "投融资": ["ipo", "上市", "融资", "估值", "投资", "财报", "利润", "营收", "亿美元", "融资", "估值"],
        "外部合作": ["合作", "战略", "签约", "物流", "供应链", "菜鸟", "东航", "南航", "供应商"],
        "跨境电商": ["出海", "海外", "美国", "欧洲", "关税", "涨价", "市场", "扩张", "跨境"],
        "监管动态": ["监管", "合规", "法律", "诉讼", "禁令", "政策", "法国", "欧盟"],
        "高管动态": ["创始人", "ceo", "董事长", "高管", "许仰天", "亮相"]
    }
    
    for category, keywords in categories.items():
        if any(keyword in text for keyword in keywords):
            return category
    
    return "行业动态"


def fetch_all_news():
    """从所有新闻源获取新闻"""
    all_news = []
    
    # 从RSS源获取（国内源优先，海外源其次）
    sorted_sources = sorted(
        RSS_SOURCES.items(),
        key=lambda x: 0 if x[1].get("region") == "cn" else 1
    )
    for source_name, source_config in sorted_sources:
        print(f"[{datetime.now()}] 正在获取 {source_config['name']} 的新闻...")
        news = fetch_rss_news(source_name, source_config)
        all_news.extend(news)
        if news:
            print(f"[{datetime.now()}] 从 {source_config['name']} 获取到 {len(news)} 条新闻")
            for n in news:
                print(f"    - [{n['pub_time'].strftime('%Y-%m-%d %H:%M')}] [{n['source']}] {n['title'][:80]}")
        time.sleep(1)  # 避免请求过快

    # 从HTML页面源获取（国内源优先）
    sorted_html = sorted(
        HTML_SOURCES.items(),
        key=lambda x: 0 if x[1].get("region") == "cn" else 1
    )
    for source_name, source_config in sorted_html:
        print(f"[{datetime.now()}] 正在获取 {source_config['name']} 的新闻...")
        if source_name == "baijing_newsflash":
            news = fetch_baijing_news(source_config)
        else:
            continue
        all_news.extend(news)
        if news:
            print(f"[{datetime.now()}] 从 {source_config['name']} 获取到 {len(news)} 条新闻")
            for n in news:
                print(f"    - [{n['pub_time'].strftime('%Y-%m-%d %H:%M')}] [{n['source']}] {n['title'][:80]}")
        time.sleep(1)
    
    # 从NewsAPI获取（如果已启用）
    if NEWS_APIS.get("newsapi", {}).get("enabled"):
        print(f"[{datetime.now()}] 正在获取 NewsAPI 的新闻...")
        news = fetch_newsapi_news()
        all_news.extend(news)
        if news:
            print(f"[{datetime.now()}] 从 NewsAPI 获取到 {len(news)} 条新闻")

    # 从GNews获取（如果已启用）
    if NEWS_APIS.get("gnews", {}).get("enabled"):
        print(f"[{datetime.now()}] 正在获取 GNews 的新闻...")
        news = fetch_gnews_news()
        all_news.extend(news)
        if news:
            print(f"[{datetime.now()}] 从 GNews 获取到 {len(news)} 条新闻")
    
    # 按时间排序，最新的在前
    all_news.sort(key=lambda x: x["pub_time"], reverse=True)

    total_before = len(all_news)

    # 去重合并（基于标题+描述相似度）
    merged_news = []
    for news in all_news:
        # 初始化多源字段
        news['sources'] = [news['source']]
        news['all_links'] = [{'source': news['source'], 'link': news.get('link', '')}]

        # 在已有组中寻找最佳匹配
        best_idx = -1
        best_score = 0.0
        for idx, existing in enumerate(merged_news):
            score = compute_similarity(news, existing)
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_score >= SIMILARITY_THRESHOLD and best_idx >= 0:
            merge_news_item(merged_news[best_idx], news)
        else:
            merged_news.append(news)

    print(f"[{datetime.now()}] 去重合并：{total_before} → {len(merged_news)} 条")

    # 重要度加权：监管/诉讼/IPO 等重大事件优先保留，避免被截断丢弃
    # 排序键：(重要度降序, 多源数降序, 时间降序)
    merged_news.sort(
        key=lambda n: (
            -compute_importance(n),
            -len(n.get('sources', [n.get('source', '')])),
            -n['pub_time'].timestamp() if n.get('pub_time') else 0
        )
    )

    # 打印重要度分级（便于排查）
    high_priority = [n for n in merged_news if compute_importance(n) >= 2]
    if high_priority:
        print(f"[{datetime.now()}] 高重要度事件 {len(high_priority)} 条（优先保留）")
        for n in high_priority[:5]:
            print(f"    ⭐ [{n['source']}] {n['title'][:80]}")

    return merged_news[:MAX_NEWS_COUNT]


# 重大事件关键词 → 重要度评分
# 重要度 ≥2 的新闻在最终截断时优先保留，确保监管/诉讼/IPO 等重大事件不会被普通新闻挤掉
_IMPORTANCE_KEYWORDS = {
    3: [  # 最高重要度：监管调查/诉讼/数据安全
        '调查', '诉讼', '禁令', '罚款', '处罚', '裁定', '裁决', '判决', '反垄断', '数据保护', '数据合规',
        'investigation', 'lawsuit', 'fine', 'penalty', 'ruling', 'antitrust', 'gdpr', 'data protection',
        'dpc', 'data transfer',
    ],
    2: [  # 较高重要度：监管/合规/IPO/上市
        '监管', '合规', '禁止', '暂停', '审查', 'ipo', '上市', '招股', '挂牌', '估值', '反垄断',
        'regulation', 'compliance', 'sec filing', 'listing', 'valuation', 'probe',
    ],
    1: [  # 普通重要度：合作/扩张/财报
        '合作', '扩张', '财报', '战略', 'partnership', 'expansion', 'earnings',
    ],
}


def compute_importance(news):
    """计算新闻重要度（0-3）。监管/诉讼类事件分数高，截断时优先保留"""
    text = ((news.get('title') or '') + ' ' + (news.get('description') or '')).lower()
    for score in (3, 2, 1):
        for kw in _IMPORTANCE_KEYWORDS[score]:
            if kw.lower() in text:
                return score
    return 0


def compute_similarity(news_a, news_b):
    """计算两条新闻的相似度，综合字符相似度和实体重叠度

    防止误合并：
    - 实体使用 Jaccard 系数 + 最小分母 2，避免单实体重叠 = 1.0
    - 增加事件关键词硬约束：两条新闻必须共享至少一个事件关键词，否则不合并
    - 字符相似度过低（<0.3）时直接判为不相似
    """
    title_a_raw = news_a.get('title') or ''
    title_b_raw = news_b.get('title') or ''
    title_a = normalize_title(title_a_raw)
    title_b = normalize_title(title_b_raw)

    if not title_a or not title_b:
        return 0.0

    # 1) 字符级相似度
    char_sim = SequenceMatcher(None, title_a, title_b).ratio()

    # 字符相似度过低 → 不可能是同一事件，直接返回（但允许实体强重叠时仍判定）
    # 注：单纯标题完全不像（如"深圳严查"vs"激战法庭"）即使品牌相同也不应合并
    if char_sim < 0.3:
        # 进一步要求事件关键词强重叠才允许合并
        ent_a = extract_entities(title_a_raw)
        ent_b = extract_entities(title_b_raw)
        # 事件关键词（与品牌/地名分开判断）
        event_a = ent_a - {'shein', 'temu', '中国', '美国', '欧洲', '法国', '德国', '英国', '日本', '越南', '印度', '韩国', '巴西', '澳大利亚', '加拿大', '新加坡', '泰国', '马来西亚', '印尼'}
        event_b = ent_b - {'shein', 'temu', '中国', '美国', '欧洲', '法国', '德国', '英国', '日本', '越南', '印度', '韩国', '巴西', '澳大利亚', '加拿大', '新加坡', '泰国', '马来西亚', '印尼'}
        # 没有共同事件关键词 → 直接判定不相似
        if not (event_a & event_b):
            return 0.0

    # 2) 实体重叠度（Jaccard 系数，分母至少为 2，避免单实体即 100% 重合）
    ent_a = extract_entities(title_a_raw)
    ent_b = extract_entities(title_b_raw)
    if ent_a and ent_b:
        union_size = len(ent_a | ent_b)
        ent_overlap = len(ent_a & ent_b) / max(union_size, 2)
    else:
        ent_overlap = 0.0

    # 3) 描述辅助（如果有）
    desc_a = (news_a.get('description') or '').lower()
    desc_b = (news_b.get('description') or '').lower()
    desc_bonus = 0.0
    if desc_a and desc_b:
        desc_sim = SequenceMatcher(None, desc_a[:200], desc_b[:200]).ratio()
        desc_bonus = 0.1 * desc_sim

    # 综合得分：字符权重提升（同一事件标题字面重合度通常较高）
    combined = 0.5 * char_sim + 0.5 * ent_overlap + desc_bonus

    return min(combined, 1.0)


# 地名同义词映射（城市 -> 国家）
_PLACE_ALIASES = {
    '巴黎': '法国', '里昂': '法国', '马赛': '法国',
    '柏林': '德国', '慕尼黑': '德国',
    '伦敦': '英国', '曼彻斯特': '英国',
    '北京': '中国', '上海': '中国', '深圳': '中国', '广州': '中国',
    '东京': '日本', '首尔': '韩国', '河内': '越南',
    '纽约': '美国', '华盛顿': '美国', '旧金山': '美国',
    '新德里': '印度', '孟买': '印度',
}


def normalize_title(text):
    """标题归一化：去掉来源后缀，统一空格"""
    text = re.sub(r'\s*[-–—]\s*[A-Za-z][\w\s.]*$', '', text)
    text = re.sub(r'\s+', ' ', text).strip().lower()
    return text


def extract_entities(text):
    """从标题中提取核心实体（品牌、地名、机构/事件关键词）用于相似度计算"""
    text_lower = normalize_title(text)
    entities = set()

    # 品牌名
    for brand in PRESERVE_BRANDS:
        if brand.lower() in text_lower:
            entities.add(brand.lower())

    # 地名（含同义词归一化：巴黎->法国）
    place_pattern = '|'.join(re.escape(p) for p in list(_PLACE_ALIASES.keys()) + [
        '法国', '德国', '中国', '欧洲', '美国', '英国', '日本', '越南', '印度', '韩国',
        '巴西', '澳大利亚', '加拿大', '新加坡', '泰国', '马来西亚', '印尼',
    ])
    for place in re.findall(f'({place_pattern})', text):
        canonical = _PLACE_ALIASES.get(place, place)
        entities.add(canonical)

    # 事件/机构关键词
    event_keywords = (
        '法院|上诉|市场|禁令|禁止|暂停|驳回|阻止|关闭|平台|裁定|裁决|判决|审判|'
        '监管|罚款|调查|收购|合并|上市|融资|IPO|合作|诉讼|关税|制裁'
    )
    for kw in re.findall(f'({event_keywords})', text):
        entities.add(kw)

    return entities


def _content_score(news):
    """计算新闻内容丰富度评分"""
    return len(news.get('title') or '') + len(news.get('description') or '')


def merge_news_item(group, new_item):
    """将 new_item 合并进 group（就地修改 group）"""
    # 如果新条目内容更丰富，替换标题/描述/主链接
    if _content_score(new_item) > _content_score(group):
        group['title'] = new_item['title']
        group['link'] = new_item['link']

    # 描述取更长的
    new_desc = new_item.get('description') or ''
    old_desc = group.get('description') or ''
    if len(new_desc) > len(old_desc):
        group['description'] = new_desc

    # 时间取最新的
    if new_item.get('pub_time') and new_item['pub_time'] > group.get('pub_time', datetime.min):
        group['pub_time'] = new_item['pub_time']

    # hours_ago 取最小值
    group['hours_ago'] = min(group.get('hours_ago', 9999), new_item.get('hours_ago', 9999))

    # 合并来源（去重）
    new_source = new_item.get('source', '')
    if new_source and new_source not in group['sources']:
        group['sources'].append(new_source)
        group['source'] = '\u3001'.join(group['sources'])

    # 合并链接（按 link 去重）
    new_link = new_item.get('link', '')
    existing_links = {item['link'] for item in group['all_links']}
    if new_link and new_link not in existing_links:
        group['all_links'].append({
            'source': new_source,
            'link': new_link
        })


def format_news_content(news_list):
    """格式化新闻内容为钉钉 Markdown 格式，返回 (title, text) 元组"""
    if not news_list:
        return None
    
    today = datetime.now().strftime("%Y年%m月%d日")
    title = "SHEIN每日热点资讯"
    
    text = f"# 📰 SHEIN每日热点资讯（{today}）\n\n---\n\n"
    
    for i, news in enumerate(news_list, 1):
        category = categorize_news(news["title"], news["description"])
        hours_ago = news.get("hours_ago", 0)
        time_str = f"{hours_ago}小时前" if hours_ago < 24 else f"{hours_ago // 24}天前"
        
        text += f"### {i}. 【{category}】{news['title']}\n\n"
        
        # 添加描述（截取约50字）
        desc = news.get("description", "")
        if desc and len(desc) > 20:
            display_desc = desc[:50] + "..." if len(desc) > 50 else desc
            text += f"{display_desc}\n\n"
        
        link = news.get('link', '')
        all_links = news.get('all_links', [])

        text += f"📰 来源：{news['source']} | ⏱️ {time_str}"
        if all_links and len(all_links) > 1:
            # 多来源：为每个来源生成独立链接，最多展示3个
            link_parts = []
            for item in all_links[:3]:
                if item.get('link'):
                    link_parts.append(f"[{item['source']}]({item['link']})")
            if link_parts:
                text += ' | ' + ' | '.join(link_parts)
            if len(all_links) > 3:
                text += f" 等{len(all_links)}家媒体报道"
        elif link:
            text += f" | [查看原文]({link})"
        text += "\n\n---\n\n"
    
    text += f"> ⏰ 每日推送时间：{PUSH_TIME} | 📊 监控范围：外部合作、投融资、跨境电商、监管动态 | ⏱️ 过去{TIME_WINDOW_HOURS}小时"
    
    return (title, text)


def main():
    """主函数"""
    if not ACCESS_TOKEN:
        print(f"[{datetime.now()}] 错误：未设置 DINGTALK_ACCESS_TOKEN 环境变量")
        return
    
    print(f"[{datetime.now()}] 开始收集SHEIN新闻...")
    print(f"[{datetime.now()}] 时间窗口：过去{TIME_WINDOW_HOURS}小时")
    
    # 获取新闻
    news_list = fetch_all_news()
    
    print(f"[{datetime.now()}] 共收集到 {len(news_list)} 条新闻")
    
    if not news_list:
        print(f"[{datetime.now()}] 过去{TIME_WINDOW_HOURS}小时内未找到SHEIN相关新闻")
        today = datetime.now().strftime("%Y年%m月%d日")
        title = "SHEIN每日热点资讯"
        text = f"# 📰 SHEIN每日热点资讯（{today}）\n\n"
        text += f"过去{TIME_WINDOW_HOURS}小时内暂无SHEIN相关新闻更新。\n\n"
        text += f"> ⏰ 每日推送时间：{PUSH_TIME} | 📊 监控范围：外部合作、投融资、跨境电商、监管动态 | ⏱️ 过去{TIME_WINDOW_HOURS}小时"
        result = send_dingtalk_message(title, text)
        print(f"[{datetime.now()}] 发送结果: {result}")
        return
    
    # 格式化内容
    result = format_news_content(news_list)
    
    if result:
        title, text = result
        # 发送钉钉消息
        send_result = send_dingtalk_message(title, text)
        print(f"[{datetime.now()}] 发送结果: {send_result}")


if __name__ == "__main__":
    main()
