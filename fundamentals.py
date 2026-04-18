"""
Fundamentals 模块 - 基本面数据抓取和评分
=========================================
基于 Mark Minervini 的 "Leader Profile" 标准评估基本面:
1. EPS 增长加速
2. 营收增长 (季度同比)
3. 净利润率扩张
4. ROE >= 17%
5. 机构持股增加

输出: 
- fundamental_score: 0-50分
- grade: A/B/C/D/F (综合评级)
- meets_leader_profile: bool
"""
import yfinance as yf
import pandas as pd
import numpy as np
import time
import random
import warnings
warnings.filterwarnings('ignore')


def get_fundamentals(ticker, max_retries=3):
    """
    抓取单只股票的基本面数据
    返回包含所有原始数据的 dict, 带重试机制
    """
    for attempt in range(max_retries):
        try:
            stock = yf.Ticker(ticker)
            
            # 基本信息
            info = {}
            try:
                info = stock.info or {}
            except Exception:
                pass
            
            # 季度财务数据
            quarterly_fin = None
            try:
                quarterly_fin = stock.quarterly_financials
            except Exception:
                pass
            
            # 季度盈利数据 (EPS)
            quarterly_earn = None
            try:
                quarterly_earn = stock.quarterly_income_stmt
            except Exception:
                pass
            
            # 机构持股
            inst_holders = None
            try:
                inst_holders = stock.institutional_holders
            except Exception:
                pass
            
            return {
                'info': info,
                'quarterly_financials': quarterly_fin,
                'quarterly_income': quarterly_earn,
                'institutional_holders': inst_holders
            }
        except Exception as e:
            err = str(e).lower()
            if 'rate' in err or 'too many' in err or '429' in err:
                wait = (2 ** attempt) + random.uniform(0.5, 1.5)
                time.sleep(wait)
                continue
            else:
                return None
    return None


def extract_eps_series(quarterly_income):
    """
    从季度利润表提取EPS数据
    返回最近4-8个季度的diluted EPS,按时间从新到旧
    """
    if quarterly_income is None or quarterly_income.empty:
        return []
    
    # yfinance返回的index可能有不同的key表示EPS
    eps_keys = ['Diluted EPS', 'Basic EPS', 'DilutedEPS', 'BasicEPS']
    eps_row = None
    for key in eps_keys:
        if key in quarterly_income.index:
            eps_row = quarterly_income.loc[key]
            break
    
    if eps_row is None:
        # 尝试手动计算: Net Income / Shares Outstanding
        if 'Net Income' in quarterly_income.index:
            ni_row = quarterly_income.loc['Net Income']
            return [{'date': d, 'eps': None, 'net_income': v} 
                    for d, v in ni_row.items() if pd.notna(v)]
        return []
    
    result = []
    for date, eps in eps_row.items():
        if pd.notna(eps):
            result.append({'date': date, 'eps': float(eps)})
    
    # 按日期从新到旧排序
    result.sort(key=lambda x: x['date'], reverse=True)
    return result


def extract_revenue_series(quarterly_financials):
    """从季度财务表提取营收数据"""
    if quarterly_financials is None or quarterly_financials.empty:
        return []
    
    revenue_keys = ['Total Revenue', 'Revenue', 'TotalRevenue']
    rev_row = None
    for key in revenue_keys:
        if key in quarterly_financials.index:
            rev_row = quarterly_financials.loc[key]
            break
    
    if rev_row is None:
        return []
    
    result = []
    for date, rev in rev_row.items():
        if pd.notna(rev):
            result.append({'date': date, 'revenue': float(rev)})
    
    result.sort(key=lambda x: x['date'], reverse=True)
    return result


def calculate_eps_metrics(eps_series):
    """
    计算EPS关键指标:
    - latest_yoy_growth: 最近季度EPS同比增速
    - prev_yoy_growth: 上一季度EPS同比增速
    - eps_accelerating: 是否加速
    - consistent_positive: 是否连续4季度为正
    """
    result = {
        'latest_eps': None,
        'latest_yoy_growth': None,
        'prev_yoy_growth': None,
        'eps_accelerating': False,
        'consistent_positive': False,
        'quarters_available': len(eps_series)
    }
    
    if len(eps_series) < 1:
        return result
    
    result['latest_eps'] = eps_series[0].get('eps')
    
    # 需要至少5个季度 (当前Q + 去年同季Q)来算同比
    if len(eps_series) < 5:
        return result
    
    latest = eps_series[0].get('eps')
    yoy_ago = eps_series[4].get('eps')  # 4个季度前 = 去年同期
    
    if latest is not None and yoy_ago is not None and yoy_ago != 0:
        # 避免负数除法的符号问题
        if yoy_ago > 0:
            result['latest_yoy_growth'] = (latest - yoy_ago) / yoy_ago * 100
        elif yoy_ago < 0 and latest > 0:
            # 从亏损转盈利,特殊处理为大正数
            result['latest_yoy_growth'] = 999.0  # 标记为极大值
        elif yoy_ago < 0 and latest < 0:
            # 亏损减少或增加
            result['latest_yoy_growth'] = (yoy_ago - latest) / abs(yoy_ago) * 100
    
    # 上一季度的同比 (需要6个季度)
    if len(eps_series) >= 6:
        prev = eps_series[1].get('eps')
        prev_yoy_ago = eps_series[5].get('eps')
        if prev is not None and prev_yoy_ago is not None and prev_yoy_ago != 0:
            if prev_yoy_ago > 0:
                result['prev_yoy_growth'] = (prev - prev_yoy_ago) / prev_yoy_ago * 100
            elif prev_yoy_ago < 0 and prev > 0:
                result['prev_yoy_growth'] = 999.0
            elif prev_yoy_ago < 0 and prev < 0:
                result['prev_yoy_growth'] = (prev_yoy_ago - prev) / abs(prev_yoy_ago) * 100
    
    # 加速判断: 最近同比 > 上季同比
    if result['latest_yoy_growth'] is not None and result['prev_yoy_growth'] is not None:
        result['eps_accelerating'] = result['latest_yoy_growth'] > result['prev_yoy_growth']
    
    # 连续4季度为正
    if len(eps_series) >= 4:
        last_4 = [q.get('eps') for q in eps_series[:4]]
        result['consistent_positive'] = all(e is not None and e > 0 for e in last_4)
    
    return result


def calculate_revenue_metrics(revenue_series):
    """计算营收增长指标"""
    result = {
        'latest_revenue': None,
        'latest_yoy_growth': None,
        'prev_yoy_growth': None,
        'revenue_accelerating': False,
        'quarters_available': len(revenue_series)
    }
    
    if len(revenue_series) < 1:
        return result
    
    result['latest_revenue'] = revenue_series[0].get('revenue')
    
    if len(revenue_series) < 5:
        return result
    
    latest = revenue_series[0].get('revenue')
    yoy_ago = revenue_series[4].get('revenue')
    
    if latest is not None and yoy_ago is not None and yoy_ago > 0:
        result['latest_yoy_growth'] = (latest - yoy_ago) / yoy_ago * 100
    
    if len(revenue_series) >= 6:
        prev = revenue_series[1].get('revenue')
        prev_yoy_ago = revenue_series[5].get('revenue')
        if prev is not None and prev_yoy_ago is not None and prev_yoy_ago > 0:
            result['prev_yoy_growth'] = (prev - prev_yoy_ago) / prev_yoy_ago * 100
    
    if result['latest_yoy_growth'] is not None and result['prev_yoy_growth'] is not None:
        result['revenue_accelerating'] = result['latest_yoy_growth'] > result['prev_yoy_growth']
    
    return result


def calculate_margin_metrics(quarterly_financials):
    """
    计算净利润率变化
    最近季度 vs 去年同季
    """
    result = {
        'latest_net_margin': None,
        'yoy_net_margin': None,
        'margin_expanding': False
    }
    
    if quarterly_financials is None or quarterly_financials.empty:
        return result
    
    ni_row = None
    rev_row = None
    for key in ['Net Income', 'NetIncome']:
        if key in quarterly_financials.index:
            ni_row = quarterly_financials.loc[key]
            break
    for key in ['Total Revenue', 'Revenue', 'TotalRevenue']:
        if key in quarterly_financials.index:
            rev_row = quarterly_financials.loc[key]
            break
    
    if ni_row is None or rev_row is None:
        return result
    
    # 合并并按时间排序 (从新到旧)
    dates = sorted(ni_row.index, reverse=True)
    if len(dates) < 5:
        return result
    
    latest_date = dates[0]
    yoy_date = dates[4]
    
    latest_ni = ni_row.get(latest_date)
    latest_rev = rev_row.get(latest_date)
    yoy_ni = ni_row.get(yoy_date)
    yoy_rev = rev_row.get(yoy_date)
    
    if all(pd.notna(x) for x in [latest_ni, latest_rev, yoy_ni, yoy_rev]) and latest_rev > 0 and yoy_rev > 0:
        result['latest_net_margin'] = latest_ni / latest_rev * 100
        result['yoy_net_margin'] = yoy_ni / yoy_rev * 100
        result['margin_expanding'] = result['latest_net_margin'] > result['yoy_net_margin']
    
    return result


def extract_info_metrics(info):
    """从info dict提取关键比率"""
    result = {
        'roe': None,
        'profit_margin': None,
        'operating_margin': None,
        'held_by_institutions': None,
        'forward_pe': None,
        'peg_ratio': None,
        'earnings_growth': None,
        'revenue_growth': None,
    }
    
    if not info:
        return result
    
    # ROE: yfinance返回的是小数 (0.17 = 17%)
    roe = info.get('returnOnEquity')
    if roe is not None:
        result['roe'] = float(roe) * 100
    
    pm = info.get('profitMargins')
    if pm is not None:
        result['profit_margin'] = float(pm) * 100
    
    om = info.get('operatingMargins')
    if om is not None:
        result['operating_margin'] = float(om) * 100
    
    hbi = info.get('heldPercentInstitutions')
    if hbi is not None:
        result['held_by_institutions'] = float(hbi) * 100
    
    result['forward_pe'] = info.get('forwardPE')
    result['peg_ratio'] = info.get('pegRatio') or info.get('trailingPegRatio')
    
    # 年度增长率 (作为备用/验证)
    eg = info.get('earningsGrowth') or info.get('earningsQuarterlyGrowth')
    if eg is not None:
        result['earnings_growth'] = float(eg) * 100
    
    rg = info.get('revenueGrowth')
    if rg is not None:
        result['revenue_growth'] = float(rg) * 100
    
    return result


def calculate_fundamental_score(eps_metrics, revenue_metrics, margin_metrics, info_metrics):
    """
    基本面评分 (0-50分)
    
    评分维度:
    - EPS增长 (最高15分): 同比增速和加速
    - 营收增长 (最高10分): 同比增速和加速
    - 盈利能力 (最高10分): ROE + 利润率
    - 利润率趋势 (最高8分): 扩张中
    - 机构认可 (最高7分): 机构持股比例
    """
    score = 0
    details = {}
    
    # === EPS (0-15分) ===
    eps_score = 0
    eps_growth = eps_metrics.get('latest_yoy_growth')
    if eps_growth is not None:
        if eps_growth >= 100:
            eps_score = 10  # 翻倍+
        elif eps_growth >= 40:
            eps_score = 8
        elif eps_growth >= 25:
            eps_score = 6
        elif eps_growth >= 10:
            eps_score = 3
        elif eps_growth > 0:
            eps_score = 1
    
    if eps_metrics.get('eps_accelerating'):
        eps_score += 3
    if eps_metrics.get('consistent_positive'):
        eps_score += 2
    
    eps_score = min(15, eps_score)
    score += eps_score
    details['eps_score'] = eps_score
    
    # === 营收 (0-10分) ===
    rev_score = 0
    rev_growth = revenue_metrics.get('latest_yoy_growth')
    if rev_growth is not None:
        if rev_growth >= 50:
            rev_score = 7
        elif rev_growth >= 25:
            rev_score = 5
        elif rev_growth >= 15:
            rev_score = 3
        elif rev_growth >= 5:
            rev_score = 1
    
    if revenue_metrics.get('revenue_accelerating'):
        rev_score += 3
    
    rev_score = min(10, rev_score)
    score += rev_score
    details['revenue_score'] = rev_score
    
    # === 盈利能力 (0-10分) ===
    profit_score = 0
    roe = info_metrics.get('roe')
    if roe is not None:
        if roe >= 30:
            profit_score += 5
        elif roe >= 20:
            profit_score += 4
        elif roe >= 17:
            profit_score += 3
        elif roe >= 10:
            profit_score += 1
    
    pm = info_metrics.get('profit_margin')
    if pm is not None:
        if pm >= 20:
            profit_score += 5
        elif pm >= 15:
            profit_score += 4
        elif pm >= 10:
            profit_score += 2
        elif pm >= 5:
            profit_score += 1
    
    profit_score = min(10, profit_score)
    score += profit_score
    details['profitability_score'] = profit_score
    
    # === 利润率趋势 (0-8分) ===
    margin_score = 0
    if margin_metrics.get('margin_expanding'):
        margin_score = 8
    elif margin_metrics.get('latest_net_margin') is not None and margin_metrics.get('yoy_net_margin') is not None:
        # 持平但为正 也给部分分
        if margin_metrics['latest_net_margin'] > 0:
            margin_score = 3
    
    score += margin_score
    details['margin_trend_score'] = margin_score
    
    # === 机构认可 (0-7分) ===
    inst_score = 0
    inst_pct = info_metrics.get('held_by_institutions')
    if inst_pct is not None:
        if inst_pct >= 70:
            inst_score = 7
        elif inst_pct >= 50:
            inst_score = 5
        elif inst_pct >= 30:
            inst_score = 3
        elif inst_pct >= 15:
            inst_score = 1
    
    score += inst_score
    details['institutional_score'] = inst_score
    
    return score, details


def grade_from_score(score):
    """50分制 → 字母等级"""
    if score >= 40:
        return 'A'
    elif score >= 30:
        return 'B'
    elif score >= 20:
        return 'C'
    elif score >= 10:
        return 'D'
    else:
        return 'F'


def check_leader_profile(eps_metrics, revenue_metrics, margin_metrics, info_metrics):
    """
    Minervini 的 "Leader Profile" 硬性标准
    全部满足 = 真正的基本面领头羊
    """
    checks = {
        'eps_growth_25plus': False,
        'eps_accelerating': False,
        'revenue_growth_positive': False,
        'roe_17plus': False,
        'margin_expanding_or_high': False,
    }
    
    # EPS 增长 >= 25%
    eps_g = eps_metrics.get('latest_yoy_growth')
    if eps_g is not None and eps_g >= 25:
        checks['eps_growth_25plus'] = True
    
    # EPS 加速
    if eps_metrics.get('eps_accelerating'):
        checks['eps_accelerating'] = True
    
    # 营收正增长
    rev_g = revenue_metrics.get('latest_yoy_growth')
    if rev_g is not None and rev_g > 0:
        checks['revenue_growth_positive'] = True
    
    # ROE >= 17%
    roe = info_metrics.get('roe')
    if roe is not None and roe >= 17:
        checks['roe_17plus'] = True
    
    # 利润率扩张 或 已经很高
    if margin_metrics.get('margin_expanding'):
        checks['margin_expanding_or_high'] = True
    else:
        pm = info_metrics.get('profit_margin')
        if pm is not None and pm >= 15:
            checks['margin_expanding_or_high'] = True
    
    meets_profile = sum(checks.values()) >= 4  # 5条过4条
    return meets_profile, checks


def analyze_fundamentals(ticker, max_retries=3):
    """
    单只股票完整基本面分析 - 对外统一接口
    
    Returns dict with:
    - ticker, timestamp
    - eps: {latest, latest_yoy_growth, prev_yoy_growth, accelerating, consistent_positive}
    - revenue: similar
    - margins: {latest_net_margin, yoy_net_margin, expanding}
    - ratios: {roe, profit_margin, operating_margin, held_by_institutions, forward_pe, peg}
    - score: 0-50
    - grade: A/B/C/D/F
    - details: 每个分项得分
    - meets_leader_profile: bool
    - leader_checks: dict
    """
    raw = get_fundamentals(ticker, max_retries=max_retries)
    if raw is None:
        return None
    
    eps_series = extract_eps_series(raw['quarterly_income'])
    rev_series = extract_revenue_series(raw['quarterly_financials'])
    
    eps_metrics = calculate_eps_metrics(eps_series)
    rev_metrics = calculate_revenue_metrics(rev_series)
    margin_metrics = calculate_margin_metrics(raw['quarterly_financials'])
    info_metrics = extract_info_metrics(raw['info'])
    
    score, details = calculate_fundamental_score(
        eps_metrics, rev_metrics, margin_metrics, info_metrics
    )
    grade = grade_from_score(score)
    
    meets_profile, leader_checks = check_leader_profile(
        eps_metrics, rev_metrics, margin_metrics, info_metrics
    )
    
    return {
        'eps': {
            'latest': eps_metrics.get('latest_eps'),
            'yoy_growth': eps_metrics.get('latest_yoy_growth'),
            'prev_yoy_growth': eps_metrics.get('prev_yoy_growth'),
            'accelerating': eps_metrics.get('eps_accelerating'),
            'consistent_positive': eps_metrics.get('consistent_positive'),
            'quarters_available': eps_metrics.get('quarters_available'),
        },
        'revenue': {
            'latest': rev_metrics.get('latest_revenue'),
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
            'peg_ratio': info_metrics.get('peg_ratio'),
        },
        'score': score,
        'grade': grade,
        'details': details,
        'meets_leader_profile': meets_profile,
        'leader_checks': leader_checks,
    }


# 测试
if __name__ == '__main__':
    print("基本面分析测试")
    print("=" * 70)
    
    for ticker in ['NVDA', 'KLAC', 'TSLA', 'INTC', 'AAPL']:
        print(f"\n=== {ticker} ===")
        result = analyze_fundamentals(ticker)
        if not result:
            print(f"  Failed to fetch")
            continue
        
        print(f"  Score: {result['score']}/50 (Grade: {result['grade']})")
        print(f"  Leader Profile: {'✓ YES' if result['meets_leader_profile'] else '✗ NO'}")
        
        eps = result['eps']
        print(f"  EPS YoY: {eps['yoy_growth']:.1f}%" if eps['yoy_growth'] is not None else "  EPS YoY: N/A")
        print(f"  EPS Prev YoY: {eps['prev_yoy_growth']:.1f}%" if eps['prev_yoy_growth'] is not None else "  EPS Prev YoY: N/A")
        print(f"  EPS Accelerating: {eps['accelerating']}")
        
        rev = result['revenue']
        print(f"  Revenue YoY: {rev['yoy_growth']:.1f}%" if rev['yoy_growth'] is not None else "  Revenue YoY: N/A")
        print(f"  Revenue Accelerating: {rev['accelerating']}")
        
        ratios = result['ratios']
        print(f"  ROE: {ratios['roe']:.1f}%" if ratios['roe'] is not None else "  ROE: N/A")
        print(f"  Profit Margin: {ratios['profit_margin']:.1f}%" if ratios['profit_margin'] is not None else "  PM: N/A")
        print(f"  Inst Holders: {ratios['held_by_institutions']:.1f}%" if ratios['held_by_institutions'] is not None else "  IH: N/A")
        
        margin = result['margins']
        print(f"  Margin Expanding: {margin['expanding']}")
        
        print(f"  Leader checks: {sum(result['leader_checks'].values())}/5")
