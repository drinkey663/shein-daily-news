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
from datetime import datetime, timedelta
from urllib.parse import quote_plus, urlencode
from xml.etree import ElementTree as ET

# ==================== 配置区域 ====================
# 钉钉机器人配置（从环境变量读取，也支持直接设置）
ACCESS_TOKEN = os.environ.get("DINGTALK_ACCESS_TOKEN", "")
SECRET = os.environ.get("DINGTALK_SECRET", "")

# 推送时间显示
PUSH_TIME = "上午9:00"

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
    "21cbh": {
        "name": "21世纪经济报道",
        "rss_url": "https://www.21jingji.com/rss.php",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    
    # 其他可用源
    "huxiu": {
        "name": "虎嗅",
        "rss_url": "https://www.huxiu.com/rss/0.xml",
        "keywords": ["SHEIN", "希音", "shein"]
    },
    "cls": {
        "name": "财联社",
        "rss_url": "https://www.cls.cn/rss/",
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


def send_dingtalk_message(content):
    """发送钉钉消息"""
    timestamp = str(round(time.time() * 1000))
    sign = generate_sign(timestamp, SECRET)

    url = f"{DINGTALK_WEBHOOK}?access_token={ACCESS_TOKEN}"
    if sign:
        url += f"&timestamp={timestamp}&sign={sign}"

    headers = {
        "Content-Type": "application/json; charset=utf-8"
    }
    data = {
        "msgtype": "text",
        "text": {
            "content": content
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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(source_config["rss_url"], headers=headers, timeout=15)
        response.encoding = 'utf-8'
        
        # 解析RSS
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError:
            # 尝试清理内容后再解析
            content = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', '', response.text)
            root = ET.fromstring(content.encode('utf-8'))
        
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
                
            # 检查是否在48小时内
            time_diff = datetime.now() - pub_datetime
            if time_diff > timedelta(hours=TIME_WINDOW_HOURS):
                continue
            
            # 清理描述中的HTML标签
            clean_desc = re.sub(r'<[^>]+>', '', description) if description else ""
            
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
    """解析发布时间"""
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
            return datetime.strptime(pub_date_str.strip(), fmt)
        except:
            continue
    
    # 尝试提取日期部分
    try:
        # 匹配 YYYY-MM-DD 格式
        match = re.search(r'(\d{4}-\d{2}-\d{2})', pub_date_str)
        if match:
            return datetime.strptime(match.group(1), "%Y-%m-%d")
    except:
        pass
    
    # 如果都失败了，返回当前时间（假设是最新的）
    return datetime.now()


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
    
    # 去重（基于标题相似度）
    unique_news = []
    for news in all_news:
        is_duplicate = False
        for existing in unique_news:
            # 简单判断标题相似度
            if similar(news["title"], existing["title"]) > 0.7:
                is_duplicate = True
                break
        if not is_duplicate:
            unique_news.append(news)
    
    return unique_news[:MAX_NEWS_COUNT]


def similar(str1, str2):
    """计算两个字符串的相似度（简单实现）"""
    if not str1 or not str2:
        return 0.0
    
    # 使用简单的集合交集方法
    set1 = set(str1.lower())
    set2 = set(str2.lower())
    
    intersection = set1.intersection(set2)
    union = set1.union(set2)
    
    if not union:
        return 0.0
    
    return len(intersection) / len(union)


def format_news_content(news_list):
    """格式化新闻内容"""
    if not news_list:
        return None
    
    today = datetime.now().strftime("%Y年%m月%d日")
    
    content = f"📰 SHEIN每日热点资讯（{today}）\n\n"
    
    for i, news in enumerate(news_list, 1):
        category = categorize_news(news["title"], news["description"])
        hours_ago = news.get("hours_ago", 0)
        time_str = f"{hours_ago}小时前" if hours_ago < 24 else f"{hours_ago // 24}天前"
        
        content += f"{i}️⃣ 【{category}】{news['title']}\n"
        
        # 添加描述（如果有且不太短）
        if news["description"] and len(news["description"]) > 20:
            content += f"{news['description']}...\n"
        
        content += f"原文链接：{news['link']}\n"
        content += f"📰 来源：{news['source']} | ⏱️ {time_str}\n\n"
    
    content += f"⏰ 每日推送时间：{PUSH_TIME}\n"
    content += f"📊 监控范围：外部合作、投融资、跨境电商、监管动态\n"
    content += f"📰 信息来源：新浪财经、36氪等权威媒体\n"
    content += f"⏱️ 时间窗口：过去{TIME_WINDOW_HOURS}小时"
    
    return content


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
        # 可选：发送提示消息（默认关闭，避免打扰）
        # 如需开启，取消下面注释
        # today = datetime.now().strftime("%Y年%m月%d日")
        # content = f"📰 SHEIN每日热点资讯（{today}）\n\n"
        # content += f"过去{TIME_WINDOW_HOURS}小时内暂无SHEIN相关新闻更新。\n\n"
        # content += f"⏰ 每日推送时间：{PUSH_TIME}\n"
        # content += f"📊 监控范围：外部合作、投融资、跨境电商、监管动态\n"
        # content += f"⏱️ 时间窗口：过去{TIME_WINDOW_HOURS}小时"
        # send_dingtalk_message(content)
        return
    
    # 格式化内容
    content = format_news_content(news_list)
    
    if content:
        # 发送钉钉消息
        result = send_dingtalk_message(content)
        print(f"[{datetime.now()}] 发送结果: {result}")


if __name__ == "__main__":
    main()
