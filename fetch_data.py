#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
定投雷达 - 生产数据获取脚本
从东方财富公开API + AKShare 获取板块行情、估值、宏观数据
生成前端H5所需的JSON数据文件
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta

import requests

# ============================================================
# 配置
# ============================================================

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.eastmoney.com/",
}

# 申万一级行业代码映射 (用于显示友好的分类)
SW_L1_NAMES = {
    "801010": "农林牧渔", "801030": "基础化工", "801040": "钢铁",
    "801050": "有色金属", "801080": "电子", "801110": "家用电器",
    "801120": "食品饮料", "801150": "医药生物", "801160": "公用事业",
    "801170": "交通运输", "801180": "房地产", "801200": "商贸零售",
    "801230": "综合", "801710": "建筑材料", "801720": "建筑装饰",
    "801730": "电力设备", "801740": "国防军工", "801750": "计算机",
    "801760": "传媒", "801770": "通信", "801780": "银行",
    "801790": "非银金融", "801880": "汽车", "801890": "机械设备",
    "801950": "煤炭", "801960": "石油石化", "801970": "环保",
    "801980": "美容护理", "801210": "社会服务", "801760": "纺织服饰",
    "801220": "轻工制造",
}

# 定投关注板块 (在热力图中高亮显示)
WATCH_LIST = [
    {"name": "沪深300", "code": "000300", "type": "index"},
    {"name": "中证500", "code": "000905", "type": "index"},
    {"name": "电子", "code": "801080", "type": "sw_l1"},
    {"name": "医药生物", "code": "801150", "type": "sw_l1"},
    {"name": "电力设备", "code": "801730", "type": "sw_l1"},
    {"name": "食品饮料", "code": "801120", "type": "sw_l1"},
    {"name": "银行", "code": "801780", "type": "sw_l1"},
    {"name": "通信", "code": "801770", "type": "sw_l1"},
    {"name": "计算机", "code": "801750", "type": "sw_l1"},
    {"name": "有色金属", "code": "801050", "type": "sw_l1"},
]


# ============================================================
# 工具函数
# ============================================================

def safe_float(v, default=0.0):
    """安全转浮点数"""
    if v is None or v == "" or v == "-":
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def http_get(url, params=None, timeout=15):
    """HTTP GET 请求"""
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        if "json" in ct or resp.text.strip().startswith(("{", "[")):
            return resp.json()
        return resp.text
    except Exception as e:
        print(f"  [ERR] {url}: {e}")
        return None


def save_json(data, filename):
    """保存JSON到data目录"""
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  -> 已保存: {path}")
    return path


# ============================================================
# 数据获取函数
# ============================================================

def fetch_sector_realtime():
    """
    获取申万行业板块实时行情 (东方财富)
    返回: 板块列表 [{name, code, change_pct, turnover, pe, pb, market_cap}]
    """
    print(">>> 获取行业板块实时行情...")
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "fid": "f3", "po": "1", "pz": "100", "pn": "1", "np": "1",
        "fltt": "2", "invt": "2",
        "fs": "m:90+t:2+f:!50",
        "fields": "f2,f3,f4,f5,f6,f7,f8,f9,f12,f14,f20,f23,f104,f109,f115,f24,f25",
    }
    data = http_get(url, params)
    if not data or "data" not in data or not data["data"]:
        return []

    sectors = []
    for item in data["data"].get("diff", []):
        sectors.append({
            "name": item.get("f14", ""),
            "code": item.get("f12", ""),
            "price": safe_float(item.get("f2")),
            "change_pct": safe_float(item.get("f3")),
            "change_amount": safe_float(item.get("f4")),
            "volume": safe_float(item.get("f5")),
            "turnover": safe_float(item.get("f6")),
            "amplitude": safe_float(item.get("f7")),
            "turnover_rate": safe_float(item.get("f8")),
            "pe": safe_float(item.get("f9")) if item.get("f9") not in (None, "-") else None,
            "pb": safe_float(item.get("f23")) if item.get("f23") not in (None, "-") else None,
            "change_month": safe_float(item.get("f104")),
            "change_3month": safe_float(item.get("f109")),
            "change_5day": safe_float(item.get("f115")),
            "change_ytd": safe_float(item.get("f24")),
            "change_1year": safe_float(item.get("f25")),
        })

    print(f"    获取到 {len(sectors)} 个板块")
    return sectors


def fetch_sw_l1_valuation():
    """
    获取申万一级行业估值数据 (AKShare)
    返回: [{name, code, pe_static, pe_ttm, pb, dividend_yield, constituent_count}]
    """
    print(">>> 获取申万一级行业估值...")
    try:
        import akshare as ak
        df = ak.sw_index_first_info()
        result = []
        for _, row in df.iterrows():
            result.append({
                "name": row.get("行业名称", ""),
                "code": row.get("行业代码", "").replace(".SI", ""),
                "constituent_count": int(row.get("成份个数", 0)),
                "pe_static": safe_float(row.get("静态市盈率")),
                "pe_ttm": safe_float(row.get("TTM(滚动)市盈率")),
                "pb": safe_float(row.get("市净率")),
                "dividend_yield": safe_float(row.get("静态股息率")),
            })
        print(f"    获取到 {len(result)} 个申万一级行业")
        return result
    except Exception as e:
        print(f"    失败: {e}")
        return []


def fetch_index_valuation():
    """
    获取主要宽基指数PE/PB历史数据 (AKShare)
    返回: {index_name: {latest_pe, latest_pb, pe_percentile, pb_percentile, ...}}
    """
    print(">>> 获取主要指数估值...")
    try:
        import akshare as ak
    except ImportError:
        print("    AKShare未安装")
        return {}

    indices = ["沪深300", "中证500"]
    result = {}

    for idx_name in indices:
        try:
            pe_df = ak.stock_index_pe_lg(symbol=idx_name)
            pb_df = ak.stock_index_pb_lg(symbol=idx_name)

            if pe_df is not None and len(pe_df) > 0:
                latest_pe_row = pe_df.iloc[-1]
                pe_values = pe_df["静态市盈率"].dropna().tolist()
                current_pe = float(latest_pe_row["静态市盈率"])
                pe_percentile = sum(1 for v in pe_values if v <= current_pe) / len(pe_values) * 100

                latest_pb_row = pb_df.iloc[-1]
                pb_values = pb_df["市净率"].dropna().tolist()
                current_pb = float(latest_pb_row["市净率"])
                pb_percentile = sum(1 for v in pb_values if v <= current_pb) / len(pb_values) * 100

                result[idx_name] = {
                    "pe": round(current_pe, 2),
                    "pe_percentile": round(pe_percentile, 2),
                    "pb": round(current_pb, 2),
                    "pb_percentile": round(pb_percentile, 2),
                    "pe_median": float(latest_pe_row.get("静态市盈率中位数", 0)),
                    "date": str(latest_pe_row.get("日期", "")),
                }
                print(f"    {idx_name}: PE={current_pe:.2f}({pe_percentile:.1f}%) PB={current_pb:.2f}({pb_percentile:.1f}%)")
        except Exception as e:
            print(f"    {idx_name} 失败: {e}")

    return result


def fetch_northbound_flow(days=20):
    """
    获取北向资金近期流向 (东方财富)
    返回: [{date, net_buy_amount (亿)}]
    """
    print(">>> 获取北向资金流向...")
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "sortColumns": "TRADE_DATE",
        "sortTypes": "-1",
        "pageSize": str(days),
        "pageNumber": "1",
        "reportName": "RPT_MUTUAL_DEAL_HISTORY",
        "columns": "ALL",
        "source": "WEB",
        "client": "WEB",
    }
    data = http_get(url, params)
    if data and "result" in data and data["result"]:
        items = data["result"].get("data", [])
        result = []
        for item in items:
            date_str = str(item.get("TRADE_DATE", ""))[:10]
            net = safe_float(item.get("NET_DEAL_AMT"))
            result.append({
                "date": date_str,
                "net_buy_amount_yi": round(net / 1e8, 2),
            })
        total_20d = sum(r["net_buy_amount_yi"] for r in result)
        print(f"    获取到 {len(result)} 天数据, 近{days}日累计净买入: {total_20d:.1f}亿")
        return {"daily": result, "total_20d_yi": round(total_20d, 2)}

    # 备用: 分钟级数据
    url2 = "https://push2.eastmoney.com/api/qt/kamt.rtmin/get"
    params2 = {
        "fields1": "f1,f2,f3,f4",
        "fields2": "f51,f52,f53,f54,f55,f56",
        "ut": "b2884a393a59ad64002292a3e90d46a5",
    }
    data2 = http_get(url2, params2)
    if data2 and "data" in data2:
        s2n = data2["data"].get("s2n", [])
        if s2n:
            print(f"    备用方案: 获取到 {len(s2n)} 条分钟级数据")
            return {"daily": [], "intraday": s2n[-5:], "total_20d_yi": None}

    print("    获取失败")
    return None


def fetch_margin_trading(days=10):
    """
    获取融资融券余额 (AKShare -> 上交所)
    返回: [{date, margin_balance, short_balance, total}]
    """
    print(">>> 获取融资融券余额...")
    try:
        import akshare as ak
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")
        df = ak.stock_margin_sse(start_date=start, end_date=end)
        result = []
        for _, row in df.tail(days).iterrows():
            result.append({
                "date": str(row["信用交易日期"]),
                "margin_balance_yi": round(safe_float(row["融资余额"]) / 1e8, 2),
                "short_balance_yi": round(safe_float(row["融券余量金额"]) / 1e8, 2),
                "total_yi": round(safe_float(row["融资融券余额"]) / 1e8, 2),
            })
        if result:
            print(f"    最新: {result[-1]['date']} 融资余额={result[-1]['margin_balance_yi']:.0f}亿")
        return result
    except Exception as e:
        print(f"    失败: {e}")
        return []


def fetch_macro_data():
    """
    获取宏观经济数据 CPI + PMI (东方财富)
    返回: {cpi: [...], pmi: [...]}
    """
    print(">>> 获取宏观经济数据...")
    base_url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    result = {}

    # CPI
    cpi_data = http_get(base_url, {
        "sortColumns": "REPORT_DATE", "sortTypes": "-1",
        "pageSize": "12", "pageNumber": "1",
        "reportName": "RPT_ECONOMY_CPI", "columns": "ALL",
        "source": "WEB", "client": "WEB",
    })
    if cpi_data and "result" in cpi_data and cpi_data["result"]:
        cpi_list = []
        for item in cpi_data["result"]["data"]:
            cpi_list.append({
                "date": str(item.get("REPORT_DATE", ""))[:10],
                "yoy": safe_float(item.get("NATIONAL_SAME")),
            })
        result["cpi"] = cpi_list
        print(f"    CPI: 最新 {cpi_list[0]['date']} = {cpi_list[0]['yoy']}%")

    # PMI
    pmi_data = http_get(base_url, {
        "sortColumns": "REPORT_DATE", "sortTypes": "-1",
        "pageSize": "12", "pageNumber": "1",
        "reportName": "RPT_ECONOMY_PMI", "columns": "ALL",
        "source": "WEB", "client": "WEB",
    })
    if pmi_data and "result" in pmi_data and pmi_data["result"]:
        pmi_list = []
        for item in pmi_data["result"]["data"]:
            pmi_list.append({
                "date": str(item.get("REPORT_DATE", ""))[:10],
                "manufacturing": safe_float(item.get("MAKE_INDEX")),
            })
        result["pmi"] = pmi_list
        print(f"    PMI: 最新 {pmi_list[0]['date']} = {pmi_list[0]['manufacturing']}")

    return result


def fetch_index_kline(index_code="1.000300", days=300):
    """
    获取指数日K线 (东方财富)
    返回: {dates: [...], closes: [...], ma250: float, above_ma250: bool}
    """
    print(f">>> 获取指数K线 ({index_code})...")
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": index_code,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101", "fqt": "1",
        "beg": (datetime.now() - timedelta(days=days + 100)).strftime("%Y%m%d"),
        "end": datetime.now().strftime("%Y%m%d"),
        "lmt": str(days),
        "ut": "fa5fd1943c7b386f172d6893dbbd1d0c",
    }
    data = http_get(url, params)
    if data and "data" in data and data["data"]:
        klines = data["data"].get("klines", [])
        dates, closes = [], []
        for k in klines:
            parts = k.split(",")
            dates.append(parts[0])
            closes.append(float(parts[2]))

        ma250 = None
        above_ma250 = None
        if len(closes) >= 250:
            ma250 = round(sum(closes[-250:]) / 250, 2)
            above_ma250 = closes[-1] > ma250

        print(f"    获取 {len(klines)} 根K线, MA250={ma250}, 当前在均线{'上方' if above_ma250 else '下方' if above_ma250 is not None else '未知'}")
        return {
            "index_code": index_code,
            "dates": dates[-30:],  # 只保留最近30天用于展示
            "closes": closes[-30:],
            "ma250": ma250,
            "latest_close": closes[-1] if closes else None,
            "above_ma250": above_ma250,
        }
    return None


# ============================================================
# 定投信号计算
# ============================================================

def calculate_signal(index_valuation, macro, kline, northbound, margin):
    """
    综合计算定投信号
    返回: {level, label, color, score, coefficient, dimensions}
    """
    print("\n>>> 计算定投信号...")

    # 1. 估值分 (沪深300 PE百分位)
    val_score = 50
    val_detail = "数据暂缺"
    if index_valuation and "沪深300" in index_valuation:
        pe_pct = index_valuation["沪深300"]["pe_percentile"]
        pe_val = index_valuation["沪深300"]["pe"]
        if pe_pct <= 20:
            val_score = 90
        elif pe_pct <= 30:
            val_score = 75
        elif pe_pct <= 40:
            val_score = 65
        elif pe_pct <= 60:
            val_score = 50
        elif pe_pct <= 70:
            val_score = 35
        elif pe_pct <= 80:
            val_score = 20
        else:
            val_score = 10
        val_detail = f"沪深300 PE={pe_val}, 处于近10年{pe_pct:.0f}%分位"
    print(f"    估值分: {val_score} ({val_detail})")

    # 2. 经济基本面分 (PMI + CPI)
    fund_score = 50
    fund_detail = "数据暂缺"
    pmi_val = None
    cpi_val = None
    if macro.get("pmi"):
        pmi_val = macro["pmi"][0].get("manufacturing")
    if macro.get("cpi"):
        cpi_val = macro["cpi"][0].get("yoy")

    if pmi_val is not None:
        if pmi_val >= 51:
            fund_score = 80
        elif pmi_val >= 50:
            fund_score = 65
        elif pmi_val >= 49:
            fund_score = 50
        else:
            fund_score = 35
        fund_detail = f"PMI={pmi_val}"
        if cpi_val is not None:
            fund_detail += f", CPI={cpi_val}%"
            if 0.5 <= cpi_val <= 2.0:
                fund_score = min(fund_score + 10, 100)
    print(f"    基本面分: {fund_score} ({fund_detail})")

    # 3. 技术趋势分
    trend_score = 50
    trend_detail = "数据暂缺"
    if kline and kline.get("ma250"):
        if kline["above_ma250"]:
            trend_score = 70
            trend_detail = f"沪深300={kline['latest_close']:.0f}, 在250日均线({kline['ma250']:.0f})上方"
        else:
            trend_score = 40
            trend_detail = f"沪深300={kline['latest_close']:.0f}, 在250日均线({kline['ma250']:.0f})下方"
    print(f"    趋势分: {trend_score} ({trend_detail})")

    # 4. 资金情绪分 (逆向指标)
    sent_score = 50
    sent_detail = "数据暂缺"
    if northbound and northbound.get("total_20d_yi") is not None:
        nb_total = northbound["total_20d_yi"]
        if nb_total > 500:
            sent_score = 30  # 过热
        elif nb_total > 200:
            sent_score = 40
        elif nb_total > -200:
            sent_score = 55
        else:
            sent_score = 70  # 恐慌时加仓
        sent_detail = f"北向资金近20日净买入{nb_total:.0f}亿"

    if margin:
        latest_margin = margin[-1].get("total_yi", 0)
        sent_detail += f", 两融余额{latest_margin:.0f}亿"
    print(f"    情绪分: {sent_score} ({sent_detail})")

    # 5. 板块均衡度分
    balance_score = 50
    balance_detail = "使用默认值"
    print(f"    均衡度分: {balance_score} ({balance_detail})")

    # 综合分
    total = (
        val_score * 0.30
        + fund_score * 0.20
        + trend_score * 0.15
        + sent_score * 0.15
        + balance_score * 0.20
    )
    total = round(total, 1)

    if total >= 70:
        level, label, color, coeff = "active", "积极加仓", "green", 1.3
    elif total >= 50:
        level, label, color, coeff = "normal", "正常定投", "blue", 1.0
    elif total >= 30:
        level, label, color, coeff = "cautious", "谨慎观望", "yellow", 0.7
    else:
        level, label, color, coeff = "stop", "风险警示", "red", 0.0

    print(f"    >>> 综合分: {total} -> {label} (系数{coeff})")

    return {
        "level": level,
        "label": label,
        "color": color,
        "score": total,
        "coefficient": coeff,
        "dimensions": {
            "valuation": {"score": val_score, "weight": 0.30, "detail": val_detail},
            "fundamentals": {"score": fund_score, "weight": 0.20, "detail": fund_detail},
            "trend": {"score": trend_score, "weight": 0.15, "detail": trend_detail},
            "sentiment": {"score": sent_score, "weight": 0.15, "detail": sent_detail},
            "balance": {"score": balance_score, "weight": 0.20, "detail": balance_detail},
        },
    }


# ============================================================
# 板块定投建议
# ============================================================

def calculate_sector_advice(sw_valuation, sectors_realtime):
    """
    基于估值+趋势, 给出每个关注板块的定投建议
    """
    advice = []
    pe_map = {}
    if sw_valuation:
        for s in sw_valuation:
            pe_map[s["name"]] = s

    for watch in WATCH_LIST:
        name = watch["name"]
        info = pe_map.get(name, {})
        pe_ttm = info.get("pe_ttm")
        pb = info.get("pb")

        # 简化估值判断 (实际应使用百分位)
        rating = "unknown"
        rec = "数据不足"
        if pe_ttm:
            if pe_ttm < 15:
                rating = "undervalued"
                rec = "建议加码"
            elif pe_ttm < 25:
                rating = "fair"
                rec = "正常定投"
            elif pe_ttm < 40:
                rating = "slightly_high"
                rec = "正常定投"
            else:
                rating = "overvalued"
                rec = "谨慎观望"

        advice.append({
            "name": name,
            "code": watch["code"],
            "type": watch["type"],
            "pe_ttm": pe_ttm,
            "pb": pb,
            "dividend_yield": info.get("dividend_yield"),
            "rating": rating,
            "recommendation": rec,
        })

    return advice


# ============================================================
# 基金推荐: 获取各板块推荐基金的历史业绩数据
# ============================================================

FUND_MAP = {
    "沪深300": [
        {"code": "110020", "name": "易方达沪深300ETF联接A", "tag": "低费率龙头"},
        {"code": "007339", "name": "广发沪深300ETF联接A", "tag": "规模大流动性好"},
    ],
    "电子": [
        {"code": "163116", "name": "申万电子行业指数A", "tag": "纯电子行业"},
    ],
    "医药生物": [
        {"code": "003095", "name": "中欧医疗健康混合A", "tag": "医药龙头主动基"},
        {"code": "001717", "name": "工银瑞信前沿医疗A", "tag": "医疗主题"},
    ],
    "电力设备": [
        {"code": "011101", "name": "天弘中证光伏产业A", "tag": "光伏主题"},
        {"code": "160225", "name": "国泰国证新能源车A", "tag": "新能源车"},
    ],
    "食品饮料": [
        {"code": "161725", "name": "招商中证白酒指数", "tag": "白酒龙头"},
        {"code": "001632", "name": "天弘中证食品饮料A", "tag": "食品饮料宽基"},
    ],
    "银行": [
        {"code": "240019", "name": "华宝中证银行ETF联接A", "tag": "银行ETF"},
    ],
    "通信": [
        {"code": "007817", "name": "国泰通信设备ETF联接A", "tag": "通信设备"},
        {"code": "008086", "name": "华夏5G通信ETF联接A", "tag": "5G主题"},
    ],
    "计算机": [
        {"code": "160626", "name": "鹏华中证信息技术A", "tag": "信息技术"},
        {"code": "000942", "name": "广发信息技术联接A", "tag": "计算机"},
    ],
    "有色金属": [
        {"code": "165520", "name": "中信保诚中证800有色A", "tag": "有色金属"},
    ],
}


def fetch_fund_recommendations():
    """
    获取各关注板块的推荐基金及其历史业绩数据 (AKShare)
    返回: {sector_name: [{code, name, tag, return_1m, return_3m, ..., nav_monthly}]}
    """
    print(">>> 获取推荐基金业绩数据...")
    try:
        import akshare as ak
    except ImportError:
        print("    AKShare未安装")
        return {}

    results = {}
    for sector, funds in FUND_MAP.items():
        results[sector] = []
        for fund in funds:
            code = fund["code"]
            try:
                df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
                if df is None or len(df) == 0:
                    continue

                # 取最近约250个交易日的数据
                df = df.tail(250)
                nav_data = []
                for _, row in df.iterrows():
                    nav_data.append({
                        "date": str(row["净值日期"]),
                        "nav": float(row["单位净值"]),
                    })

                latest = nav_data[-1]["nav"]

                # 计算各期收益
                periods = {}
                for label, offset in [("1m", 22), ("3m", 66), ("6m", 132), ("1y", 250)]:
                    if len(nav_data) >= offset:
                        base = nav_data[-offset]["nav"]
                    else:
                        base = nav_data[0]["nav"]
                    periods[label] = round((latest - base) / base * 100, 2) if base > 0 else 0

                # 月度采样
                monthly = {}
                for d in nav_data:
                    month_key = d["date"][:7]
                    monthly[month_key] = d["nav"]
                monthly_list = [{"month": k, "nav": v} for k, v in monthly.items()]

                fund_info = {
                    "code": code,
                    "name": fund["name"],
                    "tag": fund["tag"],
                    "latest_nav": round(latest, 4),
                    "latest_date": nav_data[-1]["date"],
                    "return_1m": periods["1m"],
                    "return_3m": periods["3m"],
                    "return_6m": periods["6m"],
                    "return_1y": periods["1y"],
                    "nav_monthly": monthly_list,
                }
                results[sector].append(fund_info)
                print(f"    {code} {fund['name']}: 1年{periods['1y']:+.1f}% 6月{periods['6m']:+.1f}% 3月{periods['3m']:+.1f}%")
            except Exception as e:
                print(f"    {code} {fund['name']}: 失败 - {e}")

    return results


# ============================================================
# 主流程
# ============================================================

def main():
    start_time = time.time()
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"{'='*60}")
    print(f"定投雷达 - 数据更新")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # 获取各类数据
    sectors = fetch_sector_realtime()
    sw_val = fetch_sw_l1_valuation()
    idx_val = fetch_index_valuation()
    northbound = fetch_northbound_flow()
    margin = fetch_margin_trading()
    macro = fetch_macro_data()
    kline = fetch_index_kline()

    # 计算信号
    signal = calculate_signal(idx_val, macro, kline, northbound, margin)
    sector_advice = calculate_sector_advice(sw_val, sectors)

    # 获取基金推荐数据
    fund_recs = fetch_fund_recommendations()

    # 组装完整输出
    output = {
        "meta": {
            "date": today,
            "generated_at": datetime.now().isoformat(),
            "version": "1.0.0",
        },
        "signal": signal,
        "sectors_realtime": sectors,
        "sw_valuation": sw_val,
        "index_valuation": idx_val,
        "sector_advice": sector_advice,
        "northbound_flow": northbound,
        "margin_trading": margin,
        "macro": macro,
        "kline_hs300": kline,
    }

    # 保存
    save_json(output, f"market_data_{today}.json")
    save_json(output, "market_data_latest.json")

    # 保存基金推荐数据
    if fund_recs:
        save_json(fund_recs, "fund_recommendations.json")

    elapsed = time.time() - start_time
    print(f"\n完成! 耗时 {elapsed:.1f}s, 数据已保存到 {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
