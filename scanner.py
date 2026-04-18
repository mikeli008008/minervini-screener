"""
Minervini Screener - 核心扫描引擎
=====================================
每日抓取股票数据,应用Minervini 8条趋势模板 + RS评分 + VCP检测 + 基本面分析
输出: reports/data_YYYY-MM-DD.json
"""
import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

# 引入VCP和基本面模块
from vcp import detect_vcp
from fundamentals import analyze_fundamentals


def load_tickers(path='tickers.txt'):
    """从文件读取股票池,去重"""
    with open(path) as f:
        tickers = []
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                tickers.append(line)
    return sorted(list(set(tickers)))


def calculate_stock_metrics(ticker, max_retries=3):
    """
    计算单只股票的Minervini完整指标
    带重试机制对抗Yahoo Finance rate limit
    """
    import time
    import random
    
    last_error = None
    for attempt in range(max_retries):
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period='2y', auto_adjust=True)
            
            if len(hist) < 250:
                return None
            
            # 成功拉到数据就跳出重试循环
            break
        except Exception as e:
            last_error = e
            err_msg = str(e).lower()
            if 'rate' in err_msg or 'too many' in err_msg or '429' in err_msg:
                # 指数退避 + 随机抖动
                wait = (2 ** attempt) + random.uniform(0.5, 1.5)
                time.sleep(wait)
                continue
            else:
                # 非限流错误,直接报错
                raise
    else:
        # 重试耗尽
        raise last_error if last_error else Exception("Max retries exceeded")
    
    try:
        close = hist['Close']
        volume = hist['Volume']
        high = hist['High']
        low = hist['Low']
        current_price = close.iloc[-1]
        
        # === 均线 ===
        ma50 = close.rolling(50).mean().iloc[-1]
        ma150 = close.rolling(150).mean().iloc[-1]
        ma200 = close.rolling(200).mean().iloc[-1]
        ma200_20d_ago = close.rolling(200).mean().iloc[-21] if len(close) > 220 else None
        
        # === 52周高低点 ===
        high_52w = close.iloc[-252:].max()
        low_52w = close.iloc[-252:].min()
        
        # === Minervini 8条趋势模板 ===
        criteria = {}
        criteria['c1_price_above_ma150_200'] = bool(current_price > ma150 and current_price > ma200)
        criteria['c2_ma150_above_ma200'] = bool(ma150 > ma200)
        criteria['c3_ma200_uptrend'] = bool(ma200_20d_ago is not None and ma200 > ma200_20d_ago)
        criteria['c4_ma50_above_ma150_200'] = bool(ma50 > ma150 and ma50 > ma200)
        criteria['c5_price_above_ma50'] = bool(current_price > ma50)
        criteria['c6_price_30pct_above_low'] = bool(current_price >= low_52w * 1.30)
        criteria['c7_price_within_25pct_of_high'] = bool(current_price >= high_52w * 0.75)
        # c8 (RS rating) 在后面基于全部股票排名计算
        
        # === 1年回报 ===
        price_1y_ago = close.iloc[-252]
        stock_return_1y = (current_price / price_1y_ago - 1) * 100
        
        # === ATR波动率收缩检测 (简化辅助指标) ===
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        atr_40 = tr.rolling(40).mean().iloc[-1]
        atr_10 = tr.rolling(10).mean().iloc[-1]
        volatility_contraction = bool(atr_10 < atr_40 * 0.75)
        
        # === 成交量特征 ===
        avg_vol_50 = volume.rolling(50).mean().iloc[-1]
        avg_vol_10 = volume.rolling(10).mean().iloc[-1]
        volume_drying = bool(avg_vol_10 < avg_vol_50 * 0.9)
        
        # === 真实VCP检测 (基于峰谷识别) ===
        vcp_result = detect_vcp(close, high, low, volume, lookback=90)
        
        # === 最近20天内的回调 ===
        recent_high = close.iloc[-20:].max()
        pullback_from_recent_high = (current_price / recent_high - 1) * 100
        
        # === 距离52周高低点 ===
        pct_from_high = (current_price / high_52w - 1) * 100
        pct_from_low = (current_price / low_52w - 1) * 100
        
        # === 最近日涨跌 ===
        prev_close = close.iloc[-2]
        day_change = (current_price / prev_close - 1) * 100
        
        # === 获取基本信息 ===
        try:
            info = stock.info
            market_cap = info.get('marketCap', 0)
            sector = info.get('sector', 'N/A')
            industry = info.get('industry', 'N/A')
            company_name = info.get('longName', ticker) or ticker
        except:
            info = {}
            market_cap = 0
            sector = 'N/A'
            industry = 'N/A'
            company_name = ticker
        
        # === 基本面分析 ===
        # 复用已经抓到的stock对象,避免重复网络请求
        fundamentals = None
        try:
            from fundamentals import (
                extract_eps_series, extract_revenue_series,
                calculate_eps_metrics, calculate_revenue_metrics,
                calculate_margin_metrics, extract_info_metrics,
                calculate_fundamental_score, grade_from_score,
                check_leader_profile
            )
            
            # 抓取季度财务数据
            quarterly_fin = None
            quarterly_inc = None
            try:
                quarterly_fin = stock.quarterly_financials
            except:
                pass
            try:
                quarterly_inc = stock.quarterly_income_stmt
            except:
                pass
            
            eps_series = extract_eps_series(quarterly_inc)
            rev_series = extract_revenue_series(quarterly_fin)
            eps_metrics = calculate_eps_metrics(eps_series)
            rev_metrics = calculate_revenue_metrics(rev_series)
            margin_metrics = calculate_margin_metrics(quarterly_fin)
            info_metrics = extract_info_metrics(info)
            
            fund_score, fund_details = calculate_fundamental_score(
                eps_metrics, rev_metrics, margin_metrics, info_metrics
            )
            fund_grade = grade_from_score(fund_score)
            meets_profile, leader_checks = check_leader_profile(
                eps_metrics, rev_metrics, margin_metrics, info_metrics
            )
            
            fundamentals = {
                'eps': {
                    'yoy_growth': eps_metrics.get('latest_yoy_growth'),
                    'prev_yoy_growth': eps_metrics.get('prev_yoy_growth'),
                    'accelerating': eps_metrics.get('eps_accelerating'),
                    'consistent_positive': eps_metrics.get('consistent_positive'),
                },
                'revenue': {
                    'yoy_growth': rev_metrics.get('latest_yoy_growth'),
                    'prev_yoy_growth': rev_metrics.get('prev_yoy_growth'),
                    'accelerating': rev_metrics.get('revenue_accelerating'),
                },
                'margins': {
                    'latest_net_margin': margin_metrics.get('latest_net_margin'),
                    'yoy_net_margin': margin_metrics.get('yoy_net_margin'),
                    'expanding': margin_metrics.get('margin_expanding'),
                },
                'ratios': {
                    'roe': info_metrics.get('roe'),
                    'profit_margin': info_metrics.get('profit_margin'),
                    'operating_margin': info_metrics.get('operating_margin'),
                    'held_by_institutions': info_metrics.get('held_by_institutions'),
                    'forward_pe': info_metrics.get('forward_pe'),
                },
                'score': fund_score,
                'grade': fund_grade,
                'details': fund_details,
                'meets_leader_profile': meets_profile,
                'leader_checks': leader_checks,
            }
        except Exception as fe:
            # 基本面抓取失败不影响技术面结果
            fundamentals = {
                'score': 0,
                'grade': 'N/A',
                'meets_leader_profile': False,
                'error': str(fe)[:80]
            }
        
        return {
            'ticker': ticker,
            'name': company_name,
            'sector': sector,
            'industry': industry,
            'market_cap': market_cap,
            'price': round(float(current_price), 2),
            'day_change': round(float(day_change), 2),
            'ma50': round(float(ma50), 2),
            'ma150': round(float(ma150), 2),
            'ma200': round(float(ma200), 2),
            'high_52w': round(float(high_52w), 2),
            'low_52w': round(float(low_52w), 2),
            'pct_from_high': round(float(pct_from_high), 2),
            'pct_from_low': round(float(pct_from_low), 2),
            'return_1y': round(float(stock_return_1y), 2),
            'rs_raw': round(float(stock_return_1y), 2),  # 后续调整
            'atr_10': round(float(atr_10), 3),
            'atr_40': round(float(atr_40), 3),
            'volatility_contraction': volatility_contraction,
            'volume_drying': volume_drying,
            'pullback_from_recent_high': round(float(pullback_from_recent_high), 2),
            # === 真实VCP检测结果 ===
            'vcp': {
                'has_vcp': vcp_result['has_vcp'],
                'score': vcp_result['vcp_score'],
                'num_contractions': vcp_result['num_contractions'],
                'contractions': vcp_result['contractions'],
                'tightening': vcp_result['contractions_tightening'],
                'last_contraction_pct': vcp_result['last_contraction_pct'],
                'volume_ratio': vcp_result['volume_contraction_ratio'],
                'near_pivot': vcp_result['price_near_pivot'],
                'pivot_price': vcp_result['pivot_price']
            },
            # === 基本面 ===
            'fundamentals': fundamentals,
            'criteria': criteria,
            'price_history': [
                {'d': d.strftime('%m-%d'), 'c': round(float(c), 2)}
                for d, c in zip(hist.index[-90:], close.iloc[-90:].values)
            ]
        }
    except Exception as e:
        print(f"  ❌ {ticker}: {str(e)[:80]}", file=sys.stderr)
        return None


def fetch_all(tickers, max_workers=5):
    """
    并发抓取全部股票数据
    - 降低并发数(5)减轻Yahoo限流
    - 对失败的股票做二次重试
    """
    import time
    results = []
    failed = []
    total = len(tickers)
    
    # 第一轮：正常并发抓取
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(calculate_stock_metrics, t): t for t in tickers}
        for i, future in enumerate(as_completed(futures)):
            ticker = futures[future]
            try:
                data = future.result()
                if data:
                    results.append(data)
                    print(f"[{i+1}/{total}] {ticker} ✓")
                else:
                    failed.append(ticker)
                    print(f"[{i+1}/{total}] {ticker} ✗ (no data)")
            except Exception as e:
                failed.append(ticker)
                print(f"[{i+1}/{total}] {ticker} ERROR: {str(e)[:60]}", file=sys.stderr)
    
    # 第二轮：对失败的股票单线程+长等待重试
    if failed:
        print(f"\n--- Retrying {len(failed)} failed tickers (single-thread, slow) ---")
        time.sleep(10)  # 先冷却10秒
        for i, ticker in enumerate(failed):
            try:
                # 单线程慢速重试,每个请求间隔1秒
                time.sleep(1)
                data = calculate_stock_metrics(ticker, max_retries=5)
                if data:
                    results.append(data)
                    print(f"[retry {i+1}/{len(failed)}] {ticker} ✓ recovered")
                else:
                    print(f"[retry {i+1}/{len(failed)}] {ticker} ✗ still failed")
            except Exception as e:
                print(f"[retry {i+1}/{len(failed)}] {ticker} ERROR: {str(e)[:60]}", file=sys.stderr)
    
    return results


def calculate_rs_rating(results, spy_return_1y):
    """
    计算相对强度RS Rating (0-99百分位)
    IBD式: 股票1年回报 vs 全部股票的分布
    """
    returns = np.array([r['return_1y'] for r in results])
    
    for r in results:
        # 相对SPY的超额回报
        r['rs_raw'] = round(r['return_1y'] - spy_return_1y, 2)
        
        # 百分位排名
        pct_rank = (returns < r['return_1y']).sum() / len(returns) * 100
        r['rs_rating'] = round(pct_rank, 0)
        r['criteria']['c8_rs_rating_70plus'] = bool(pct_rank >= 70)


def calculate_scores(results):
    """计算综合Minervini评分"""
    for r in results:
        # 8条通过数
        r['criteria_passed'] = sum(1 for v in r['criteria'].values() if v)
        r['all_8_passed'] = r['criteria_passed'] == 8
        
        # === 综合评分 (0-220) ===
        # 技术面 (0-160):
        #   - 8条趋势模板 ×10 = 80分
        #   - RS评分 ×0.3 = 30分
        #   - 真VCP × 25 = 25分
        #   - ATR/Volume/近高/近pivot/全通过/perfect加分 = 最高25分
        # 基本面 (0-50):
        #   - 基本面评分 ×1.0 (直接加)
        # Leader Profile 奖励 (0-10):
        #   - 基本面达标 Leader Profile +10
        #   - 与 Perfect Setup 叠加时形成 "真正的Minervini大牛股信号"
        
        # === 技术面基础分 ===
        score = r['criteria_passed'] * 10
        score += r['rs_rating'] * 0.3
        
        vcp = r.get('vcp', {})
        vcp_score_val = vcp.get('score', 0)
        has_vcp = vcp.get('has_vcp', False)
        near_pivot = vcp.get('near_pivot', False)
        
        score += (vcp_score_val / 100) * 25
        
        if r['volatility_contraction']:
            score += 3
        if r['volume_drying']:
            score += 3
        if r['pct_from_high'] > -15:
            score += 5
        if near_pivot:
            score += 4
        if r['all_8_passed']:
            score += 5
        if has_vcp and r['all_8_passed'] and near_pivot:
            score += 5  # 技术面完美setup
        
        # === 基本面得分 ===
        fund = r.get('fundamentals', {}) or {}
        fund_score = fund.get('score', 0) or 0
        meets_leader = fund.get('meets_leader_profile', False)
        
        score += fund_score  # 基本面评分直接加(0-50)
        
        if meets_leader:
            score += 10  # Leader Profile奖励
        
        # === 真·大牛股信号: Perfect Setup + Leader Profile ===
        # 这是 Minervini 最看重的信号组合
        r['super_stock_candidate'] = bool(
            has_vcp and r['all_8_passed'] and near_pivot and meets_leader
        )
        if r['super_stock_candidate']:
            score += 5  # 额外奖励
        
        r['minervini_score'] = round(score, 1)


def save_report(results, spy_return_1y, output_dir='reports', watchlist_status=None):
    """保存报告JSON"""
    Path(output_dir).mkdir(exist_ok=True)
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 按评分排序
    results.sort(key=lambda x: x['minervini_score'], reverse=True)    
    output = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'date': today,
        'spy_return_1y': round(spy_return_1y, 2),
        'total_stocks': len(results),
        'all_8_passed_count': sum(1 for r in results if r['all_8_passed']),
        'pass_7_count': sum(1 for r in results if r['criteria_passed'] >= 7),
        'vcp_count': sum(1 for r in results if r['volatility_contraction']),
        'true_vcp_count': sum(1 for r in results if r.get('vcp', {}).get('has_vcp')),
        'near_pivot_count': sum(1 for r in results if r.get('vcp', {}).get('near_pivot')),
        'perfect_setup_count': sum(1 for r in results if 
                                    r.get('vcp', {}).get('has_vcp') 
                                    and r['all_8_passed']
                                    and r.get('vcp', {}).get('near_pivot')),
        # === 基本面统计 ===
        'leader_profile_count': sum(1 for r in results 
                                    if (r.get('fundamentals') or {}).get('meets_leader_profile')),
        'grade_a_count': sum(1 for r in results 
                            if (r.get('fundamentals') or {}).get('grade') == 'A'),
        'grade_b_count': sum(1 for r in results 
                            if (r.get('fundamentals') or {}).get('grade') == 'B'),
        'super_stock_count': sum(1 for r in results if r.get('super_stock_candidate')),
        'watchlist_status': watchlist_status or [],
        'watchlist_count': len(watchlist_status) if watchlist_status else 0,
        'stocks': results
    }
    
    # 最新数据 - 使用default处理numpy类型
    def json_safe(obj):
        if hasattr(obj, 'item'):  # numpy标量
            return obj.item()
        if isinstance(obj, (pd.Timestamp,)):
            return str(obj)
        return str(obj)
    
    latest_path = f'{output_dir}/latest.json'
    with open(latest_path, 'w') as f:
        json.dump(output, f, separators=(',', ':'), default=json_safe)
    
    # 归档每日快照
    daily_path = f'{output_dir}/data_{today}.json'
    with open(daily_path, 'w') as f:
        json.dump(output, f, separators=(',', ':'), default=json_safe)
    
    return output


def main():
    print("="*60)
    print("MINERVINI SCREENER - Daily Scan")
    print("="*60)
    
    tickers = load_tickers()
    print(f"Loaded {len(tickers)} tickers\n")
    
    # 抓取SPY作为基准
    print("Fetching SPY benchmark...")
    spy = yf.Ticker('SPY').history(period='2y', auto_adjust=True)
    spy_return_1y = (spy['Close'].iloc[-1] / spy['Close'].iloc[-252] - 1) * 100
    print(f"SPY 1Y Return: {spy_return_1y:.2f}%\n")
    
    # 抓取全部股票
    print("Scanning stocks (parallel)...")
    results = fetch_all(tickers)
    print(f"\nSuccessfully fetched: {len(results)}/{len(tickers)}\n")
    
    # 计算RS和评分
    print("Computing RS ratings...")
    calculate_rs_rating(results, spy_return_1y)
    
    print("Computing Minervini scores...")
    calculate_scores(results)
    
    # === 更新 Watchlist (自动沉淀 Super Stock 和 Perfect Setup) ===
    try:
        from watchlist import update_watchlist_from_scan, get_watchlist_status
        added, updated = update_watchlist_from_scan(results)
        if added or updated:
            print(f"\n✓ Watchlist updated: +{added} new, {updated} upgraded")
        else:
            print(f"\n✓ Watchlist unchanged")
        
        # 获取完整状态但在存JSON时只保留轻量字段(scan_data太大会膨胀JSON)
        watchlist_full = get_watchlist_status(results)
        watchlist_status = []
        for w in watchlist_full:
            light = {k: v for k, v in w.items() if k != 'scan_data'}
            # 保留scan_data的关键字段
            if w.get('scan_data'):
                sd = w['scan_data']
                light['price'] = sd.get('price')
                light['name'] = sd.get('name')
                light['sector'] = sd.get('sector')
                light['pct_from_high'] = sd.get('pct_from_high')
                light['return_1y'] = sd.get('return_1y')
                light['rs_rating'] = sd.get('rs_rating')
                light['criteria_passed'] = sd.get('criteria_passed')
                light['fund_grade'] = (sd.get('fundamentals') or {}).get('grade')
                light['pivot_price'] = (sd.get('vcp') or {}).get('pivot_price')
                light['has_vcp'] = (sd.get('vcp') or {}).get('has_vcp')
                light['near_pivot'] = (sd.get('vcp') or {}).get('near_pivot')
                light['meets_leader'] = (sd.get('fundamentals') or {}).get('meets_leader_profile')
            watchlist_status.append(light)
    except Exception as we:
        print(f"\n⚠ Watchlist update failed: {we}", file=sys.stderr)
        watchlist_status = []
    
    # 保存报告 (包含watchlist状态)
    output = save_report(results, spy_return_1y, watchlist_status=watchlist_status)
    
    # 打印Top 15
    print("\n" + "="*115)
    print(f"TOP 15 (Date: {output['date']}, Total: {output['total_stocks']}, "
          f"8/8 Pass: {output['all_8_passed_count']}, True VCP: {output['true_vcp_count']}, "
          f"Leader: {output['leader_profile_count']}, ★Super: {output['super_stock_count']})")
    print("="*115)
    print(f"{'#':<4}{'Ticker':<8}{'Company':<26}{'Score':>7}{'Pass':>5}{'RS':>4}"
          f"{'1Y%':>7}{'Fund':>6}{'Gr':>4}{'EPS%':>8}{'Rev%':>7}{'Setup':>18}")
    print("-"*115)
    for i, r in enumerate(sorted(results, key=lambda x: x['minervini_score'], reverse=True)[:15]):
        setup = []
        vcp = r.get('vcp', {})
        fund = r.get('fundamentals') or {}
        if r.get('super_stock_candidate'): setup.append('★SUPER')
        elif vcp.get('has_vcp'): setup.append('✓VCP')
        if vcp.get('near_pivot'): setup.append('near')
        if fund.get('meets_leader_profile'): setup.append('LDR')
        setup_str = ','.join(setup) if setup else '-'
        name = r['name'][:24]
        fund_score = int(fund.get('score', 0) or 0)
        grade = fund.get('grade', '-')
        eps_g = fund.get('eps', {}).get('yoy_growth') if fund.get('eps') else None
        rev_g = fund.get('revenue', {}).get('yoy_growth') if fund.get('revenue') else None
        eps_str = f"{eps_g:.0f}%" if eps_g is not None else "-"
        rev_str = f"{rev_g:.0f}%" if rev_g is not None else "-"
        print(f"{i+1:<4}{r['ticker']:<8}{name:<26}{r['minervini_score']:>7.1f}"
              f"{r['criteria_passed']:>5}{int(r['rs_rating']):>4}"
              f"{r['return_1y']:>6.0f}%{fund_score:>6}{grade:>4}"
              f"{eps_str:>8}{rev_str:>7}{setup_str:>18}")
    
    print(f"\n✓ Report saved to reports/latest.json and reports/data_{output['date']}.json")
    return output


if __name__ == '__main__':
    main()
