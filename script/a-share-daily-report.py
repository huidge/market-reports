#!/usr/bin/env python3
"""
A股每日收盘行情汇总报告生成器
数据源优先级: 东方财富 API > AKShare (Sina + 同花顺) 兜底
替代原东方财富 push2 接口（已不可用），使用 push2his + 东方财富实时接口

输出格式与原 eastmoney-scraper cron job 生成的报告完全一致。
用法:
  python3 a-share-daily-report.py                    # 输出到 stdout
  python3 a-share-daily-report.py /path/to/output.md # 保存到文件
"""
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import sys
import os
import json
import subprocess

pd.set_option('display.max_columns', 20)
pd.set_option('display.width', 140)

# ── 工具函数 ──────────────────────────────────────────────

def fmt_amount(val):
    """格式化金额为 X万亿 / X亿"""
    if abs(val) >= 1e4:
        return f"{val/1e4:.2f}万亿"
    return f"{val:.0f}亿"

def fmt_pct(val):
    """格式化涨跌幅，加粗标记"""
    s = f"{val:+.2f}%"
    if abs(val) >= 1:
        return f"**{s}**"
    return s

def get_weekday_cn(dt):
    weekdays = ['周一','周二','周三','周四','周五','周六','周日']
    return weekdays[dt.weekday()]

# ── 数据采集 ──────────────────────────────────────────────

def fetch_index_data():
    """获取主要指数行情
    
    优先级:
    1. 东方财富实时接口 stock_zh_index_spot_em() — 主要指数 (除深证成指/创业板指外均可用)
    2. Sina 日线 stock_zh_index_daily() — 兜底深证成指/创业板指/北证50
    3. 东方财富 push2his API — 额外兜底 (间歇性可用)
    """
    index_codes = {
        '000001': '上证指数',
        '399001': '深证成指',
        '399006': '创业板指',
        '000688': '科创50',
        '000016': '上证50',
        '000300': '沪深300',
        '000905': '中证500',
        '000852': '中证1000',
    }
    results = {}
    fetched_codes = set()
    
    # ── 数据源1: 东方财富实时接口 (AKShare) ──
    try:
        df = ak.stock_zh_index_spot_em()
        for code, name in index_codes.items():
            try:
                row = df[df['代码'] == code]
                if row.empty:
                    continue
                r = row.iloc[0]
                close = float(r['最新价'])
                prev_close = float(r['昨收'])
                change_pct = float(r['涨跌幅'])
                change = float(r['涨跌额'])
                vol = float(r['成交量'])
                amount = float(r['成交额'])
                results[name] = {
                    'close': close, 'change_pct': change_pct, 'change': change,
                    'high': float(r['最高']), 'low': float(r['最低']),
                    'open': float(r['今开']), 'prev_close': prev_close,
                    'vol': vol, 'amount': amount,
                    'source': 'eastmoney_realtime',
                }
                fetched_codes.add(code)
            except Exception:
                pass
    except Exception:
        pass
    
    # ── 数据源2: Sina 日线 (兜底缺失的指数) ──
    sina_symbols = {
        '399001': 'sz399001', '399006': 'sz399006', '000001': 'sh000001',
        '000688': 'sh000688', '000016': 'sh000016', '000300': 'sh000300',
        '000905': 'sh000905', '000852': 'sh000852',
    }
    for code, name in index_codes.items():
        if code in fetched_codes:
            continue
        sym = sina_symbols.get(code)
        if not sym:
            continue
        try:
            df = ak.stock_zh_index_daily(symbol=sym)
            if df.empty or len(df) < 2:
                continue
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            close = float(latest['close'])
            prev_close = float(prev['close'])
            change_pct = (close - prev_close) / prev_close * 100
            results[name] = {
                'close': close, 'change_pct': change_pct, 'change': close - prev_close,
                'high': float(latest['high']), 'low': float(latest['low']),
                'open': float(latest['open']), 'prev_close': prev_close,
                'vol': float(latest['volume']),
                'amount': float(latest.get('amount', latest['volume'] * close)),
                'source': 'sina_daily',
            }
            fetched_codes.add(code)
        except Exception:
            pass

    # ── 北证50 (Sina 兜底) ──
    if '北证50' not in results:
        try:
            df = ak.stock_zh_index_daily(symbol='bj899050')
            if not df.empty and len(df) >= 2:
                latest = df.iloc[-1]
                prev = df.iloc[-2]
                close = float(latest['close'])
                prev_close = float(prev['close'])
                change_pct = (close - prev_close) / prev_close * 100
                results['北证50'] = {
                    'close': close, 'change_pct': change_pct,
                    'change': close - prev_close,
                    'high': float(latest['high']), 'low': float(latest['low']),
                    'open': float(latest['open']), 'prev_close': prev_close,
                    'vol': float(latest['volume']),
                    'amount': float(latest.get('amount', latest['volume'] * close)),
                    'source': 'sina_daily',
                }
        except Exception:
            results['北证50'] = {'error': '北证50数据获取失败'}
    
    # 标记获取失败的指数
    for name in index_codes.values():
        if name not in results:
            results[name] = {'error': '所有数据源均失败'}
    
    return results


def fetch_sector_data():
    """获取行业板块数据
    
    优先级:
    1. 东方财富板块资金流向 stock_sector_fund_flow_rank() — 包含涨跌幅+资金数据
    2. 同花顺板块 stock_board_industry_summary_ths() — 兜底
    """
    # ── 数据源1: 东方财富板块资金流向 ──
    try:
        df_flow = ak.stock_sector_fund_flow_rank(indicator='今日', sector_type='行业资金流')
        if df_flow is not None and not df_flow.empty:
            # 标准化列名以匹配下游处理
            df = pd.DataFrame()
            df['板块'] = df_flow['名称']
            df['涨跌幅'] = df_flow['今日涨跌幅']
            df['净流入'] = df_flow['今日主力净流入-净额'] / 1e8  # 转为亿
            df['上涨家数'] = 0  # 东财资金流向不含涨跌家数
            df['下跌家数'] = 0
            df['领涨股'] = df_flow.get('今日主力净流入最大股', '--')
            df['领涨股-涨跌幅'] = 0.0
            df['_source'] = 'eastmoney_fund_flow'
            return df
    except Exception:
        pass
    
    # ── 数据源2: 同花顺板块 ──
    try:
        df = ak.stock_board_industry_summary_ths()
        df['_source'] = 'ths'
        return df
    except Exception:
        return None


def fetch_stock_data():
    """获取全市场个股行情 (Sina)"""
    df = ak.stock_zh_a_spot()
    return df


def fetch_concept_data():
    """获取概念板块 (同花顺)"""
    df = ak.stock_board_concept_summary_ths()
    return df

# ── 报告生成 ──────────────────────────────────────────────

def generate_report():
    now = datetime.now()
    date_str = now.strftime('%Y年%m月%d日')
    weekday = get_weekday_cn(now)
    date_file = now.strftime('%Y-%m-%d')

    # 保存路径：daily/YYYY-MM-DD.md
    save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'market-reports', 'daily')
    if len(sys.argv) > 1:
        save_path = sys.argv[1]
    else:
        save_path = os.path.join(save_dir, f'{date_file}.md')

    lines = []

    # ── 标题 ──
    lines.append(f'# A股每日交易汇总报告 — {date_str}（{weekday}）')
    lines.append('')

    # ── 1. 主要指数 ──
    lines.append('## 📊 主要指数收盘')
    lines.append('')
    lines.append('| 指数 | 收盘 | 涨跌幅 |')
    lines.append('|------|------|--------|')

    idx_data = fetch_index_data()
    total_amount = 0

    index_order = ['上证指数','深证成指','创业板指','科创50','沪深300','上证50','北证50','中证500','中证1000']
    for name in index_order:
        d = idx_data.get(name, {})
        if 'error' in d:
            lines.append(f'| {name} | -- | 获取失败 |')
            continue
        close = d['close']
        pct = d['change_pct']
        total_amount += d.get('amount', 0)
        pct_str = fmt_pct(pct)
        lines.append(f'| {name} | {close:.2f} | {pct_str} |')

    lines.append('')

    # ── 成交额 ──
    lines.append('**数据获取中...**')
    lines.append('')

    # ── 2. 行业板块 ──
    lines.append('## 📈 行业板块涨跌排行')
    lines.append('')
    
    df_sec = None
    has_fund_flow_in_sector = False
    
    try:
        df_sec = fetch_sector_data()
        source = str(df_sec['_source'].iloc[0]) if df_sec is not None and '_source' in df_sec.columns else 'unknown'
        
        # 检查是否有涨跌家数（同花顺有，东财资金流向没有）
        has_updown_count = (source == 'ths')
        has_fund_flow_in_sector = (source == 'eastmoney_fund_flow')

        if has_updown_count:
            # 同花顺数据源：包含涨跌家数和领涨股
            lines.append('**涨幅 TOP10**')
            lines.append('')
            lines.append('| 板块 | 涨跌幅 | 涨/跌家数 | 领涨股 |')
            lines.append('|------|--------|-----------|--------|')
            top10 = df_sec.nlargest(10, '涨跌幅')
            for _, row in top10.iterrows():
                pct = row['涨跌幅']
                up_n = int(row['上涨家数'])
                dn_n = int(row['下跌家数'])
                leader = row['领涨股']
                leader_pct = row.get('领涨股-涨跌幅', 0)
                lines.append(f'| {row["板块"]} | {pct:+.2f}% | {up_n}/{dn_n} | {leader}(+{leader_pct:.1f}%) |')
        else:
            # 东财资金流向数据源：无涨跌家数但有主力净流入
            lines.append('**涨幅 TOP10**')
            lines.append('')
            lines.append('| 板块 | 涨跌幅 | 主力净流入 | 领涨股 |')
            lines.append('|------|--------|-----------|--------|')
            top10 = df_sec.nlargest(10, '涨跌幅')
            for _, row in top10.iterrows():
                pct = row['涨跌幅']
                flow = row['净流入']
                leader = row.get('领涨股', '--')
                flow_str = f"{flow:+.2f}亿"
                lines.append(f'| {row["板块"]} | {pct:+.2f}% | {flow_str} | {leader} |')
        lines.append('')

        # 跌幅榜
        if has_updown_count:
            lines.append('**跌幅 TOP5**')
            lines.append('')
            lines.append('| 板块 | 涨跌幅 | 涨/跌家数 |')
            lines.append('|------|--------|-----------|')
            bot5 = df_sec.nsmallest(5, '涨跌幅')
            for _, row in bot5.iterrows():
                pct = row['涨跌幅']
                up_n = int(row['上涨家数'])
                dn_n = int(row['下跌家数'])
                lines.append(f'| {row["板块"]} | {pct:+.2f}% | {up_n}/{dn_n} |')
        else:
            lines.append('**跌幅 TOP5**')
            lines.append('')
            lines.append('| 板块 | 涨跌幅 | 主力净流入 |')
            lines.append('|------|--------|-----------|')
            bot5 = df_sec.nsmallest(5, '涨跌幅')
            for _, row in bot5.iterrows():
                pct = row['涨跌幅']
                flow = row['净流入']
                lines.append(f'| {row["板块"]} | {pct:+.2f}% | {flow:+.2f}亿 |')
        lines.append('')
    except Exception as e:
        lines.append(f'> 行业板块数据获取失败: {e}')
        lines.append('')

    # ── 3. 资金流向 ──
    lines.append('## 💰 行业板块资金净流入')
    lines.append('')
    try:
        if has_fund_flow_in_sector:
            # 东财数据源：资金流向已含在板块数据中
            lines.append('**净流入 TOP10**')
            lines.append('')
            lines.append('| 板块 | 净流入 | 涨跌幅 |')
            lines.append('|------|--------|--------|')
            top_flow = df_sec.nlargest(10, '净流入')
            for _, row in top_flow.iterrows():
                flow = row['净流入']
                pct = row['涨跌幅']
                lines.append(f'| {row["板块"]} | {flow:+.2f}亿 | {pct:+.2f}% |')
            lines.append('')

            lines.append('**净流出 TOP5**')
            lines.append('')
            lines.append('| 板块 | 净流入 | 涨跌幅 |')
            lines.append('|------|--------|--------|')
            bot_flow = df_sec.nsmallest(5, '净流入')
            for _, row in bot_flow.iterrows():
                flow = row['净流入']
                pct = row['涨跌幅']
                lines.append(f'| {row["板块"]} | {flow:+.2f}亿 | {pct:+.2f}% |')
        else:
            # 同花顺数据源：资金流向在同花顺板块数据中
            lines.append('**净流入 TOP10**')
            lines.append('')
            lines.append('| 板块 | 净流入 | 涨跌幅 |')
            lines.append('|------|--------|--------|')
            top_flow = df_sec.nlargest(10, '净流入')
            for _, row in top_flow.iterrows():
                flow = row['净流入']
                pct = row['涨跌幅']
                lines.append(f'| {row["板块"]} | {flow:+.2f}亿 | {pct:+.2f}% |')
            lines.append('')

            lines.append('**净流出 TOP5**')
            lines.append('')
            lines.append('| 板块 | 净流入 | 涨跌幅 |')
            lines.append('|------|--------|--------|')
            bot_flow = df_sec.nsmallest(5, '净流入')
            for _, row in bot_flow.iterrows():
                flow = row['净流入']
                pct = row['涨跌幅']
                lines.append(f'| {row["板块"]} | {flow:+.2f}亿 | {pct:+.2f}% |')
        lines.append('')
    except Exception as e:
        lines.append(f'> 资金流向数据获取失败: {e}')
        lines.append('')

    # ── 4. 概念板块 ──
    lines.append('## 🔥 近期热门概念板块')
    lines.append('')
    try:
        df_concept = fetch_concept_data()
        lines.append('| 概念 | 成分股 | 驱动事件 |')
        lines.append('|------|--------|---------|')
        for _, row in df_concept.head(8).iterrows():
            name = row['概念名称']
            count = row['成分股数量']
            event = str(row.get('驱动事件', '--'))[:40]
            lines.append(f'| {name} | {count}只 | {event} |')
        lines.append('')
    except Exception as e:
        lines.append(f'> 概念板块获取失败: {e}')
        lines.append('')

    # ── 5. 个股统计 ──
    lines.append('## 📊 个股涨跌统计')
    lines.append('')
    try:
        df_all = fetch_stock_data()
        total = len(df_all)
        up = len(df_all[df_all['涨跌幅'] > 0])
        down = len(df_all[df_all['涨跌幅'] < 0])
        flat = len(df_all[df_all['涨跌幅'] == 0])
        limit_up = len(df_all[df_all['涨跌幅'] >= 9.9])
        limit_down = len(df_all[df_all['涨跌幅'] <= -9.9])
        total_amount_all = df_all['成交额'].sum() / 1e8

        lines.append(f'全市场 **{total}只**：上涨 {up} | 下跌 {down} | 平盘 {flat} | 涨停 {limit_up} | 跌停 {limit_down}')
        lines.append(f'> 上涨占比 **{up/total*100:.1f}%**，成交额约 **{total_amount_all/10000:.2f}万亿**')
        lines.append('')

        # 涨幅榜
        lines.append('🏆 **涨幅 TOP5**')
        top5 = df_all.nlargest(5, '涨跌幅')
        for _, row in top5.iterrows():
            lines.append(f'- {row["名称"]} ({row["代码"]}) {row["涨跌幅"]:+.2f}%  成交额{row["成交额"]/1e8:.1f}亿')
        lines.append('')

        # 跌幅榜
        lines.append('💀 **跌幅 TOP5**')
        bot5_s = df_all.nsmallest(5, '涨跌幅')
        for _, row in bot5_s.iterrows():
            lines.append(f'- {row["名称"]} ({row["代码"]}) {row["涨跌幅"]:+.2f}%  成交额{row["成交额"]/1e8:.1f}亿')
        lines.append('')
    except Exception as e:
        lines.append(f'> 个股统计获取失败: {e}')
        lines.append('')

    # ── 6. 市场总结（由 AI 补充） ──
    lines.append('## 💡 市场总结')
    lines.append('')
    lines.append('> （此部分由 AI 根据以上数据自动补充）')
    lines.append('')

    # ── 尾部 ──
    lines.append('---')
    lines.append('')
    
    # 数据来源说明
    sources = set()
    for d in idx_data.values():
        src = d.get('source', '')
        if src:
            sources.add(src)
    src_str = '东方财富实时' if 'eastmoney_realtime' in sources else 'Sina'
    if 'sina_daily' in sources:
        src_str += ' + Sina日线'
    if df_sec is not None and '_source' in df_sec.columns:
        sec_src = df_sec['_source'].iloc[0] if len(df_sec) > 0 else ''
        if sec_src == 'eastmoney_fund_flow':
            src_str += ' + 东方财富资金流向'
        else:
            src_str += ' + 同花顺板块'
    
    lines.append(f'*数据来源：{src_str} | 数据时间：{date_file}*')

    return '\n'.join(lines), idx_data


# ── 主入口 ──────────────────────────────────────────────

if __name__ == '__main__':
    report, _ = generate_report()
    print(report)

    # 自动保存到 market-reports/daily/ 目录
    now = datetime.now()
    date_file = now.strftime('%Y-%m-%d')
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_dir = os.path.join(script_dir, '..', '..', 'market-reports', 'daily')

    if len(sys.argv) > 1:
        output_path = sys.argv[1]
    else:
        output_path = os.path.normpath(os.path.join(default_dir, f'{date_file}.md'))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f'\n报告已保存到: {output_path}', file=sys.stderr)
