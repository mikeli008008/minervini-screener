"""
VCP (Volatility Contraction Pattern) 检测模块
===============================================
基于 Mark Minervini 的真实VCP定义:
- 股票处于Stage 2上升趋势中
- 经历2-6次连续的回调,每次回调深度递减
- 回调期间成交量萎缩
- 最终收敛到一个"紧张点",准备突破

核心算法:
1. 识别最近的整理期(从近期高点开始)
2. 在整理期内找出所有峰谷
3. 测量每次回调幅度(peak→trough)
4. 判断回调幅度是否呈现递减趋势(收缩)
5. 计算最后一次收缩的紧张度
"""
import numpy as np
import pandas as pd


def find_peaks_troughs(prices, min_distance=5, threshold_pct=3.0):
    """
    识别价格序列中的显著峰和谷
    
    Args:
        prices: 收盘价序列 (np.array 或 pd.Series)
        min_distance: 两个极值点之间的最小间隔(交易日)
        threshold_pct: 极值点与相邻点的最小百分比差异
    
    Returns:
        peaks: [(index, price), ...]  峰
        troughs: [(index, price), ...] 谷
    """
    if isinstance(prices, pd.Series):
        prices = prices.values
    n = len(prices)
    if n < min_distance * 2 + 1:
        return [], []
    
    peaks = []
    troughs = []
    
    # 滑动窗口寻找局部极值
    for i in range(min_distance, n - min_distance):
        window = prices[i - min_distance:i + min_distance + 1]
        center = prices[i]
        
        # 是否为窗口内最高点
        if center == window.max() and center != window.min():
            # 必须显著高于窗口两端
            left_max = prices[i - min_distance]
            right_max = prices[i + min_distance]
            if (center - left_max) / left_max * 100 >= threshold_pct or \
               (center - right_max) / right_max * 100 >= threshold_pct:
                # 与最近一个峰值至少间隔min_distance天
                if not peaks or i - peaks[-1][0] >= min_distance:
                    peaks.append((i, center))
        
        # 是否为窗口内最低点
        if center == window.min() and center != window.max():
            left_min = prices[i - min_distance]
            right_min = prices[i + min_distance]
            if (left_min - center) / center * 100 >= threshold_pct or \
               (right_min - center) / center * 100 >= threshold_pct:
                if not troughs or i - troughs[-1][0] >= min_distance:
                    troughs.append((i, center))
    
    return peaks, troughs


def extract_contractions(prices, lookback=90, min_distance=5, threshold_pct=3.0):
    """
    从近期价格序列中提取连续的收缩(回调)
    
    每个收缩 = peak → trough → new peak
    depth = (peak - trough) / peak * 100
    
    Returns:
        contractions: list of dicts, 每个包含:
            - peak_idx, peak_price
            - trough_idx, trough_price  
            - depth_pct (回调深度)
            - duration (回调天数)
    """
    if isinstance(prices, pd.Series):
        prices = prices.values
    
    # 只看最近lookback天
    recent = prices[-lookback:] if len(prices) > lookback else prices
    offset = len(prices) - len(recent)
    
    peaks, troughs = find_peaks_troughs(recent, min_distance, threshold_pct)
    
    if len(peaks) < 1 or len(troughs) < 1:
        return []
    
    # 合并并按时间排序
    all_extrema = [(idx, price, 'P') for idx, price in peaks] + \
                  [(idx, price, 'T') for idx, price in troughs]
    all_extrema.sort(key=lambda x: x[0])
    
    # 提取peak→trough对
    contractions = []
    i = 0
    while i < len(all_extrema) - 1:
        if all_extrema[i][2] == 'P':
            # 找下一个T
            j = i + 1
            while j < len(all_extrema) and all_extrema[j][2] != 'T':
                j += 1
            if j < len(all_extrema):
                peak_idx, peak_price, _ = all_extrema[i]
                trough_idx, trough_price, _ = all_extrema[j]
                if peak_price > trough_price:
                    depth = (peak_price - trough_price) / peak_price * 100
                    contractions.append({
                        'peak_idx': peak_idx + offset,
                        'peak_price': round(float(peak_price), 2),
                        'trough_idx': trough_idx + offset,
                        'trough_price': round(float(trough_price), 2),
                        'depth_pct': round(float(depth), 2),
                        'duration': trough_idx - peak_idx
                    })
                i = j
            else:
                break
        else:
            i += 1
    
    return contractions


def detect_vcp(close, high, low, volume, lookback=90):
    """
    真实的VCP检测 - 综合评分版
    
    判据 (Minervini官方标准):
    1. 至少2次连续收缩(越多越好,3-4次最理想)
    2. 每次收缩深度递减(contractions tightening)
    3. 最后一次收缩深度 < 15% (紧凑整理)
    4. 整理期内成交量整体萎缩
    5. 当前价格接近最近高点(准备突破)
    
    Args:
        close, high, low, volume: pd.Series (最近2年数据)
        lookback: 整理期分析窗口(交易日)
    
    Returns:
        dict:
            - has_vcp: bool, 是否检测到VCP
            - vcp_score: 0-100分
            - contractions: 识别到的收缩列表
            - num_contractions: 收缩次数
            - contractions_tightening: 是否递减
            - last_contraction_pct: 最后一次收缩深度
            - volume_contraction_ratio: 近期vs早期成交量比
            - price_near_pivot: 是否接近突破点
            - pivot_price: 估算的买点
    """
    result = {
        'has_vcp': False,
        'vcp_score': 0,
        'contractions': [],
        'num_contractions': 0,
        'contractions_tightening': False,
        'last_contraction_pct': None,
        'volume_contraction_ratio': None,
        'price_near_pivot': False,
        'pivot_price': None,
        'notes': []
    }
    
    if len(close) < lookback + 20:
        result['notes'].append('insufficient data')
        return result
    
    # 提取收缩
    contractions = extract_contractions(close, lookback=lookback)
    result['contractions'] = contractions
    result['num_contractions'] = len(contractions)
    
    if len(contractions) < 2:
        result['notes'].append(f'only {len(contractions)} contraction(s) found, need >=2')
        return result
    
    # 取最近的2-4次收缩(过老的忽略)
    recent_contractions = contractions[-4:] if len(contractions) > 4 else contractions
    depths = [c['depth_pct'] for c in recent_contractions]
    
    # === 判据1: 收缩深度递减 ===
    # 允许少量噪声,只要整体趋势递减即可
    tightening_score = 0
    decreasing_count = 0
    for i in range(1, len(depths)):
        if depths[i] < depths[i-1]:
            decreasing_count += 1
    tightening_ratio = decreasing_count / (len(depths) - 1)
    result['contractions_tightening'] = tightening_ratio >= 0.5
    
    if tightening_ratio == 1.0:
        tightening_score = 30  # 全部递减
    elif tightening_ratio >= 0.66:
        tightening_score = 20  # 大部分递减
    elif tightening_ratio >= 0.5:
        tightening_score = 10
    
    # === 判据2: 最后一次收缩的紧凑度 ===
    last_depth = depths[-1]
    result['last_contraction_pct'] = round(last_depth, 2)
    
    if last_depth < 8:
        compactness_score = 25   # 非常紧(VCP完美)
    elif last_depth < 12:
        compactness_score = 20
    elif last_depth < 15:
        compactness_score = 15
    elif last_depth < 20:
        compactness_score = 5
    else:
        compactness_score = 0
    
    # === 判据3: 成交量萎缩 ===
    # 比较整理期前半段 vs 后半段的平均成交量
    if len(volume) >= lookback:
        recent_vol = volume.iloc[-lookback:]
        first_half_avg = recent_vol.iloc[:lookback//2].mean()
        second_half_avg = recent_vol.iloc[lookback//2:].mean()
        vol_ratio = second_half_avg / first_half_avg if first_half_avg > 0 else 1.0
        result['volume_contraction_ratio'] = round(float(vol_ratio), 3)
        
        if vol_ratio < 0.7:
            volume_score = 20   # 明显萎缩
        elif vol_ratio < 0.85:
            volume_score = 15
        elif vol_ratio < 1.0:
            volume_score = 8
        else:
            volume_score = 0
    else:
        volume_score = 0
    
    # === 判据4: 接近突破点 ===
    # Pivot = 最近一个主要peak (通常是最后一次收缩起点)
    if recent_contractions:
        pivot_price = recent_contractions[-1]['peak_price']
        current_price = close.iloc[-1]
        result['pivot_price'] = pivot_price
        
        distance_to_pivot = (pivot_price - current_price) / pivot_price * 100
        
        if distance_to_pivot <= 2:
            pivot_score = 15     # 非常接近(可能已突破)
            result['price_near_pivot'] = True
        elif distance_to_pivot <= 5:
            pivot_score = 12
            result['price_near_pivot'] = True
        elif distance_to_pivot <= 10:
            pivot_score = 8
        else:
            pivot_score = 0
    else:
        pivot_score = 0
    
    # === 判据5: 收缩次数奖励 ===
    count_score = min(10, len(recent_contractions) * 3)  # 3次=9分,4次=10分
    
    # === 综合VCP评分 ===
    total_score = tightening_score + compactness_score + volume_score + pivot_score + count_score
    result['vcp_score'] = min(100, total_score)
    
    # has_vcp判定:得分>=50 且 至少2次收缩 且 最后一次<20%
    result['has_vcp'] = bool(
        total_score >= 50 
        and len(recent_contractions) >= 2
        and last_depth < 20
    )
    
    # Notes
    if result['has_vcp']:
        result['notes'].append(f"VCP detected: {len(recent_contractions)} contractions, "
                               f"depths {[f'{d:.1f}%' for d in depths]}")
    
    return result


# 测试用例
if __name__ == '__main__':
    import yfinance as yf
    
    print("VCP算法测试\n" + "="*60)
    
    # 测试几只已知状态的股票
    for ticker in ['NVDA', 'COHR', 'VRT', 'TSLA', 'AAPL']:
        print(f"\n=== {ticker} ===")
        hist = yf.Ticker(ticker).history(period='1y', auto_adjust=True)
        if len(hist) < 100:
            print(f"  {ticker}: insufficient data")
            continue
        result = detect_vcp(hist['Close'], hist['High'], hist['Low'], hist['Volume'])
        print(f"  Has VCP: {result['has_vcp']}")
        print(f"  Score: {result['vcp_score']}")
        print(f"  Contractions: {result['num_contractions']}")
        if result['contractions']:
            depths = [f"{c['depth_pct']:.1f}%" for c in result['contractions']]
            print(f"  Depths: {depths}")
        print(f"  Last contraction: {result['last_contraction_pct']}%")
        print(f"  Volume ratio: {result['volume_contraction_ratio']}")
        print(f"  Pivot: ${result['pivot_price']}")
        print(f"  Near pivot: {result['price_near_pivot']}")
        print(f"  Notes: {result['notes']}")
