"""
Watchlist 模块 - 管理Super Stock/Perfect Setup的历史沉淀
===========================================================
功能:
1. 自动把每次扫描中的 Super Stock 和 Perfect Setup 加入 watchlist.txt
2. 用户可以手动编辑 watchlist.txt (加/删/加注释)
3. 记录每只票首次进入watchlist的日期、信号类型、历史最高评分
4. 为邮件/报告提供 watchlist status

文件格式: watchlist.txt (CSV-like, 每行一只股票)
TICKER | FIRST_SEEN | PEAK_SIGNAL | PEAK_SCORE | NOTE
例如:
TSLA | 2026-04-18 | Perfect | 152.8 | Robotaxi叙事,等基本面兑现
NVDA | 2025-01-15 | Super | 215.3 | AI leader
"""
import os
from datetime import datetime
from pathlib import Path


WATCHLIST_FILE = 'watchlist.txt'
HEADER = """# Minervini Watchlist - 自动沉淀的历史强信号股票
# 格式: TICKER | FIRST_SEEN | PEAK_SIGNAL | PEAK_SCORE | NOTE
# 注释行以 # 开头, 可以随意手动编辑此文件
# 要删除股票直接删除该行, 要加note在最后一列填写
#
# PEAK_SIGNAL: Super (技术+基本面四重共振) > Perfect (技术完美) > Leader (基本面达标)
#
"""


def load_watchlist(path=WATCHLIST_FILE):
    """
    读取 watchlist.txt
    返回 dict: {ticker: {first_seen, peak_signal, peak_score, note}}
    """
    if not os.path.exists(path):
        return {}
    
    entries = {}
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = [p.strip() for p in line.split('|')]
            if len(parts) < 2:
                continue
            
            ticker = parts[0].upper()
            try:
                entries[ticker] = {
                    'first_seen': parts[1] if len(parts) > 1 else '',
                    'peak_signal': parts[2] if len(parts) > 2 else 'Unknown',
                    'peak_score': float(parts[3]) if len(parts) > 3 and parts[3] else 0.0,
                    'note': parts[4] if len(parts) > 4 else '',
                }
            except (ValueError, IndexError):
                # 解析失败的行跳过
                entries[ticker] = {
                    'first_seen': '',
                    'peak_signal': 'Unknown',
                    'peak_score': 0.0,
                    'note': '',
                }
    
    return entries


def save_watchlist(entries, path=WATCHLIST_FILE):
    """保存 watchlist.txt (保留用户手动添加的注释)"""
    lines = [HEADER]
    
    # 按 peak_score 排序 (最强信号在前)
    sorted_tickers = sorted(entries.keys(), 
                            key=lambda t: entries[t].get('peak_score', 0), 
                            reverse=True)
    
    for ticker in sorted_tickers:
        e = entries[ticker]
        note = e.get('note', '').replace('|', '/')  # 防止 | 污染格式
        line = f"{ticker} | {e.get('first_seen','')} | {e.get('peak_signal','')} | {e.get('peak_score', 0):.1f} | {note}"
        lines.append(line)
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def update_watchlist_from_scan(scan_results, path=WATCHLIST_FILE):
    """
    从扫描结果自动沉淀 Super Stock 和 Perfect Setup 到 watchlist
    规则:
    - 新股票: 直接加入, 记录信号类型和评分
    - 已存在股票: 如果本次评分更高,更新peak_score和peak_signal
    - 不降级: 一旦是Super,即使后来只有Perfect,也保留Super标记
    
    Returns: (num_added, num_updated) 统计信息
    """
    entries = load_watchlist(path)
    today = datetime.now().strftime('%Y-%m-%d')
    
    signal_rank = {'Super': 3, 'Perfect': 2, 'Leader': 1, 'Unknown': 0}
    
    added = 0
    updated = 0
    
    for s in scan_results:
        ticker = s['ticker']
        
        # 判断本次信号类型
        if s.get('super_stock_candidate'):
            current_signal = 'Super'
        elif (s.get('vcp', {}).get('has_vcp') 
              and s.get('all_8_passed') 
              and s.get('vcp', {}).get('near_pivot')):
            current_signal = 'Perfect'
        else:
            # 不是Super也不是Perfect的不沉淀
            continue
        
        current_score = s.get('minervini_score', 0)
        
        if ticker not in entries:
            # 新票加入
            entries[ticker] = {
                'first_seen': today,
                'peak_signal': current_signal,
                'peak_score': current_score,
                'note': '',
            }
            added += 1
        else:
            # 已存在,比较信号强度
            existing = entries[ticker]
            existing_rank = signal_rank.get(existing.get('peak_signal', ''), 0)
            current_rank = signal_rank.get(current_signal, 0)
            
            # 升级信号 or 同信号但评分更高
            if current_rank > existing_rank:
                existing['peak_signal'] = current_signal
                existing['peak_score'] = current_score
                updated += 1
            elif current_rank == existing_rank and current_score > existing.get('peak_score', 0):
                existing['peak_score'] = current_score
                updated += 1
    
    save_watchlist(entries, path)
    return added, updated


def get_watchlist_status(scan_results, path=WATCHLIST_FILE):
    """
    根据最新扫描结果,生成watchlist中每只股票的当前状态
    用于邮件/报告显示
    
    Returns: list of dicts with both watchlist metadata and current scan data
    """
    entries = load_watchlist(path)
    if not entries:
        return []
    
    # 建立 ticker -> scan_data 的快速查找
    scan_lookup = {s['ticker']: s for s in scan_results}
    
    result = []
    for ticker, meta in entries.items():
        scan_data = scan_lookup.get(ticker)
        
        if scan_data:
            # 本次扫描有这只票的数据
            current_signal = 'Super' if scan_data.get('super_stock_candidate') else \
                             'Perfect' if (scan_data.get('vcp', {}).get('has_vcp') 
                                          and scan_data.get('all_8_passed') 
                                          and scan_data.get('vcp', {}).get('near_pivot')) else \
                             'Leader' if (scan_data.get('fundamentals') or {}).get('meets_leader_profile') else \
                             'Watching'
            
            # 判断是否需要警示(信号退化)
            signal_rank = {'Super': 3, 'Perfect': 2, 'Leader': 1, 'Watching': 0}
            peak_rank = signal_rank.get(meta.get('peak_signal', ''), 0)
            current_rank = signal_rank.get(current_signal, 0)
            degraded = current_rank < peak_rank
            
            entry = {
                'ticker': ticker,
                'first_seen': meta.get('first_seen', ''),
                'peak_signal': meta.get('peak_signal', ''),
                'peak_score': meta.get('peak_score', 0),
                'note': meta.get('note', ''),
                'current_signal': current_signal,
                'current_score': scan_data.get('minervini_score', 0),
                'degraded': degraded,
                'scan_data': scan_data,  # 完整当前数据
            }
        else:
            # 扫描结果中没有这只票 (rate limited or removed from universe)
            entry = {
                'ticker': ticker,
                'first_seen': meta.get('first_seen', ''),
                'peak_signal': meta.get('peak_signal', ''),
                'peak_score': meta.get('peak_score', 0),
                'note': meta.get('note', ''),
                'current_signal': 'No Data',
                'current_score': 0,
                'degraded': True,
                'scan_data': None,
            }
        
        result.append(entry)
    
    # 排序: 当前Super > Perfect > Leader > Watching > No Data, 再按peak_score降序
    signal_rank = {'Super': 4, 'Perfect': 3, 'Leader': 2, 'Watching': 1, 'No Data': 0}
    result.sort(key=lambda x: (signal_rank.get(x['current_signal'], 0), 
                                x.get('peak_score', 0)), 
                reverse=True)
    
    return result


if __name__ == '__main__':
    # 测试
    print("Watchlist 模块测试")
    print("=" * 60)
    
    entries = load_watchlist()
    if entries:
        print(f"当前watchlist有 {len(entries)} 只股票:")
        for ticker, meta in sorted(entries.items(), 
                                    key=lambda x: x[1].get('peak_score', 0), 
                                    reverse=True)[:10]:
            print(f"  {ticker}: {meta['peak_signal']} (peak {meta['peak_score']}) - {meta['note']}")
    else:
        print("Watchlist 为空 (watchlist.txt 不存在)")
        print("运行 scanner.py 后会自动创建")
