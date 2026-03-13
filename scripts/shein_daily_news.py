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

# 新闻源配置 - RSS源（10+权威媒体，经过验证可用的源）
RSS_SOURCES = {
    # 综合财经媒体（已验证可用）
    "sina_finance": {
        "name": "新浪财经",
        "rss_url": "https://rss.sina.com.cn/roll/finance/hot_roll.xml",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    "sina_tech": {
        "name": "新浪科技",
        "rss_url": "https://rss.sina.com.cn/tech/rollnews.xml",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    
    # 科技创业媒体（已验证可用）
    "36kr": {
        "name": "36氪",
        "rss_url": "https://36kr.com/feed",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    
    # 财经商业媒体（已验证可用）
    "jiebian": {
        "name": "界面新闻",
        "rss_url": "https://a.jiemian.com/index.php?m=article&a=rss",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    
    # 其他可用源
    "huxiu": {
        "name": "虎嗅",
        "rss_url": "https://www.huxiu.com/rss/0.xml",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    "geekpark": {
        "name": "极客公园",
        "rss_url": "https://www.geekpark.net/rss",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    "cyzone": {
        "name": "创业邦",
        "rss_url": "https://www.cyzone.cn/rss/",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    "tmtpost": {
        "name": "钛媒体",
        "rss_url": "https://www.tmtpost.com/rss.xml",
        "keywords": ["SHEIN", "希音", "shein"]
    },

    # 国际电商平台博客
    "shopify_blog": {
        "name": "Shopify Blog",
        "rss_url": "https://www.shopify.com/blog.atom",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    "shopify_editions": {
        "name": "Shopify Editions",
        "rss_url": "https://www.shopify.com/editions/feed",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    "woocommerce": {
        "name": "WooCommerce Blog",
        "rss_url": "https://woocommerce.com/blog/feed/",
        "keywords": ["SHEIN", "希音", "shein"]
    },

    # 电商行业英文媒体
    "practical_ecommerce": {
        "name": "Practical Ecommerce",
        "rss_url": "https://www.practicalecommerce.com/feed",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    "sej_ecommerce": {
        "name": "Search Engine Journal",
        "rss_url": "https://www.searchenginejournal.com/category/ecommerce/feed/",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    "search_engine_land": {
        "name": "Search Engine Land",
        "rss_url": "https://searchengineland.com/feed",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    "martech": {
        "name": "MarTech",
        "rss_url": "https://martech.org/feed/",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    "retail_dive": {
        "name": "Retail Dive",
        "rss_url": "https://www.retaildive.com/feeds/news/",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    "digital_commerce_360": {
        "name": "Digital Commerce 360",
        "rss_url": "https://www.digitalcommerce360.com/feed/",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    "modern_retail": {
        "name": "Modern Retail",
        "rss_url": "https://www.modernretail.co/feed/",
        "keywords": ["SHEIN", "希音", "shein"]
    },

    # 跨境电商中文媒体
    "ennews": {
        "name": "亿恩网",
        "rss_url": "https://www.ennews.com/rss",
        "keywords": ["SHEIN", "希音", "shein"]
    },

    # SHEIN官方 & 时尚零售
    "retail_touchpoints": {
        "name": "Retail TouchPoints",
        "rss_url": "https://www.retailtouchpoints.com/feed",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    "pymnts_ecommerce": {
        "name": "PYMNTS ECommerce",
        "rss_url": "https://www.pymnts.com/category/news/ecommerce/feed/",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    "bof": {
        "name": "Business of Fashion",
        "rss_url": "https://www.businessoffashion.com/feed/",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    "glossy": {
        "name": "Glossy",
        "rss_url": "https://www.glossy.co/feed/",
        "keywords": ["SHEIN", "希音", "shein"]
    },

    # Google News 聚合
    "google_news_shein": {
        "name": "Google新闻(SHEIN)",
        "rss_url": "https://news.google.com/rss/search?q=SHEIN",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    "google_news_shein_temu": {
        "name": "Google新闻(SHEIN+Temu)",
        "rss_url": "https://news.google.com/rss/search?q=SHEIN+Temu",
        "keywords": ["SHEIN", "希音", "shein"]
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
        "enabled": False,  # 默认关闭，需要配置API Key
        "api_key": "",  # 请填写你的API Key
        "endpoint": "https://gnews.io/api/v4/search",
        "params": {
            "q": "SHEIN",
            "lang": "zh",
            "max": 10
        }
    }
}

# 最大新闻条数
MAX_NEWS_COUNT = 8
# 时间窗口（小时）- 只获取过去24小时的新闻
TIME_WINDOW_HOURS = 24
# 相似度阈值 - 超过此值的新闻会被合并
SIMILARITY_THRESHOLD = 0.8
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
        
        for item in items[:15]:  # 只取前15条
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
            
            # 提取描述
            desc_elem = item.find('description')
            if desc_elem is None:
                desc_elem = item.find('.//{http://www.w3.org/2005/Atom}summary')
            
            if title_elem is None:
                continue
                
            title = title_elem.text or ""
            
            # 获取链接
            link = ""
            if link_elem is not None:
                link = link_elem.text or link_elem.get('href', '')
            
            pub_date = pub_date_elem.text if pub_date_elem is not None else ""
            description = desc_elem.text if desc_elem is not None else ""
            
            # 检查是否包含SHEIN关键词
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
            
            # 清理描述中的HTML标签
            clean_desc = re.sub(r'<[^>]+>', '', description) if description else ""

            # 翻译英文内容
            if is_english_text(title):
                title = translate_to_chinese(title)
                if clean_desc:
                    clean_desc = translate_to_chinese(clean_desc[:200])
            
            news_list.append({
                "title": title.strip(),
                "link": link.strip(),
                "source": source_config["name"],
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


def parse_pub_date(pub_date_str):
    """解析发布时间，统一返回 naive datetime"""
    def _strip_tz(dt):
        return dt.replace(tzinfo=None) if dt.tzinfo else dt

    if not pub_date_str:
        return datetime.now()
    
    # 尝试多种日期格式
    date_formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    ]
    
    for fmt in date_formats:
        try:
            return _strip_tz(datetime.strptime(pub_date_str.strip(), fmt))
        except:
            continue
    
    # 尝试提取日期部分
    try:
        # 匹配 YYYY-MM-DD 格式
        match = re.search(r'(\d{4}-\d{2}-\d{2})', pub_date_str)
        if match:
            return _strip_tz(datetime.strptime(match.group(1), "%Y-%m-%d"))
    except:
        pass
    
    # 如果都失败了，返回当前时间（假设是最新的）
    return datetime.now()


def is_english_text(text):
    """检测文本是否为英文（非CJK字符占多数）"""
    if not text:
        return False
    cjk_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return cjk_count / max(len(text), 1) < 0.1


def translate_to_chinese(text):
    """使用 Google Translate 免费 API 将文本翻译为中文"""
    if not text or not is_english_text(text):
        return text
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": "zh-CN",
            "dt": "t",
            "q": text[:500],
        }
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            result = resp.json()
            translated = ''.join(part[0] for part in result[0] if part[0])
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
    
    # 从RSS源获取
    for source_name, source_config in RSS_SOURCES.items():
        print(f"[{datetime.now()}] 正在获取 {source_config['name']} 的新闻...")
        news = fetch_rss_news(source_name, source_config)
        all_news.extend(news)
        if news:
            print(f"[{datetime.now()}] 从 {source_config['name']} 获取到 {len(news)} 条新闻")
        time.sleep(1)  # 避免请求过快
    
    # 从NewsAPI获取（如果已启用）
    if NEWS_APIS.get("newsapi", {}).get("enabled"):
        print(f"[{datetime.now()}] 正在获取 NewsAPI 的新闻...")
        news = fetch_newsapi_news()
        all_news.extend(news)
        if news:
            print(f"[{datetime.now()}] 从 NewsAPI 获取到 {len(news)} 条新闻")
    
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

    return merged_news[:MAX_NEWS_COUNT]


def compute_similarity(news_a, news_b):
    """计算两条新闻的相似度，综合比较标题和描述"""
    title_a = (news_a.get('title') or '').lower()
    title_b = (news_b.get('title') or '').lower()

    if not title_a or not title_b:
        return 0.0

    title_sim = SequenceMatcher(None, title_a, title_b).ratio()

    desc_a = (news_a.get('description') or '').lower()
    desc_b = (news_b.get('description') or '').lower()

    if desc_a and desc_b:
        desc_sim = SequenceMatcher(None, desc_a, desc_b).ratio()
        weighted = 0.6 * title_sim + 0.4 * desc_sim
        return max(title_sim, weighted)

    return title_sim


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
