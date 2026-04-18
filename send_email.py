"""
Minervini Screener - 邮件推送
=====================================
读取 reports/latest.json,生成HTML邮件,通过SMTP发送

环境变量配置(GitHub Secrets):
- SMTP_HOST      (默认 smtp.gmail.com)
- SMTP_PORT      (默认 587)
- SMTP_USER      (你的邮箱)
- SMTP_PASS      (应用专用密码,非账户密码)
- EMAIL_FROM     (发件人,通常同SMTP_USER)
- EMAIL_TO       (收件人,多个用逗号分隔)
- REPORT_URL     (可选,GitHub Pages完整报告链接)
"""
import json
import os
import sys
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime


def load_report(path='reports/latest.json'):
    with open(path) as f:
        return json.load(f)


def mini_sparkline(prices, width=120, height=28, color='#d4ff00'):
    """小型价格走势SVG"""
    if not prices or len(prices) < 2:
        return ''
    vals = [p['c'] for p in prices]
    mn, mx = min(vals), max(vals)
    rng = mx - mn or 1
    n = len(vals)
    points = []
    for i, v in enumerate(vals):
        x = (i / (n - 1)) * width
        y = height - ((v - mn) / rng) * height
        points.append(f"{x:.1f},{y:.1f}")
    pts_str = ' '.join(points)
    
    # 判断涨跌色
    actual_color = color if vals[-1] >= vals[0] else '#ff4444'
    
    return f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" style="vertical-align:middle;">
<polyline points="{pts_str}" fill="none" stroke="{actual_color}" stroke-width="1.5"/>
<circle cx="{(n-1)/(n-1)*width:.1f}" cy="{height - ((vals[-1]-mn)/rng)*height:.1f}" r="2" fill="{actual_color}"/>
</svg>'''


def criteria_dots(criteria_dict):
    """生成8个评分点"""
    dots = []
    for v in criteria_dict.values():
        if v:
            dots.append('<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#d4ff00;margin-right:2px;"></span>')
        else:
            dots.append('<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#3a3a3a;margin-right:2px;"></span>')
    return ''.join(dots)


def render_email(report, report_url=None):
    """生成HTML邮件内容"""
    date = report['date']
    total = report['total_stocks']
    pass8 = report['all_8_passed_count']
    pass7 = report['pass_7_count']
    true_vcp = report.get('true_vcp_count', 0)
    perfect = report.get('perfect_setup_count', 0)
    near_pivot = report.get('near_pivot_count', 0)
    leader_count = report.get('leader_profile_count', 0)
    super_count = report.get('super_stock_count', 0)
    grade_a = report.get('grade_a_count', 0)
    grade_b = report.get('grade_b_count', 0)
    watchlist = report.get('watchlist_status', [])
    spy_ret = report['spy_return_1y']
    
    stocks = sorted(report['stocks'], key=lambda x: x['minervini_score'], reverse=True)
    top20 = stocks[:20]
    
    # === 精选列表 (按优先级分层) ===
    # ★★ Super Stock: 真VCP + 8/8 + near pivot + Leader Profile (四重共振,最高优先级)
    super_stocks = [s for s in stocks if s.get('super_stock_candidate')][:8]
    
    # ★ Perfect Setup (技术面完美,但未必基本面达标) - 排除已入super的
    perfect_setups = [s for s in stocks 
                      if s.get('vcp', {}).get('has_vcp') 
                      and s['all_8_passed']
                      and s.get('vcp', {}).get('near_pivot')
                      and s not in super_stocks][:8]
    
    # Leader Profile (基本面达标) - 排除已入上两区的
    leader_list = [s for s in stocks 
                   if (s.get('fundamentals') or {}).get('meets_leader_profile')
                   and s not in super_stocks
                   and s not in perfect_setups][:8]
    
    # True VCP (技术面VCP但未进前三区)
    true_vcp_list = [s for s in stocks 
                     if s.get('vcp', {}).get('has_vcp') 
                     and s not in super_stocks
                     and s not in perfect_setups
                     and s not in leader_list][:6]
    
    # Breakout watch: 距52周高点≤3% + 至少7条通过
    breakout_watch = [s for s in stocks 
                      if s['pct_from_high'] > -3 
                      and s['criteria_passed'] >= 7
                      and s not in super_stocks
                      and s not in perfect_setups][:6]
    
    # 板块分布
    sector_counts = {}
    for s in stocks[:50]:
        sec = s['sector']
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
    sector_counts = dict(sorted(sector_counts.items(), key=lambda x: -x[1])[:6])
    
    report_link_html = ''
    if report_url:
        report_link_html = f'''
        <div style="text-align:center;margin:24px 0;">
          <a href="{report_url}" style="display:inline-block;background:#d4ff00;color:#0a0a0a;padding:12px 32px;text-decoration:none;font-weight:700;letter-spacing:0.1em;font-size:12px;border-radius:2px;">
            VIEW FULL INTERACTIVE REPORT →
          </a>
        </div>'''
    
    # === ★★ Super Stock 专区 (最高优先级 - 技术+基本面四重共振) ===
    super_html = ''
    if super_stocks:
        rows = ''
        for s in super_stocks:
            v = s.get('vcp', {})
            f = s.get('fundamentals') or {}
            eps_g = (f.get('eps') or {}).get('yoy_growth')
            rev_g = (f.get('revenue') or {}).get('yoy_growth')
            roe = (f.get('ratios') or {}).get('roe')
            
            depths = [c['depth_pct'] for c in v.get('contractions', [])[-3:]]
            depths_str = ' → '.join([f'{d:.1f}%' for d in depths])
            current = s['price']
            pivot = v.get('pivot_price', 0)
            dist_to_pivot = ((pivot - current) / pivot * 100) if pivot else 0
            pivot_status = 'ABOVE' if current >= pivot else f'{dist_to_pivot:.1f}% below'
            pivot_color = '#00d68f' if current >= pivot else '#ffaa00'
            
            eps_str = f"+{eps_g:.0f}%" if eps_g is not None and eps_g >= 0 else (f"{eps_g:.0f}%" if eps_g is not None else "—")
            rev_str = f"+{rev_g:.0f}%" if rev_g is not None and rev_g >= 0 else (f"{rev_g:.0f}%" if rev_g is not None else "—")
            roe_str = f"{roe:.0f}%" if roe is not None else "—"
            grade = f.get('grade', '—')
            grade_color = '#00d68f' if grade == 'A' else '#d4ff00' if grade == 'B' else '#ffaa00'
            
            rows += f'''
            <tr style="border-bottom:1px solid #1f1f1f;">
              <td style="padding:14px 12px;vertical-align:top;">
                <div style="color:#00ff9d;font-weight:800;font-size:15px;letter-spacing:0.02em;">{s['ticker']}</div>
                <div style="color:#aaa;font-size:10px;margin-top:2px;">{s['name'][:28]}</div>
                <div style="color:#666;font-size:9px;margin-top:4px;letter-spacing:0.05em;text-transform:uppercase;">{s['sector'][:18]}</div>
              </td>
              <td style="padding:14px 10px;text-align:right;vertical-align:top;">
                <div style="font-family:Georgia,serif;font-size:22px;color:#00ff9d;font-weight:700;">{s['minervini_score']}</div>
                <div style="color:#666;font-size:9px;letter-spacing:0.1em;text-transform:uppercase;margin-top:2px;">score</div>
              </td>
              <td style="padding:14px 10px;text-align:right;vertical-align:top;">
                <div style="font-family:monospace;color:#fff;font-size:14px;">${s['price']:.2f}</div>
                <div style="color:{pivot_color};font-size:10px;margin-top:4px;">
                  Pivot: <b>${pivot:.2f}</b>
                </div>
                <div style="color:#888;font-size:9px;margin-top:2px;">{pivot_status}</div>
              </td>
              <td style="padding:14px 10px;vertical-align:top;">
                <div style="color:#aaa;font-size:9px;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:3px;">VCP · {v.get('num_contractions',0)} cntr</div>
                <div style="font-family:monospace;font-size:11px;color:#d4ff00;letter-spacing:0.02em;">{depths_str}</div>
                <div style="color:#666;font-size:9px;margin-top:4px;">VCP: {v.get('score',0)}/100</div>
              </td>
              <td style="padding:14px 10px;vertical-align:top;border-left:1px solid #1f1f1f;">
                <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">
                  <span style="color:{grade_color};font-family:Georgia,serif;font-weight:700;font-size:16px;">{grade}</span>
                  <span style="color:#666;font-size:9px;letter-spacing:0.1em;">Grade · {f.get('score',0)}/50</span>
                </div>
                <div style="font-size:10px;color:#aaa;line-height:1.6;margin-top:4px;">
                  <span style="color:#666;">EPS:</span> <b style="color:#00d68f;">{eps_str}</b>
                  &nbsp;·&nbsp; <span style="color:#666;">Rev:</span> <b style="color:#00d68f;">{rev_str}</b>
                </div>
                <div style="font-size:10px;color:#aaa;margin-top:3px;">
                  <span style="color:#666;">ROE:</span> <b>{roe_str}</b>
                  &nbsp;·&nbsp; <span style="color:#00ff9d;font-weight:600;">LEADER ✓</span>
                </div>
              </td>
            </tr>'''
        
        super_html = f'''
        <!-- ★★ Super Stock -->
        <div style="margin:28px 28px 0;padding:22px;background:linear-gradient(135deg, rgba(0,255,157,0.1), rgba(0,214,143,0.02));border:2px solid rgba(0,255,157,0.35);border-left:4px solid #00ff9d;">
          <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;">
            <h2 style="font-family:Georgia,serif;font-size:22px;font-weight:500;color:#00ff9d;margin:0;letter-spacing:-0.01em;">
              ★★ Super Stock
            </h2>
            <span style="color:#aaa;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;">{len(super_stocks)} found</span>
          </div>
          <p style="font-size:11px;color:#ccc;margin:0 0 16px;letter-spacing:0.03em;">
            True VCP · 8/8 template · near pivot · <b style="color:#00ff9d;">Leader Profile (基本面达标)</b>
            &nbsp;→&nbsp; <b style="color:#00ff9d;">Minervini 大牛股候选信号</b>
          </p>
          <table style="width:100%;border-collapse:collapse;">{rows}</table>
        </div>'''
    
    # === Perfect Setup 专区 (技术面完美,但基本面未必达标) ===
    perfect_html = ''
    if perfect_setups:
        rows = ''
        for s in perfect_setups:
            v = s.get('vcp', {})
            f = s.get('fundamentals') or {}
            depths = [c['depth_pct'] for c in v.get('contractions', [])[-4:]]
            depths_str = ' → '.join([f'{d:.1f}%' for d in depths])
            current = s['price']
            pivot = v.get('pivot_price', 0)
            dist_to_pivot = ((pivot - current) / pivot * 100) if pivot else 0
            pivot_status = 'ABOVE' if current >= pivot else f'{dist_to_pivot:.1f}% below'
            pivot_color = '#d4ff00' if current >= pivot else '#ffaa00'
            grade = f.get('grade', '—')
            grade_color = '#00d68f' if grade == 'A' else '#d4ff00' if grade == 'B' else '#ffaa00' if grade == 'C' else '#888'
            
            rows += f'''
            <tr style="border-bottom:1px solid #1f1f1f;">
              <td style="padding:14px 12px;vertical-align:top;">
                <div style="color:#d4ff00;font-weight:700;font-size:14px;letter-spacing:0.02em;">{s['ticker']}</div>
                <div style="color:#888;font-size:10px;margin-top:2px;">{s['name'][:30]}</div>
                <div style="color:#666;font-size:9px;margin-top:4px;letter-spacing:0.05em;text-transform:uppercase;">{s['sector'][:18]}</div>
              </td>
              <td style="padding:14px 12px;text-align:right;vertical-align:top;">
                <div style="font-family:Georgia,serif;font-size:20px;color:#d4ff00;font-weight:600;">{s['minervini_score']}</div>
                <div style="color:#666;font-size:9px;letter-spacing:0.1em;text-transform:uppercase;margin-top:2px;">score</div>
                <div style="margin-top:6px;">
                  <span style="color:{grade_color};font-size:10px;font-weight:600;">Fund: {grade}</span>
                </div>
              </td>
              <td style="padding:14px 12px;text-align:right;vertical-align:top;">
                <div style="font-family:monospace;color:#fff;font-size:14px;">${s['price']:.2f}</div>
                <div style="color:{pivot_color};font-size:10px;margin-top:4px;">
                  Pivot: <b>${pivot:.2f}</b>
                </div>
                <div style="color:#888;font-size:9px;margin-top:2px;">{pivot_status}</div>
              </td>
              <td style="padding:14px 12px;vertical-align:top;">
                <div style="color:#aaa;font-size:10px;margin-bottom:4px;letter-spacing:0.1em;text-transform:uppercase;">Contractions ({v.get('num_contractions',0)})</div>
                <div style="font-family:monospace;font-size:11px;color:#d4ff00;letter-spacing:0.02em;">{depths_str}</div>
                <div style="color:#666;font-size:9px;margin-top:4px;">VCP: {v.get('score',0)}/100 · Vol: {v.get('volume_ratio',1):.2f}×</div>
              </td>
            </tr>'''
        
        perfect_html = f'''
        <!-- Perfect Setups -->
        <div style="margin:28px 28px 0;padding:20px;background:linear-gradient(135deg, rgba(212,255,0,0.08), rgba(212,255,0,0.02));border:1px solid rgba(212,255,0,0.3);border-left:3px solid #d4ff00;">
          <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;">
            <h2 style="font-family:Georgia,serif;font-size:20px;font-weight:400;color:#d4ff00;margin:0;">
              ★ Perfect Setups
            </h2>
            <span style="color:#888;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;">{len(perfect_setups)} found</span>
          </div>
          <p style="font-size:11px;color:#aaa;margin:0 0 16px;letter-spacing:0.03em;">
            Technical perfect (真VCP + 8/8 + near pivot) · <b>check Fund grade</b> before trading
          </p>
          <table style="width:100%;border-collapse:collapse;">{rows}</table>
        </div>'''
    
    # === Leader Profile 专区 (基本面达标但技术面未完美) ===
    leader_html = ''
    if leader_list:
        rows = ''
        for s in leader_list:
            f = s.get('fundamentals') or {}
            eps_g = (f.get('eps') or {}).get('yoy_growth')
            rev_g = (f.get('revenue') or {}).get('yoy_growth')
            roe = (f.get('ratios') or {}).get('roe')
            grade = f.get('grade', '—')
            grade_color = '#00d68f' if grade == 'A' else '#d4ff00' if grade == 'B' else '#ffaa00'
            eps_str = f"+{eps_g:.0f}%" if eps_g is not None and eps_g >= 0 else (f"{eps_g:.0f}%" if eps_g is not None else "—")
            rev_str = f"+{rev_g:.0f}%" if rev_g is not None and rev_g >= 0 else (f"{rev_g:.0f}%" if rev_g is not None else "—")
            roe_str = f"{roe:.0f}%" if roe is not None else "—"
            
            rows += f'''
            <tr style="border-bottom:1px solid #1a1a1a;">
              <td style="padding:8px 10px;vertical-align:top;">
                <div style="color:#fff;font-weight:700;font-size:12px;">{s['ticker']}</div>
                <div style="color:#888;font-size:10px;">{s['name'][:24]}</div>
              </td>
              <td style="padding:8px 10px;text-align:center;">
                <span style="color:{grade_color};font-family:Georgia,serif;font-weight:700;font-size:14px;">{grade}</span>
              </td>
              <td style="padding:8px 10px;text-align:right;color:#00d68f;font-family:monospace;font-size:11px;">{eps_str}</td>
              <td style="padding:8px 10px;text-align:right;color:#00d68f;font-family:monospace;font-size:11px;">{rev_str}</td>
              <td style="padding:8px 10px;text-align:right;color:#ccc;font-family:monospace;font-size:11px;">{roe_str}</td>
              <td style="padding:8px 10px;text-align:right;color:#aaa;font-size:11px;">{s['criteria_passed']}/8</td>
            </tr>'''
        
        leader_html = f'''
        <!-- Leader Profile -->
        <div style="margin:24px 28px 0;padding:18px;background:rgba(0,214,143,0.04);border:1px solid rgba(0,214,143,0.25);border-left:3px solid #00d68f;">
          <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px;">
            <h3 style="font-family:Georgia,serif;font-size:17px;font-weight:400;color:#00d68f;margin:0;">
              🏆 Leader Profile
            </h3>
            <span style="color:#888;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;">{len(leader_list)} found</span>
          </div>
          <p style="font-size:10px;color:#888;margin:0 0 12px;">
            Strong fundamentals (5-point leader check passed) · waiting for technical confirmation
          </p>
          <table style="width:100%;border-collapse:collapse;">
            <tr style="background:#000;">
              <td style="padding:6px 10px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;">Ticker</td>
              <td style="padding:6px 10px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;text-align:center;">Grade</td>
              <td style="padding:6px 10px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;text-align:right;">EPS YoY</td>
              <td style="padding:6px 10px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;text-align:right;">Rev YoY</td>
              <td style="padding:6px 10px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;text-align:right;">ROE</td>
              <td style="padding:6px 10px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;text-align:right;">Criteria</td>
            </tr>
            {rows}
          </table>
        </div>'''
    
    # === Watchlist 专区 (所有曾经达到 Super/Perfect 的股票当前状态) ===
    watchlist_html = ''
    if watchlist:
        rows = ''
        for w in watchlist:
            current = w.get('current_signal', 'Unknown')
            peak = w.get('peak_signal', 'Unknown')
            degraded = w.get('degraded', False)
            note = w.get('note', '') or ''
            
            # 当前信号配色
            current_color = {
                'Super': '#00ff9d',
                'Perfect': '#d4ff00',
                'Leader': '#00d68f',
                'Watching': '#888',
                'No Data': '#555'
            }.get(current, '#888')
            
            # 状态图标
            if current == peak:
                status_icon = '●'  # 维持
                status_color = current_color
            elif degraded:
                status_icon = '↓'  # 降级
                status_color = '#ff8888'
            else:
                status_icon = '↑'  # 升级
                status_color = '#00ff9d'
            
            price = w.get('price')
            name = w.get('name', w['ticker'])
            pct_from_high = w.get('pct_from_high')
            rs = w.get('rs_rating')
            criteria_passed = w.get('criteria_passed')
            grade = w.get('fund_grade') or '—'
            pivot = w.get('pivot_price')
            
            price_str = f"${price:.2f}" if price else "—"
            pct_str = f"{pct_from_high:+.1f}%" if pct_from_high is not None else "—"
            rs_str = f"{int(rs)}" if rs is not None else "—"
            pass_str = f"{criteria_passed}/8" if criteria_passed is not None else "—"
            pivot_str = f"${pivot:.0f}" if pivot else "—"
            
            note_html = f'<div style="color:#999;font-size:10px;font-style:italic;margin-top:2px;">{note[:60]}</div>' if note else ''
            
            # 当前信号tag
            current_tag = f'<span style="display:inline-block;background:{current_color};color:#000;padding:2px 7px;font-size:9px;font-weight:700;letter-spacing:0.05em;">{current}</span>'
            
            rows += f'''
            <tr style="border-bottom:1px solid #1a1a1a;">
              <td style="padding:10px 10px;vertical-align:top;">
                <div style="color:#fff;font-weight:700;font-size:13px;">{w['ticker']}</div>
                <div style="color:#888;font-size:10px;">{name[:24]}</div>
                {note_html}
              </td>
              <td style="padding:10px 8px;text-align:center;vertical-align:top;">
                <span style="color:{status_color};font-size:16px;font-weight:700;">{status_icon}</span>
              </td>
              <td style="padding:10px 6px;text-align:center;vertical-align:top;">
                <div style="color:#666;font-size:9px;">PEAK</div>
                <div style="color:#aaa;font-size:11px;font-weight:500;">{peak}</div>
                <div style="color:#666;font-size:9px;margin-top:2px;">{w.get('peak_score', 0):.0f}</div>
              </td>
              <td style="padding:10px 6px;text-align:center;vertical-align:top;">
                <div style="color:#666;font-size:9px;">NOW</div>
                <div style="margin:3px 0;">{current_tag}</div>
                <div style="color:#666;font-size:9px;">{w.get('current_score', 0):.0f}</div>
              </td>
              <td style="padding:10px 6px;text-align:center;vertical-align:top;">
                <span style="color:#ccc;font-family:Georgia,serif;font-weight:600;font-size:13px;">{grade}</span>
              </td>
              <td style="padding:10px 6px;text-align:right;vertical-align:top;color:#ccc;font-size:11px;">{pass_str}</td>
              <td style="padding:10px 6px;text-align:right;vertical-align:top;color:#ccc;font-size:11px;">{rs_str}</td>
              <td style="padding:10px 6px;text-align:right;vertical-align:top;color:#fff;font-family:monospace;font-size:11px;">{price_str}</td>
              <td style="padding:10px 6px;text-align:right;vertical-align:top;">
                <div style="color:#ffaa00;font-family:monospace;font-size:11px;">{pivot_str}</div>
                <div style="color:#888;font-size:9px;">{pct_str}</div>
              </td>
            </tr>'''
        
        watchlist_html = f'''
        <!-- Watchlist -->
        <div style="margin:28px 28px 0;padding:20px;background:rgba(138,43,226,0.04);border:1px solid rgba(138,43,226,0.25);border-left:3px solid #a87ff0;">
          <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px;">
            <h3 style="font-family:Georgia,serif;font-size:17px;font-weight:400;color:#a87ff0;margin:0;">
              👁 Watchlist
            </h3>
            <span style="color:#888;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;">{len(watchlist)} tracked</span>
          </div>
          <p style="font-size:10px;color:#888;margin:0 0 14px;">
            Historical Super/Perfect signals · sorted by current signal strength · <span style="color:#999;">● maintained &nbsp; ↓ degraded &nbsp; ↑ upgraded</span>
          </p>
          <table style="width:100%;border-collapse:collapse;font-size:11px;">
            <thead>
              <tr style="background:#000;">
                <td style="padding:6px 8px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;">Ticker</td>
                <td style="padding:6px 8px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;text-align:center;">Δ</td>
                <td style="padding:6px 6px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;text-align:center;">Peak</td>
                <td style="padding:6px 6px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;text-align:center;">Current</td>
                <td style="padding:6px 6px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;text-align:center;">Fund</td>
                <td style="padding:6px 6px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;text-align:right;">Pass</td>
                <td style="padding:6px 6px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;text-align:right;">RS</td>
                <td style="padding:6px 6px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;text-align:right;">Price</td>
                <td style="padding:6px 6px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;text-align:right;">Pivot / High</td>
              </tr>
            </thead>
            <tbody>
            {rows}
            </tbody>
          </table>
        </div>'''
    
    # === Top 20 表格行 ===
    top_rows = ''
    for i, s in enumerate(top20):
        dots = criteria_dots(s['criteria'])
        spark = mini_sparkline(s['price_history'])
        ret_color = '#00d68f' if s['return_1y'] >= 0 else '#ff4444'
        rs_color = '#d4ff00' if s['rs_rating'] >= 90 else '#ffaa00' if s['rs_rating'] >= 70 else '#888'
        
        v = s.get('vcp', {})
        f = s.get('fundamentals') or {}
        grade = f.get('grade', '—')
        grade_color = '#00ff9d' if grade == 'A' else '#d4ff00' if grade == 'B' else '#ffaa00' if grade == 'C' else '#ff8888' if grade in ('D','F') else '#555'
        
        setup_tags = []
        if s.get('super_stock_candidate'):
            setup_tags.append('<span style="display:inline-block;background:linear-gradient(135deg,rgba(0,255,157,0.3),rgba(0,255,157,0.1));color:#00ff9d;padding:2px 6px;font-size:9px;letter-spacing:0.05em;font-weight:800;margin-right:3px;border:1px solid rgba(0,255,157,0.5);">★★SUPER</span>')
        elif v.get('has_vcp'):
            setup_tags.append('<span style="display:inline-block;background:rgba(212,255,0,0.2);color:#d4ff00;padding:2px 6px;font-size:9px;letter-spacing:0.05em;font-weight:600;margin-right:3px;">★VCP</span>')
        elif s.get('volatility_contraction'):
            setup_tags.append('<span style="display:inline-block;background:rgba(212,255,0,0.1);color:#9ab800;padding:2px 6px;font-size:9px;letter-spacing:0.05em;margin-right:3px;">atr</span>')
        if v.get('near_pivot'):
            setup_tags.append('<span style="display:inline-block;background:rgba(255,170,0,0.2);color:#ffaa00;padding:2px 6px;font-size:9px;letter-spacing:0.05em;margin-right:3px;">PIVOT</span>')
        if f.get('meets_leader_profile'):
            setup_tags.append('<span style="display:inline-block;background:rgba(0,214,143,0.2);color:#00d68f;padding:2px 6px;font-size:9px;letter-spacing:0.05em;font-weight:600;margin-right:3px;">LDR</span>')
        if s.get('volume_drying'):
            setup_tags.append('<span style="display:inline-block;background:rgba(0,214,143,0.15);color:#00d68f;padding:2px 6px;font-size:9px;letter-spacing:0.05em;">VOL↓</span>')
        setup_html = ''.join(setup_tags) or '<span style="color:#555;font-size:10px;">—</span>'
        
        bg = '#0f0f0f' if i % 2 == 0 else '#141414'
        
        top_rows += f'''
        <tr style="background:{bg};">
          <td style="padding:10px 10px;color:#555;font-size:11px;width:24px;">{i+1}</td>
          <td style="padding:10px 10px;">
            <div style="color:#fff;font-weight:700;font-size:13px;letter-spacing:0.02em;">{s['ticker']}</div>
            <div style="color:#888;font-size:10px;margin-top:2px;">{s['name'][:24]}</div>
          </td>
          <td style="padding:10px 8px;text-align:right;">
            <div style="color:#d4ff00;font-weight:700;font-size:15px;font-family:Georgia,serif;">{s['minervini_score']}</div>
          </td>
          <td style="padding:10px 6px;text-align:center;">
            <div>{dots}</div>
            <div style="color:#555;font-size:10px;margin-top:3px;">{s['criteria_passed']}/8</div>
          </td>
          <td style="padding:10px 6px;text-align:center;">
            <span style="color:{rs_color};border:1px solid {rs_color};padding:2px 7px;font-size:11px;font-weight:500;">{int(s['rs_rating'])}</span>
          </td>
          <td style="padding:10px 6px;text-align:center;">
            <span style="color:{grade_color};font-family:Georgia,serif;font-weight:700;font-size:14px;">{grade}</span>
          </td>
          <td style="padding:10px 8px;text-align:right;color:#fff;font-family:monospace;font-size:11px;">${s['price']:.2f}</td>
          <td style="padding:10px 6px;text-align:right;color:{ret_color};font-family:monospace;font-weight:500;font-size:11px;">{'+' if s['return_1y']>=0 else ''}{s['return_1y']:.0f}%</td>
          <td style="padding:10px 8px;text-align:right;">{spark}</td>
          <td style="padding:10px 8px;">{setup_html}</td>
        </tr>'''
    
    # === True VCP 列表(非perfect) ===
    vcp_html = ''
    for s in true_vcp_list:
        v = s.get('vcp', {})
        depths = [f'{c["depth_pct"]:.1f}%' for c in v.get('contractions', [])[-3:]]
        depths_str = '→'.join(depths)
        pivot = v.get('pivot_price', 0)
        vcp_html += f'''
        <tr style="border-bottom:1px solid #1a1a1a;">
          <td style="padding:8px;color:#fff;font-weight:700;font-size:12px;">{s['ticker']}</td>
          <td style="padding:8px;color:#888;font-size:11px;">{s['name'][:22]}</td>
          <td style="padding:8px;text-align:right;color:#d4ff00;font-family:monospace;font-size:10px;">{depths_str}</td>
          <td style="padding:8px;text-align:right;color:#ffaa00;font-family:monospace;font-size:11px;">${pivot:.2f}</td>
        </tr>'''
    
    # === Breakout watch ===
    breakout_html = ''
    for s in breakout_watch:
        breakout_html += f'''
        <tr style="border-bottom:1px solid #1a1a1a;">
          <td style="padding:8px;color:#fff;font-weight:700;font-size:12px;">{s['ticker']}</td>
          <td style="padding:8px;color:#888;font-size:11px;">{s['name'][:22]}</td>
          <td style="padding:8px;text-align:right;color:#ffaa00;font-family:monospace;font-size:11px;">{s['pct_from_high']:+.1f}%</td>
          <td style="padding:8px;text-align:right;color:#d4ff00;font-family:monospace;font-size:11px;">${s['price']:.2f}</td>
        </tr>'''
    
    # === Sector breakdown ===
    sector_html = ''
    max_count = max(sector_counts.values()) if sector_counts else 1
    for sec, count in sector_counts.items():
        pct = count / max_count * 100
        sector_html += f'''
        <div style="margin-bottom:8px;">
          <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px;">
            <span style="color:#aaa;">{sec[:22]}</span>
            <span style="color:#888;">{count}</span>
          </div>
          <div style="height:4px;background:#1a1a1a;">
            <div style="height:100%;background:#d4ff00;width:{pct}%;"></div>
          </div>
        </div>'''
    
    html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Minervini Daily Scan · {date}</title>
</head>
<body style="margin:0;padding:0;background:#000;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#e8e8e8;">

<div style="max-width:720px;margin:0 auto;background:#0a0a0a;">

  <!-- Header -->
  <div style="padding:32px 28px 24px;border-bottom:1px solid #1f1f1f;">
    <div style="font-family:Georgia,serif;font-size:28px;font-weight:300;letter-spacing:-0.02em;color:#fff;">
      MINERVINI <em style="color:#d4ff00;font-style:italic;">SCREENER</em>
    </div>
    <div style="font-size:10px;color:#888;letter-spacing:0.2em;text-transform:uppercase;margin-top:6px;">
      Daily Scan · {date} · SEPA / Stage 2 · True VCP Detection
    </div>
  </div>

  <!-- Summary stats (两行 - 技术+基本面) -->
  <table style="width:100%;border-collapse:collapse;background:#0a0a0a;">
    <tr>
      <td style="padding:14px 10px;border-right:1px solid #1f1f1f;border-bottom:1px solid #1f1f1f;width:16.66%;">
        <div style="font-size:9px;color:#888;letter-spacing:0.15em;text-transform:uppercase;">Universe</div>
        <div style="font-family:Georgia,serif;font-size:24px;font-weight:300;color:#d4ff00;margin-top:3px;">{total}</div>
        <div style="font-size:9px;color:#666;margin-top:1px;">scanned</div>
      </td>
      <td style="padding:14px 10px;border-right:1px solid #1f1f1f;border-bottom:1px solid #1f1f1f;width:16.66%;background:{('linear-gradient(135deg, rgba(0,255,157,0.08), transparent)' if super_count > 0 else '#0a0a0a')};">
        <div style="font-size:9px;color:#00ff9d;letter-spacing:0.15em;text-transform:uppercase;font-weight:700;">★★ Super</div>
        <div style="font-family:Georgia,serif;font-size:24px;font-weight:500;color:#00ff9d;margin-top:3px;">{super_count}</div>
        <div style="font-size:9px;color:#00ff9d;margin-top:1px;">tech+fund</div>
      </td>
      <td style="padding:14px 10px;border-right:1px solid #1f1f1f;border-bottom:1px solid #1f1f1f;width:16.66%;background:{('linear-gradient(135deg, rgba(212,255,0,0.05), transparent)' if perfect > 0 else '#0a0a0a')};">
        <div style="font-size:9px;color:#d4ff00;letter-spacing:0.15em;text-transform:uppercase;font-weight:600;">★ Perfect</div>
        <div style="font-family:Georgia,serif;font-size:24px;font-weight:400;color:#d4ff00;margin-top:3px;">{perfect}</div>
        <div style="font-size:9px;color:#d4ff00;margin-top:1px;">tech perfect</div>
      </td>
      <td style="padding:14px 10px;border-right:1px solid #1f1f1f;border-bottom:1px solid #1f1f1f;width:16.66%;">
        <div style="font-size:9px;color:#00d68f;letter-spacing:0.15em;text-transform:uppercase;">🏆 Leader</div>
        <div style="font-family:Georgia,serif;font-size:24px;font-weight:300;color:#00d68f;margin-top:3px;">{leader_count}</div>
        <div style="font-size:9px;color:#666;margin-top:1px;">fund strong</div>
      </td>
      <td style="padding:14px 10px;border-right:1px solid #1f1f1f;border-bottom:1px solid #1f1f1f;width:16.66%;">
        <div style="font-size:9px;color:#888;letter-spacing:0.15em;text-transform:uppercase;">8/8 Pass</div>
        <div style="font-family:Georgia,serif;font-size:24px;font-weight:300;color:#fff;margin-top:3px;">{pass8}</div>
        <div style="font-size:9px;color:#666;margin-top:1px;">template qual.</div>
      </td>
      <td style="padding:14px 10px;border-bottom:1px solid #1f1f1f;width:16.68%;">
        <div style="font-size:9px;color:#888;letter-spacing:0.15em;text-transform:uppercase;">Grade A+B</div>
        <div style="font-family:Georgia,serif;font-size:24px;font-weight:300;color:#fff;margin-top:3px;">{grade_a + grade_b}</div>
        <div style="font-size:9px;color:#666;margin-top:1px;">A:{grade_a} B:{grade_b}</div>
      </td>
    </tr>
  </table>

  <!-- Market context -->
  <div style="padding:14px 28px;background:#080808;border-bottom:1px solid #1f1f1f;font-size:11px;color:#888;letter-spacing:0.05em;">
    Benchmark: <span style="color:#fff;">SPY 1Y</span> <span style="color:{'#00d68f' if spy_ret >= 0 else '#ff4444'};">{spy_ret:+.1f}%</span>
    &nbsp;·&nbsp; RS Rating = percentile rank (0–99)
    &nbsp;·&nbsp; Pivot = last major peak before final contraction
  </div>

  {report_link_html}

  {watchlist_html}

  {super_html}

  {perfect_html}

  {leader_html}

  <!-- TOP 20 -->
  <div style="padding:28px 28px 8px;">
    <h2 style="font-family:Georgia,serif;font-size:20px;font-weight:400;color:#fff;margin:0 0 4px;">
      Top 20 by Minervini Score
    </h2>
    <p style="font-size:11px;color:#888;margin:0 0 16px;letter-spacing:0.05em;">
      Composite score: trend template + RS rating + VCP pattern
    </p>
  </div>
  
  <table style="width:100%;border-collapse:collapse;background:#0a0a0a;">
    <thead>
      <tr style="background:#000;">
        <th style="padding:10px 10px;text-align:left;font-size:9px;color:#666;letter-spacing:0.15em;text-transform:uppercase;font-weight:500;border-bottom:1px solid #2a2a2a;">#</th>
        <th style="padding:10px 10px;text-align:left;font-size:9px;color:#666;letter-spacing:0.15em;text-transform:uppercase;font-weight:500;border-bottom:1px solid #2a2a2a;">Ticker</th>
        <th style="padding:10px 8px;text-align:right;font-size:9px;color:#666;letter-spacing:0.15em;text-transform:uppercase;font-weight:500;border-bottom:1px solid #2a2a2a;">Score</th>
        <th style="padding:10px 6px;text-align:center;font-size:9px;color:#666;letter-spacing:0.15em;text-transform:uppercase;font-weight:500;border-bottom:1px solid #2a2a2a;">Criteria</th>
        <th style="padding:10px 6px;text-align:center;font-size:9px;color:#666;letter-spacing:0.15em;text-transform:uppercase;font-weight:500;border-bottom:1px solid #2a2a2a;">RS</th>
        <th style="padding:10px 6px;text-align:center;font-size:9px;color:#666;letter-spacing:0.15em;text-transform:uppercase;font-weight:500;border-bottom:1px solid #2a2a2a;">Fund</th>
        <th style="padding:10px 8px;text-align:right;font-size:9px;color:#666;letter-spacing:0.15em;text-transform:uppercase;font-weight:500;border-bottom:1px solid #2a2a2a;">Price</th>
        <th style="padding:10px 6px;text-align:right;font-size:9px;color:#666;letter-spacing:0.15em;text-transform:uppercase;font-weight:500;border-bottom:1px solid #2a2a2a;">1Y</th>
        <th style="padding:10px 8px;text-align:right;font-size:9px;color:#666;letter-spacing:0.15em;text-transform:uppercase;font-weight:500;border-bottom:1px solid #2a2a2a;">Trend</th>
        <th style="padding:10px 8px;text-align:left;font-size:9px;color:#666;letter-spacing:0.15em;text-transform:uppercase;font-weight:500;border-bottom:1px solid #2a2a2a;">Setup</th>
      </tr>
    </thead>
    <tbody>{top_rows}</tbody>
  </table>

  <!-- Two columns: True VCP + Breakout Watch -->
  <table style="width:100%;border-collapse:collapse;margin-top:32px;background:#0a0a0a;">
    <tr>
      <td style="width:50%;padding:20px 14px 20px 28px;vertical-align:top;border-right:1px solid #1f1f1f;">
        <h3 style="font-family:Georgia,serif;font-size:15px;font-weight:400;color:#d4ff00;margin:0 0 4px;">
          🎯 True VCP Patterns
        </h3>
        <p style="font-size:10px;color:#666;margin:0 0 14px;">Contractions tightening · volume drying</p>
        <table style="width:100%;border-collapse:collapse;">
          <tr style="background:#000;">
            <td style="padding:6px 8px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;">Ticker</td>
            <td style="padding:6px 8px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;">Name</td>
            <td style="padding:6px 8px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;text-align:right;">Depths</td>
            <td style="padding:6px 8px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;text-align:right;">Pivot</td>
          </tr>
          {vcp_html if vcp_html else '<tr><td colspan="4" style="color:#555;font-size:11px;padding:12px 8px;">No new patterns today</td></tr>'}
        </table>
      </td>
      <td style="width:50%;padding:20px 28px 20px 14px;vertical-align:top;">
        <h3 style="font-family:Georgia,serif;font-size:15px;font-weight:400;color:#ffaa00;margin:0 0 4px;">
          ⚡ Breakout Watch
        </h3>
        <p style="font-size:10px;color:#666;margin:0 0 14px;">≤3% from 52W high · 7+/8 criteria</p>
        <table style="width:100%;border-collapse:collapse;">
          <tr style="background:#000;">
            <td style="padding:6px 8px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;">Ticker</td>
            <td style="padding:6px 8px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;">Name</td>
            <td style="padding:6px 8px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;text-align:right;">From High</td>
            <td style="padding:6px 8px;font-size:8px;color:#666;letter-spacing:0.15em;text-transform:uppercase;text-align:right;">Price</td>
          </tr>
          {breakout_html if breakout_html else '<tr><td colspan="4" style="color:#555;font-size:11px;padding:12px 8px;">No candidates today</td></tr>'}
        </table>
      </td>
    </tr>
  </table>

  <!-- Sector breakdown -->
  <div style="padding:32px 28px;border-top:1px solid #1f1f1f;margin-top:12px;">
    <h3 style="font-family:Georgia,serif;font-size:15px;font-weight:400;color:#fff;margin:0 0 16px;">
      📊 Top 50 · Sector Concentration
    </h3>
    {sector_html}
  </div>

  <!-- Methodology -->
  <div style="padding:20px 28px;background:#080808;border-top:1px solid #1f1f1f;font-size:10px;color:#666;line-height:1.7;">
    <strong style="color:#888;">Methodology:</strong> Minervini SEPA — 8-criteria trend template + true VCP + fundamental leader profile<br>
    <strong style="color:#888;">Trend:</strong> Price>MA150/200, MA150>MA200, MA200↑, MA50>MA150/200, Price>MA50, Price≥30% above 52W low, Price≤25% from 52W high, RS≥70<br>
    <strong style="color:#888;">True VCP:</strong> ≥2 consecutive contractions · depths tightening · final &lt;15% · volume drying · near pivot<br>
    <strong style="color:#888;">Leader Profile:</strong> EPS YoY ≥25% · EPS accelerating · Revenue growing · ROE ≥17% · margins expanding<br>
    <strong style="color:#00ff9d;">★★ Super Stock:</strong> Perfect technical (VCP + 8/8 + near pivot) <b>AND</b> Leader Profile — Minervini's strongest signal combination
  </div>

  <!-- Footer -->
  <div style="padding:24px 28px;text-align:center;border-top:1px solid #1f1f1f;">
    <div style="font-size:10px;color:#555;letter-spacing:0.1em;">
      This is a research tool. Not investment advice.<br>
      Based on Mark Minervini's SEPA methodology from <em>Trade Like a Stock Market Wizard</em>.
    </div>
  </div>

</div>

</body>
</html>'''
    return html


def send_email(html_content, subject):
    """发送邮件"""
    smtp_host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_user = os.environ['SMTP_USER']
    smtp_pass = os.environ['SMTP_PASS']
    email_from = os.environ.get('EMAIL_FROM', smtp_user)
    email_to = os.environ['EMAIL_TO']
    
    recipients = [e.strip() for e in email_to.split(',')]
    
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = email_from
    msg['To'] = ', '.join(recipients)
    
    # 纯文本fallback
    text_part = MIMEText("Please view this email in an HTML-capable client.", 'plain')
    html_part = MIMEText(html_content, 'html')
    msg.attach(text_part)
    msg.attach(html_part)
    
    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls(context=context)
        server.login(smtp_user, smtp_pass)
        server.sendmail(email_from, recipients, msg.as_string())
    
    print(f"✓ Email sent to {len(recipients)} recipient(s)")


def main():
    report = load_report()
    report_url = os.environ.get('REPORT_URL', None)
    
    html = render_email(report, report_url=report_url)
    
    # 保存预览
    with open('reports/email_preview.html', 'w') as f:
        f.write(html)
    print(f"Email preview saved to reports/email_preview.html")
    
    # 检测环境变量
    if not os.environ.get('SMTP_USER') or not os.environ.get('SMTP_PASS'):
        print("⚠ SMTP credentials not set — skipping actual send (preview only)")
        print("  Required env vars: SMTP_USER, SMTP_PASS, EMAIL_TO")
        return
    
    # 统计
    top = sorted(report['stocks'], key=lambda x: x['minervini_score'], reverse=True)[:3]
    top_str = ' · '.join([s['ticker'] for s in top])
    perfect = report.get('perfect_setup_count', 0)
    true_vcp = report.get('true_vcp_count', 0)
    super_ct = report.get('super_stock_count', 0)
    
    # 标题根据发现的信号强度动态生成 (Super优先)
    if super_ct > 0:
        subject = f"★★ {super_ct} Super Stock{'s' if super_ct > 1 else ''} · Minervini {report['date']} · {top_str}"
    elif perfect > 0:
        subject = f"★ {perfect} Perfect Setup{'s' if perfect > 1 else ''} · Minervini {report['date']} · {top_str}"
    elif true_vcp > 0:
        subject = f"🎯 {true_vcp} VCP Patterns · Minervini {report['date']} · {top_str}"
    else:
        subject = f"📈 Minervini {report['date']} · {report['all_8_passed_count']} qualifiers · {top_str}"
    
    send_email(html, subject)


if __name__ == '__main__':
    main()
