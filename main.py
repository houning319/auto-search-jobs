#!/usr/bin/env python3
"""
国企招聘信息每日自动搜索 & 邮件推送
每天自动搜索国企招聘（重点外派越南），汇总后发送至指定邮箱
"""

import anthropic
import smtplib
import json
import logging
import re
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config

# ── 日志配置 ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("job_alert.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


# ── 日期过滤（核心：Python 硬性剔除旧数据）─────────────────────────────────────
def parse_publish_date(date_str: str) -> datetime | None:
    """尝试解析各种格式的中文/英文日期字符串"""
    if not date_str:
        return None
    # 常见格式列表
    patterns = [
        (r"(\d{4})年(\d{1,2})月(\d{1,2})日", "%Y%m%d"),
        (r"(\d{4})-(\d{1,2})-(\d{1,2})", "%Y%m%d"),
        (r"(\d{4})/(\d{1,2})/(\d{1,2})", "%Y%m%d"),
        (r"(\d{4})\.(\d{1,2})\.(\d{1,2})", "%Y%m%d"),
    ]
    for pattern, _ in patterns:
        m = re.search(pattern, date_str)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
    return None


def filter_recent_jobs(jobs: list[dict], days: int = 35) -> tuple[list[dict], list[dict]]:
    """
    将职位分为两组：
      recent  — 发布日期在 days 天内，或日期解析失败（保留但标注）
      outdated — 明确是 days 天之前的旧数据
    返回 (recent, outdated)
    """
    cutoff = datetime.now() - timedelta(days=days)
    recent, outdated = [], []
    for job in jobs:
        dt = parse_publish_date(job.get("publish_date", ""))
        if dt is None:
            # 日期未知：保留但打上标记，邮件里显示"日期未知"
            job["publish_date"] = ""
            job["date_unknown"] = True
            recent.append(job)
        elif dt >= cutoff:
            job["date_unknown"] = False
            recent.append(job)
        else:
            outdated.append(job)
    return recent, outdated


def search_jobs() -> tuple[list[dict], dict]:
    """调用 Claude API（联网搜索）获取最新国企招聘信息，同时返回搜索覆盖情况"""
    log.info("开始搜索国企招聘信息...")
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    today = datetime.now().strftime("%Y年%m月%d日")
    one_month_ago = datetime.now().replace(day=1).strftime("%Y年%m月%d日")
    year = datetime.now().year
    month = datetime.now().month

    # 搜索方向定义（用于覆盖率报告）
    search_directions = {
        "D01": "平台·智联招聘 国企越南外派",
        "D02": "平台·前程无忧 央企越南",
        "D03": "平台·猎聘 国企海外越南",
        "D04": "平台·BOSS直聘 国企外派越南",
        "D05": "企业·招商局/中远海运/中外运/航运物流",
        "D06": "企业·中交/电建/中铁建/中建 越南",
        "D07": "企业·国家电网/南方电网/中国能建 越南",
        "D08": "企业·中行/工行/建行/农行 越南分行",
        "D09": "企业·华为/中兴/中国移动/电信 越南",
        "D10": "地点·越南河内/胡志明市/海防",
        "D11": "地点·央企越南工程项目外派",
        "D12": "行业·能源电力国企越南",
        "D13": "行业·建筑工程央企越南EPC",
        "D14": "行业·交通运输国企越南",
        "D15": "行业·制造业国企越南工厂",
    }

    prompt = f"""今天是{today}。请通过网络搜索【最近一个月内（{one_month_ago}之后发布）】的中国国有企业招聘信息。
⚠️ 只收录{one_month_ago}之后发布的职位，过期或日期不明的排除。

请按以下15个方向逐一搜索，并记录每个方向是否找到有效结果：

【平台定向搜索】
D01. site:zhaopin.com 国企 越南 外派 {year}
D02. site:51job.com 央企 越南 {year}
D03. site:liepin.com 国企 海外 越南 {year}
D04. site:boss.zhipin.com 国企 外派越南 {year}

【企业定向搜索】
D05. （招商局 OR 中远海运 OR 中外运 OR 航运 OR 物流 OR 船公司）越南 招聘 {year}年{month}月
D06. （中交股份 OR 中国电建 OR 中铁建 OR 中建集团）越南 招聘 {year}年{month}月
D07. （国家电网 OR 南方电网 OR 中国能建）越南 外派 {year}
D08. （中国银行 OR 工商银行 OR 建设银行 OR 农业银行）越南 分行 招聘 {year}
D09. （华为 OR 中兴通讯 OR 中国移动 OR 中国电信）越南 招聘 {year}

【地点定向搜索】
D10. 国企 招聘 越南 （河内 OR 胡志明市 OR 海防）{year}年
D11. 央企 越南 工程项目 外派 {year}年{month}月

【行业定向搜索】
D12. 能源电力 国企 越南 招聘 最新 {year}
D13. 建筑工程 央企 越南EPC项目 招聘 {year}
D14. 交通运输 国企 越南 外派 {year}
D15. 制造业 国企 越南 工厂 招聘 {year}

搜索完毕后，请汇总所有结果，整理成招聘信息列表。"""

    # 第一步：联网搜索
    log.info("第一步：联网搜索招聘信息...")
    search_response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )

    search_text = ""
    for block in search_response.content:
        if hasattr(block, "type") and block.type == "text":
            search_text += block.text

    if not search_text.strip():
        log.warning("第一步搜索无返回文本")
        return [], {d: False for d in search_directions}

    log.info(f"第一步完成，获取到 {len(search_text)} 字符的搜索结果")

    # 第二步：格式化为结构化 JSON（含职位列表 + 搜索覆盖情况）
    log.info("第二步：格式化为 JSON...")
    format_prompt = f"""请将以下国企招聘搜索结果整理为结构化JSON。

只输出一个JSON对象，不要任何说明文字，不要```代码块标记，格式如下：
{{
  "jobs": [
    {{
      "title": "职位名称",
      "company": "企业全称",
      "company_short": "简称",
      "location": "工作地点",
      "industry": "能源电力|建筑工程|通信科技|金融银行|交通物流|制造业|其他（只能选其一）",
      "vietnam": true,
      "publish_date": "发布日期如2026年3月20日，不确定填空字符串",
      "salary": "薪资或空字符串",
      "requirements": "主要要求30字内",
      "deadline": "截止日期或空字符串",
      "source": "来源平台",
      "url": "链接或空字符串",
      "hot": false,
      "desc": "职位简介40字内",
      "search_direction": "来自哪个搜索方向，如D05或D12"
    }}
  ],
  "coverage": {{
    "D01": true,
    "D02": false,
    "D03": true,
    "D04": false,
    "D05": true,
    "D06": true,
    "D07": false,
    "D08": true,
    "D09": false,
    "D10": true,
    "D11": true,
    "D12": false,
    "D13": true,
    "D14": false,
    "D15": true
  }}
}}

说明：
- jobs：只保留{one_month_ago}之后发布的职位，过期排除
- coverage：每个方向true=找到有效结果，false=无结果或全是旧数据
- search_direction：每条职位标注来自哪个搜索方向编号

原始搜索结果：
{search_text[:6000]}

输出第一个字符必须是 {{"""

    format_response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        messages=[{"role": "user", "content": format_prompt}],
    )

    raw_text = ""
    for block in format_response.content:
        if hasattr(block, "type") and block.type == "text":
            raw_text += block.text

    log.info(f"第二步返回内容前150字符：{raw_text[:150]}")

    # 解析 JSON 对象
    raw_text = raw_text.strip().replace("```json", "").replace("```", "").strip()
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1:
        log.warning(f"未找到JSON对象，内容：{raw_text[:200]}")
        return [], {d: False for d in search_directions}

    parsed = json.loads(raw_text[start : end + 1])
    jobs = parsed.get("jobs", [])
    coverage_raw = parsed.get("coverage", {})

    # 合并覆盖情况，补充描述文字
    coverage = {
        code: {"label": label, "found": bool(coverage_raw.get(code, False))}
        for code, label in search_directions.items()
    }

    log.info(f"API 原始返回 {len(jobs)} 条职位")
    hit_count = sum(1 for v in coverage.values() if v["found"])
    log.info(f"搜索覆盖：{hit_count}/15 个方向有结果")

    # Python 硬性过滤旧数据
    jobs, outdated = filter_recent_jobs(jobs, days=35)
    log.info(f"过滤旧数据 {len(outdated)} 条，保留 {len(jobs)} 条")
    if outdated:
        log.info("被过滤：" + ", ".join(
            f"{j.get('title','?')}({j.get('publish_date','?')})" for j in outdated
        ))

    log.info(f"最终：{len(jobs)} 条，越南外派 {sum(1 for j in jobs if j.get('vietnam'))} 条")
    return jobs, coverage


# ── 2. 生成 HTML 邮件内容 ──────────────────────────────────────────────────────
def build_html_email(jobs: list[dict], coverage: dict) -> str:
    """将职位列表渲染为精美 HTML 邮件"""
    today_str = datetime.now().strftime("%Y年%m月%d日")
    vn_jobs = [j for j in jobs if j.get("vietnam")]
    other_jobs = [j for j in jobs if not j.get("vietnam")]

    industries = {
        "能源电力": "#1D9E75", "建筑工程": "#378ADD", "通信科技": "#7F77DD",
        "金融银行": "#D4537E", "交通物流": "#BA7517", "制造业": "#639922", "其他": "#888780",
    }

    def job_card(job: dict, highlight: bool = False) -> str:
        ind_color = industries.get(job.get("industry", "其他"), "#888780")
        border = f"border-left: 4px solid {ind_color};" if highlight else ""
        if job.get("date_unknown"):
            date_str = '<span style="font-size:11px;color:#BA7517;background:#FAEEDA;padding:1px 6px;border-radius:3px;margin-left:6px;">发布日期未知</span>'
        elif job.get("publish_date"):
            date_str = f'<span style="font-size:11px;color:#aaa;margin-left:6px;">发布：{job["publish_date"]}</span>'
        else:
            date_str = ""
        vn_badge = '<span style="background:#E1F5EE;color:#0F6E56;font-size:11px;padding:2px 8px;border-radius:4px;margin-left:6px;font-weight:600;">外派越南</span>' if job.get("vietnam") else ""
        hot_badge = '<span style="background:#FCEBEB;color:#A32D2D;font-size:11px;padding:2px 8px;border-radius:4px;margin-left:4px;">热招</span>' if job.get("hot") else ""
        salary_str = f'<span style="color:#1D9E75;font-weight:600;">{job["salary"]}</span> · ' if job.get("salary") else ""
        url_str = f'<a href="{job["url"]}" style="color:#378ADD;font-size:12px;text-decoration:none;">查看详情 →</a>' if job.get("url") else ""
        return f"""
        <div style="background:#fff;border-radius:8px;padding:14px 16px;margin-bottom:10px;{border}box-shadow:0 1px 4px rgba(0,0,0,0.06);">
          <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:4px;">
            <div>
              <span style="font-size:15px;font-weight:600;color:#1a1a1a;">{job.get('title','—')}</span>
              {vn_badge}{hot_badge}{date_str}
            </div>
            <span style="font-size:11px;background:{ind_color}1a;color:{ind_color};padding:2px 8px;border-radius:4px;font-weight:500;">{job.get('industry','—')}</span>
          </div>
          <div style="margin-top:6px;font-size:13px;color:#555;">
            🏢 {job.get('company_short') or job.get('company','—')} &nbsp;·&nbsp; 📍 {job.get('location','—')}
          </div>
          <div style="margin-top:5px;font-size:13px;color:#444;">
            {salary_str}{job.get('desc','—')}
          </div>
          <div style="margin-top:6px;font-size:12px;color:#888;display:flex;gap:12px;flex-wrap:wrap;">
            {f'要求：{job["requirements"]}' if job.get("requirements") else ""}
            {f'截止：{job["deadline"]}' if job.get("deadline") else ""}
            {f'来源：{job["source"]}' if job.get("source") else ""}
          </div>
          {f'<div style="margin-top:6px;">{url_str}</div>' if url_str else ""}
        </div>"""

    vn_section = "".join(job_card(j, highlight=True) for j in vn_jobs) if vn_jobs else \
        '<p style="color:#888;font-size:14px;padding:12px;">今日暂无外派越南相关职位，明日继续关注。</p>'
    # 按行业分组
    industry_order = ["能源电力", "建筑工程", "通信科技", "金融银行", "交通物流", "制造业", "其他"]
    industry_groups = {}
    for j in other_jobs:
        ind = j.get("industry", "其他")
        industry_groups.setdefault(ind, []).append(j)

    industry_sections = ""
    for ind in industry_order:
        group = industry_groups.get(ind, [])
        if not group:
            continue
        color = industries.get(ind, "#888780")
        industry_sections += f"""
        <div style="margin-bottom:6px;">
          <div style="font-size:12px;font-weight:600;color:{color};padding:6px 0 8px;border-bottom:1px solid #f0f0f0;margin-bottom:8px;">
            ▌ {ind}（{len(group)} 条）
          </div>
          {"".join(job_card(j) for j in group)}
        </div>"""

    # 搜索覆盖率区块
    hit = sum(1 for v in coverage.values() if v["found"])
    total = len(coverage)
    pct = round(hit / total * 100) if total else 0

    def cov_row(code: str, info: dict) -> str:
        found = info["found"]
        icon = "✓" if found else "—"
        bg = "#E1F5EE" if found else "#F5F4F0"
        color = "#0F6E56" if found else "#aaa"
        return (
            f'<tr>'
            f'<td style="padding:5px 8px;font-size:12px;color:#555;border-bottom:0.5px solid #f0f0f0;">'
            f'<span style="font-family:monospace;font-size:11px;color:#aaa;margin-right:6px;">{code}</span>'
            f'{info["label"]}</td>'
            f'<td style="padding:5px 8px;text-align:center;border-bottom:0.5px solid #f0f0f0;">'
            f'<span style="background:{bg};color:{color};font-size:11px;padding:2px 8px;border-radius:4px;font-weight:600;">{icon}</span>'
            f'</td></tr>'
        )

    coverage_rows = "".join(cov_row(k, v) for k, v in coverage.items())
    coverage_section = f"""
    <div style="background:#fff;padding:20px 20px 16px;margin-top:2px;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
        <div style="font-size:14px;font-weight:600;color:#333;">📡 搜索覆盖报告</div>
        <div style="font-size:13px;">
          <span style="color:#1D9E75;font-weight:600;">{hit}</span>
          <span style="color:#aaa;">/{total} 个方向有结果（{pct}%）</span>
        </div>
      </div>
      <table style="width:100%;border-collapse:collapse;">
        <thead>
          <tr style="background:#F5F4F0;">
            <th style="padding:6px 8px;font-size:11px;color:#888;text-align:left;font-weight:500;">搜索方向</th>
            <th style="padding:6px 8px;font-size:11px;color:#888;text-align:center;font-weight:500;width:60px;">结果</th>
          </tr>
        </thead>
        <tbody>{coverage_rows}</tbody>
      </table>
      <div style="margin-top:10px;font-size:11px;color:#bbb;">
        ✓ = 找到有效职位 &nbsp;|&nbsp; — = 无结果或全为旧数据
      </div>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#F5F4F0;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;">
  <div style="max-width:640px;margin:0 auto;padding:20px 12px;">

    <!-- 头部 -->
    <div style="background:#1a1a1a;border-radius:12px 12px 0 0;padding:24px 24px 20px;">
      <div style="color:#fff;font-size:20px;font-weight:600;">国企招聘日报</div>
      <div style="color:#aaa;font-size:13px;margin-top:4px;">{today_str} · 每日早8点自动推送</div>
      <div style="display:flex;gap:16px;margin-top:16px;">
        <div style="text-align:center;">
          <div style="color:#5DCAA5;font-size:24px;font-weight:700;">{len(vn_jobs)}</div>
          <div style="color:#888;font-size:11px;">外派越南</div>
        </div>
        <div style="text-align:center;">
          <div style="color:#fff;font-size:24px;font-weight:700;">{len(jobs)}</div>
          <div style="color:#888;font-size:11px;">职位总数</div>
        </div>
        <div style="text-align:center;">
          <div style="color:#85B7EB;font-size:24px;font-weight:700;">{len({{j.get('company_short') or j.get('company') for j in jobs}})}</div>
          <div style="color:#888;font-size:11px;">招聘企业</div>
        </div>
        <div style="text-align:center;">
          <div style="color:#FAC775;font-size:24px;font-weight:700;">{hit}/{total}</div>
          <div style="color:#888;font-size:11px;">搜索命中</div>
        </div>
      </div>
    </div>

    <!-- 越南专区 -->
    <div style="background:#fff;padding:20px 20px 10px;border-top:3px solid #1D9E75;">
      <div style="font-size:14px;font-weight:600;color:#0F6E56;margin-bottom:12px;">
        🌏 外派越南专项职位（{len(vn_jobs)} 条）
      </div>
      {vn_section}
    </div>

    <!-- 行业分类 -->
    <div style="background:#fff;padding:20px 20px 10px;margin-top:2px;">
      <div style="font-size:14px;font-weight:600;color:#333;margin-bottom:12px;">
        📋 按行业分类（{len(other_jobs)} 条）
      </div>
      {industry_sections}
    </div>

    <!-- 搜索覆盖报告 -->
    {coverage_section}

    <!-- 底部 -->
    <div style="background:#F5F4F0;padding:16px;text-align:center;border-radius:0 0 8px 8px;">
      <div style="font-size:11px;color:#999;">本邮件由自动化脚本生成 · 数据来源于公开招聘网站</div>
      <div style="font-size:11px;color:#bbb;margin-top:4px;">如需退订请回复"退订"</div>
    </div>

  </div>
</body>
</html>"""


# ── 3. 发送邮件 ────────────────────────────────────────────────────────────────
def send_email(html_content: str, job_count: int, vn_count: int) -> bool:
    """通过 SMTP 发送 HTML 邮件"""
    today_str = datetime.now().strftime("%Y年%m月%d日")
    subject = f"【国企招聘日报】{today_str} · 外派越南 {vn_count} 条 · 共 {job_count} 条"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.SMTP_USER
    msg["To"] = config.TARGET_EMAIL
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    log.info(f"正在发送邮件至 {config.TARGET_EMAIL}...")
    try:
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.login(config.SMTP_USER, config.SMTP_PASS)
            server.sendmail(config.SMTP_USER, config.TARGET_EMAIL, msg.as_string())
        log.info("邮件发送成功 ✓")
        return True
    except Exception as e:
        log.error(f"邮件发送失败：{e}")
        return False


# ── 4. 主流程 ──────────────────────────────────────────────────────────────────
def main():
    log.info("=" * 50)
    log.info(f"国企招聘日报任务启动 · {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log.info("=" * 50)

    # 搜索职位
    jobs, coverage = search_jobs()
    if not jobs:
        log.error("未获取到任何招聘信息，任务终止")
        return

    # 生成邮件
    vn_jobs = [j for j in jobs if j.get("vietnam")]
    html = build_html_email(jobs, coverage)

    # 发送
    success = send_email(html, len(jobs), len(vn_jobs))
    if success:
        log.info(f"任务完成：{len(jobs)} 条职位，{len(vn_jobs)} 条越南外派，已发送至 {config.TARGET_EMAIL}")
    else:
        log.error("任务完成，但邮件发送失败，请检查 SMTP 配置")


if __name__ == "__main__":
    main()
