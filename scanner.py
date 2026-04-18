"""
Minervini Screener - 核心扫描引擎
=====================================
每日抓取股票数据,应用Minervini 8条趋势模板 + RS评分 + VCP检测
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

# 引入VCP检测模块
from vcp import detect_vcp


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
            market_cap = 0
            sector = 'N/A'
            industry = 'N/A'
            company_name = ticker
        
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
        
        # === 综合评分 (0-160) ===
        # 基础分 (0-110):
        #   - 每条模板条件满足 ×10 = 最高80分
        #   - RS评分 ×0.3 = 最高30分
        # 形态加分 (0-40):
        #   - 真VCP识别 (vcp_score/100 × 25) = 最高25分 ★主要setup加分★
        #   - ATR收缩 +3分
        #   - 成交量萎缩 +3分
        #   - 距52周高点 ≤15% +5分 (准备突破)
        #   - 距VCP pivot ≤5% +4分 (即将触发)
        # 完美奖励 (0-10):
        #   - 8条全通过 +5
        #   - 真VCP + 8条全通过 + 接近pivot +5 (完美setup)
        score = r['criteria_passed'] * 10
        score += r['rs_rating'] * 0.3
        
        vcp = r.get('vcp', {})
        vcp_score = vcp.get('score', 0)
        has_vcp = vcp.get('has_vcp', False)
        near_pivot = vcp.get('near_pivot', False)
        
        # 真VCP评分作为最主要的setup加分
        score += (vcp_score / 100) * 25
        
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
            score += 5  # 完美setup
        
        r['minervini_score'] = round(score, 1)


def save_report(results, spy_return_1y, output_dir='reports'):
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
        'stocks': results
    }
    
    # 最新数据
    latest_path = f'{output_dir}/latest.json'
    with open(latest_path, 'w') as f:
        json.dump(output, f, separators=(',', ':'))
    
    # 归档每日快照
    daily_path = f'{output_dir}/data_{today}.json'
    with open(daily_path, 'w') as f:
        json.dump(output, f, separators=(',', ':'))
    
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
    
    # 保存报告
    output = save_report(results, spy_return_1y)
    
    # 打印Top 15
    print("\n" + "="*95)
    print(f"TOP 15 (Date: {output['date']}, Total: {output['total_stocks']}, "
          f"8/8 Pass: {output['all_8_passed_count']}, True VCP: {output['true_vcp_count']})")
    print("="*95)
    print(f"{'#':<4}{'Ticker':<8}{'Company':<28}{'Score':>7}{'Pass':>6}{'RS':>5}"
          f"{'1Y%':>8}{'VCP':>5}{'Pivot':>10}{'Setup':>12}")
    print("-"*95)
    for i, r in enumerate(sorted(results, key=lambda x: x['minervini_score'], reverse=True)[:15]):
        setup = []
        vcp = r.get('vcp', {})
        if vcp.get('has_vcp'): setup.append('✓VCP')
        elif r['volatility_contraction']: setup.append('atr')
        if r['volume_drying']: setup.append('vol')
        if vcp.get('near_pivot'): setup.append('near')
        setup_str = ','.join(setup) if setup else '-'
        name = r['name'][:26]
        vcp_score_str = f"{int(vcp.get('score', 0))}"
        pivot_str = f"${vcp.get('pivot_price', 0):.0f}" if vcp.get('pivot_price') else '-'
        print(f"{i+1:<4}{r['ticker']:<8}{name:<28}{r['minervini_score']:>7.1f}"
              f"{r['criteria_passed']:>6}{int(r['rs_rating']):>5}"
              f"{r['return_1y']:>7.1f}%{vcp_score_str:>5}{pivot_str:>10}{setup_str:>12}")
    
    print(f"\n✓ Report saved to reports/latest.json and reports/data_{output['date']}.json")
    return output


if __name__ == '__main__':
    main()        criteria['c3_ma200_uptrend'] = bool(ma200_20d_ago is not None and ma200 > ma200_20d_ago)
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
            market_cap = 0
            sector = 'N/A'
            industry = 'N/A'
            company_name = ticker
        
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
            'criteria': criteria,
            'price_history': [
                {'d': d.strftime('%m-%d'), 'c': round(float(c), 2)}
                for d, c in zip(hist.index[-90:], close.iloc[-90:].values)
            ]
        }
    except Exception as e:
        print(f"  ❌ {ticker}: {str(e)[:80]}", file=sys.stderr)
        return None


def fetch_all(tickers, max_workers=10):
    """并发抓取全部股票数据"""
    results = []
    total = len(tickers)
    
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
                    print(f"[{i+1}/{total}] {ticker} ✗ (no data)")
            except Exception as e:
                print(f"[{i+1}/{total}] {ticker} ERROR: {e}", file=sys.stderr)
    
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
        
        # === 综合评分 (0-160) ===
        # 基础分 (0-110):
        #   - 每条模板条件满足 ×10 = 最高80分
        #   - RS评分 ×0.3 = 最高30分
        # 形态加分 (0-40):
        #   - 真VCP识别 (vcp_score/100 × 25) = 最高25分 ★主要setup加分★
        #   - ATR收缩 +3分
        #   - 成交量萎缩 +3分
        #   - 距52周高点 ≤15% +5分 (准备突破)
        #   - 距VCP pivot ≤5% +4分 (即将触发)
        # 完美奖励 (0-10):
        #   - 8条全通过 +5
        #   - 真VCP + 8条全通过 + 接近pivot +5 (完美setup)
        score = r['criteria_passed'] * 10
        score += r['rs_rating'] * 0.3
        
        vcp = r.get('vcp', {})
        vcp_score = vcp.get('score', 0)
        has_vcp = vcp.get('has_vcp', False)
        near_pivot = vcp.get('near_pivot', False)
        
        # 真VCP评分作为最主要的setup加分
        score += (vcp_score / 100) * 25
        
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
            score += 5  # 完美setup
        
        r['minervini_score'] = round(score, 1)


def save_report(results, spy_return_1y, output_dir='reports'):
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
        'stocks': results
    }
    
    # 最新数据
    latest_path = f'{output_dir}/latest.json'
    with open(latest_path, 'w') as f:
        json.dump(output, f, separators=(',', ':'))
    
    # 归档每日快照
    daily_path = f'{output_dir}/data_{today}.json'
    with open(daily_path, 'w') as f:
        json.dump(output, f, separators=(',', ':'))
    
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
    
    # 保存报告
    output = save_report(results, spy_return_1y)
    
    # 打印Top 15
    print("\n" + "="*95)
    print(f"TOP 15 (Date: {output['date']}, Total: {output['total_stocks']}, "
          f"8/8 Pass: {output['all_8_passed_count']}, True VCP: {output['true_vcp_count']})")
    print("="*95)
    print(f"{'#':<4}{'Ticker':<8}{'Company':<28}{'Score':>7}{'Pass':>6}{'RS':>5}"
          f"{'1Y%':>8}{'VCP':>5}{'Pivot':>10}{'Setup':>12}")
    print("-"*95)
    for i, r in enumerate(sorted(results, key=lambda x: x['minervini_score'], reverse=True)[:15]):
        setup = []
        vcp = r.get('vcp', {})
        if vcp.get('has_vcp'): setup.append('✓VCP')
        elif r['volatility_contraction']: setup.append('atr')
        if r['volume_drying']: setup.append('vol')
        if vcp.get('near_pivot'): setup.append('near')
        setup_str = ','.join(setup) if setup else '-'
        name = r['name'][:26]
        vcp_score_str = f"{int(vcp.get('score', 0))}"
        pivot_str = f"${vcp.get('pivot_price', 0):.0f}" if vcp.get('pivot_price') else '-'
        print(f"{i+1:<4}{r['ticker']:<8}{name:<28}{r['minervini_score']:>7.1f}"
              f"{r['criteria_passed']:>6}{int(r['rs_rating']):>5}"
              f"{r['return_1y']:>7.1f}%{vcp_score_str:>5}{pivot_str:>10}{setup_str:>12}")
    
    print(f"\n✓ Report saved to reports/latest.json and reports/data_{output['date']}.json")
    return output


if __name__ == '__main__':
    main()
