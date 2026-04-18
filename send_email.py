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
    spy_ret = report['spy_return_1y']
    
    stocks = sorted(report['stocks'], key=lambda x: x['minervini_score'], reverse=True)
    top20 = stocks[:20]
    
    # === 三个精选列表 ===
    # Perfect Setup: 真VCP + 8/8通过 + 接近pivot (最高优先级)
    perfect_setups = [s for s in stocks 
                      if s.get('vcp', {}).get('has_vcp') 
                      and s['all_8_passed']
                      and s.get('vcp', {}).get('near_pivot')][:8]
    
    # True VCP (不满足perfect但识别到真VCP)
    true_vcp_list = [s for s in stocks 
                     if s.get('vcp', {}).get('has_vcp') 
                     and s not in perfect_setups][:8]
    
    # Breakout watch: 距52周高点≤3% + 至少7条通过
    breakout_watch = [s for s in stocks 
                      if s['pct_from_high'] > -3 
                      and s['criteria_passed'] >= 7
                      and s not in perfect_setups][:8]
    
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
    
    # === Perfect Setup 专区 (最显眼) ===
    perfect_html = ''
    if perfect_setups:
        rows = ''
        for s in perfect_setups:
            v = s.get('vcp', {})
            depths = [c['depth_pct'] for c in v.get('contractions', [])[-4:]]
            depths_str = ' → '.join([f'{d:.1f}%' for d in depths])
            current = s['price']
            pivot = v.get('pivot_price', 0)
            dist_to_pivot = ((pivot - current) / pivot * 100) if pivot else 0
            pivot_status = 'ABOVE' if current >= pivot else f'{dist_to_pivot:.1f}% below'
            pivot_color = '#d4ff00' if current >= pivot else '#ffaa00'
            
            rows += f'''
            <tr style="border-bottom:1px solid #1f1f1f;">
              <td style="padding:14px 12px;vertical-align:top;">
                <div style="color:#d4ff00;font-weight:700;font-size:14px;letter-spacing:0.02em;">{s['ticker']}</div>
                <div style="color:#888;font-size:10px;margin-top:2px;">{s['name'][:32]}</div>
                <div style="color:#666;font-size:9px;margin-top:4px;letter-spacing:0.05em;text-transform:uppercase;">{s['sector'][:18]}</div>
              </td>
              <td style="padding:14px 12px;text-align:right;vertical-align:top;">
                <div style="font-family:Georgia,serif;font-size:20px;color:#d4ff00;font-weight:600;">{s['minervini_score']}</div>
                <div style="color:#666;font-size:9px;letter-spacing:0.1em;text-transform:uppercase;margin-top:2px;">score</div>
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
            True VCP identified · 8/8 trend template · Price at or near pivot point → <b style="color:#d4ff00;">highest-priority watchlist</b>
          </p>
          <table style="width:100%;border-collapse:collapse;">{rows}</table>
        </div>'''
    
    # === Top 20 表格行 ===
    top_rows = ''
    for i, s in enumerate(top20):
        dots = criteria_dots(s['criteria'])
        spark = mini_sparkline(s['price_history'])
        ret_color = '#00d68f' if s['return_1y'] >= 0 else '#ff4444'
        rs_color = '#d4ff00' if s['rs_rating'] >= 90 else '#ffaa00' if s['rs_rating'] >= 70 else '#888'
        
        v = s.get('vcp', {})
        setup_tags = []
        if v.get('has_vcp'):
            setup_tags.append('<span style="display:inline-block;background:rgba(212,255,0,0.2);color:#d4ff00;padding:2px 6px;font-size:9px;letter-spacing:0.05em;font-weight:600;margin-right:3px;">★VCP</span>')
        elif s.get('volatility_contraction'):
            setup_tags.append('<span style="display:inline-block;background:rgba(212,255,0,0.1);color:#9ab800;padding:2px 6px;font-size:9px;letter-spacing:0.05em;margin-right:3px;">atr</span>')
        if v.get('near_pivot'):
            setup_tags.append('<span style="display:inline-block;background:rgba(255,170,0,0.2);color:#ffaa00;padding:2px 6px;font-size:9px;letter-spacing:0.05em;margin-right:3px;">PIVOT</span>')
        if s.get('volume_drying'):
            setup_tags.append('<span style="display:inline-block;background:rgba(0,214,143,0.15);color:#00d68f;padding:2px 6px;font-size:9px;letter-spacing:0.05em;">VOL↓</span>')
        if s['pct_from_high'] > -3:
            setup_tags.append('<span style="display:inline-block;background:rgba(255,170,0,0.12);color:#ffaa00;padding:2px 6px;font-size:9px;letter-spacing:0.05em;margin-left:3px;">HIGH</span>')
        setup_html = ''.join(setup_tags) or '<span style="color:#555;font-size:10px;">—</span>'
        
        bg = '#0f0f0f' if i % 2 == 0 else '#141414'
        
        top_rows += f'''
        <tr style="background:{bg};">
          <td style="padding:10px 12px;color:#555;font-size:11px;width:24px;">{i+1}</td>
          <td style="padding:10px 12px;">
            <div style="color:#fff;font-weight:700;font-size:13px;letter-spacing:0.02em;">{s['ticker']}</div>
            <div style="color:#888;font-size:10px;margin-top:2px;">{s['name'][:28]}</div>
          </td>
          <td style="padding:10px 12px;text-align:right;">
            <div style="color:#d4ff00;font-weight:700;font-size:15px;font-family:Georgia,serif;">{s['minervini_score']}</div>
          </td>
          <td style="padding:10px 12px;text-align:center;">
            <div>{dots}</div>
            <div style="color:#555;font-size:10px;margin-top:3px;">{s['criteria_passed']}/8</div>
          </td>
          <td style="padding:10px 12px;text-align:center;">
            <span style="color:{rs_color};border:1px solid {rs_color};padding:2px 8px;font-size:11px;font-weight:500;">{int(s['rs_rating'])}</span>
          </td>
          <td style="padding:10px 12px;text-align:right;color:#fff;font-family:monospace;">${s['price']:.2f}</td>
          <td style="padding:10px 12px;text-align:right;color:{ret_color};font-family:monospace;font-weight:500;">{'+' if s['return_1y']>=0 else ''}{s['return_1y']:.1f}%</td>
          <td style="padding:10px 12px;text-align:right;">{spark}</td>
          <td style="padding:10px 12px;">{setup_html}</td>
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

  <!-- Summary stats (5列新版) -->
  <table style="width:100%;border-collapse:collapse;background:#0a0a0a;">
    <tr>
      <td style="padding:18px 12px;border-right:1px solid #1f1f1f;border-bottom:1px solid #1f1f1f;width:20%;">
        <div style="font-size:9px;color:#888;letter-spacing:0.15em;text-transform:uppercase;">Universe</div>
        <div style="font-family:Georgia,serif;font-size:26px;font-weight:300;color:#d4ff00;margin-top:4px;">{total}</div>
        <div style="font-size:10px;color:#666;margin-top:2px;">scanned</div>
      </td>
      <td style="padding:18px 12px;border-right:1px solid #1f1f1f;border-bottom:1px solid #1f1f1f;width:20%;">
        <div style="font-size:9px;color:#888;letter-spacing:0.15em;text-transform:uppercase;">8/8 Pass</div>
        <div style="font-family:Georgia,serif;font-size:26px;font-weight:300;color:#fff;margin-top:4px;">{pass8}</div>
        <div style="font-size:10px;color:#666;margin-top:2px;">qualifiers</div>
      </td>
      <td style="padding:18px 12px;border-right:1px solid #1f1f1f;border-bottom:1px solid #1f1f1f;width:20%;background:{('linear-gradient(135deg, rgba(212,255,0,0.05), transparent)' if perfect > 0 else '#0a0a0a')};">
        <div style="font-size:9px;color:#d4ff00;letter-spacing:0.15em;text-transform:uppercase;font-weight:600;">★ Perfect</div>
        <div style="font-family:Georgia,serif;font-size:26px;font-weight:400;color:#d4ff00;margin-top:4px;">{perfect}</div>
        <div style="font-size:10px;color:#d4ff00;margin-top:2px;">top priority</div>
      </td>
      <td style="padding:18px 12px;border-right:1px solid #1f1f1f;border-bottom:1px solid #1f1f1f;width:20%;">
        <div style="font-size:9px;color:#888;letter-spacing:0.15em;text-transform:uppercase;">True VCP</div>
        <div style="font-family:Georgia,serif;font-size:26px;font-weight:300;color:#fff;margin-top:4px;">{true_vcp}</div>
        <div style="font-size:10px;color:#666;margin-top:2px;">pattern match</div>
      </td>
      <td style="padding:18px 12px;border-bottom:1px solid #1f1f1f;width:20%;">
        <div style="font-size:9px;color:#888;letter-spacing:0.15em;text-transform:uppercase;">Near Pivot</div>
        <div style="font-family:Georgia,serif;font-size:26px;font-weight:300;color:#ffaa00;margin-top:4px;">{near_pivot}</div>
        <div style="font-size:10px;color:#666;margin-top:2px;">breakout zone</div>
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

  {perfect_html}

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
        <th style="padding:10px 12px;text-align:left;font-size:9px;color:#666;letter-spacing:0.15em;text-transform:uppercase;font-weight:500;border-bottom:1px solid #2a2a2a;">#</th>
        <th style="padding:10px 12px;text-align:left;font-size:9px;color:#666;letter-spacing:0.15em;text-transform:uppercase;font-weight:500;border-bottom:1px solid #2a2a2a;">Ticker</th>
        <th style="padding:10px 12px;text-align:right;font-size:9px;color:#666;letter-spacing:0.15em;text-transform:uppercase;font-weight:500;border-bottom:1px solid #2a2a2a;">Score</th>
        <th style="padding:10px 12px;text-align:center;font-size:9px;color:#666;letter-spacing:0.15em;text-transform:uppercase;font-weight:500;border-bottom:1px solid #2a2a2a;">Criteria</th>
        <th style="padding:10px 12px;text-align:center;font-size:9px;color:#666;letter-spacing:0.15em;text-transform:uppercase;font-weight:500;border-bottom:1px solid #2a2a2a;">RS</th>
        <th style="padding:10px 12px;text-align:right;font-size:9px;color:#666;letter-spacing:0.15em;text-transform:uppercase;font-weight:500;border-bottom:1px solid #2a2a2a;">Price</th>
        <th style="padding:10px 12px;text-align:right;font-size:9px;color:#666;letter-spacing:0.15em;text-transform:uppercase;font-weight:500;border-bottom:1px solid #2a2a2a;">1Y</th>
        <th style="padding:10px 12px;text-align:right;font-size:9px;color:#666;letter-spacing:0.15em;text-transform:uppercase;font-weight:500;border-bottom:1px solid #2a2a2a;">Trend</th>
        <th style="padding:10px 12px;text-align:left;font-size:9px;color:#666;letter-spacing:0.15em;text-transform:uppercase;font-weight:500;border-bottom:1px solid #2a2a2a;">Setup</th>
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
    <strong style="color:#888;">Methodology:</strong> Minervini 8-criteria trend template + true VCP detection<br>
    <strong style="color:#888;">Trend:</strong> Price>MA150/200, MA150>MA200, MA200↑, MA50>MA150/200, Price>MA50, Price≥30% above 52W low, Price≤25% from 52W high, RS≥70<br>
    <strong style="color:#888;">True VCP:</strong> ≥2 consecutive contractions · depths tightening · final contraction &lt;15% · volume drying · near pivot point
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
    
    # 标题根据发现的信号强度动态生成
    if perfect > 0:
        subject = f"★ {perfect} Perfect Setup{'s' if perfect > 1 else ''} · Minervini {report['date']} · {top_str}"
    elif true_vcp > 0:
        subject = f"🎯 {true_vcp} VCP Patterns · Minervini {report['date']} · {top_str}"
    else:
        subject = f"📈 Minervini {report['date']} · {report['all_8_passed_count']} qualifiers · {top_str}"
    
    send_email(html, subject)


if __name__ == '__main__':
    main()
