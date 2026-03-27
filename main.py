#!/usr/bin/env python3
"""
国企招聘信息每日自动搜索 & 邮件推送
每天自动搜索国企招聘（重点外派越南），汇总后发送至指定邮箱
"""

import anthropic
import smtplib
import json
import logging
from datetime import datetime
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


# ── 1. 搜索国企招聘信息 ────────────────────────────────────────────────────────
def search_jobs() -> list[dict]:
    """调用 Claude API（联网搜索）获取最新国企招聘信息"""
    log.info("开始搜索国企招聘信息...")
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    today = datetime.now().strftime("%Y年%m月%d日")

    prompt = f"""今天是{today}。请通过网络搜索最新的中国国有企业（国企/央企）招聘信息，
特别重点关注外派越南的职位机会。

搜索关键词方向（逐一搜索）：
1. 国企招聘 外派越南 {datetime.now().year}
2. 央企越南项目 招聘
3. 中交股份 越南 招聘
4. 中国电建 越南 招聘
5. 中铁 越南 工程项目 招聘
6. 中建 越南 海外项目 职位
7. 国家电网 越南 外派
8. 华为中兴 越南 招聘（含国企背景）
9. 中国银行 越南 招聘
10. 国企海外招聘 越南 胡志明市 河内

请整理出12-18条招聘信息，以如下JSON数组格式返回，不要包含任何其他文字：
[
  {{
    "title": "职位名称",
    "company": "企业全称（如中国交通建设股份有限公司）",
    "company_short": "简称（如中交股份）",
    "location": "工作地点（如越南河内、越南胡志明市）",
    "industry": "行业（能源|建筑|通信|金融|交通|制造|其他）",
    "vietnam": true或false,
    "salary": "薪资描述（若无则空字符串）",
    "requirements": "主要要求（30字内）",
    "deadline": "截止日期（若无则空字符串）",
    "source": "来源平台（如智联招聘/前程无忧/官网等）",
    "url": "职位链接（若有）",
    "hot": true或false,
    "desc": "职位简介（40字内）"
  }}
]"""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )

    # 提取 JSON
    raw_text = ""
    for block in response.content:
        if block.type == "text":
            raw_text += block.text

    # 解析 JSON 数组
    start = raw_text.find("[")
    end = raw_text.rfind("]")
    if start == -1 or end == -1:
        log.warning("未能从响应中找到 JSON 数组，返回空列表")
        return []

    jobs = json.loads(raw_text[start : end + 1])
    log.info(f"搜索完成，共获取 {len(jobs)} 条职位，其中越南外派 {sum(1 for j in jobs if j.get('vietnam'))} 条")
    return jobs


# ── 2. 生成 HTML 邮件内容 ──────────────────────────────────────────────────────
def build_html_email(jobs: list[dict]) -> str:
    """将职位列表渲染为精美 HTML 邮件"""
    today_str = datetime.now().strftime("%Y年%m月%d日")
    vn_jobs = [j for j in jobs if j.get("vietnam")]
    other_jobs = [j for j in jobs if not j.get("vietnam")]

    industries = {
        "能源": "#1D9E75", "建筑": "#378ADD", "通信": "#7F77DD",
        "金融": "#D4537E", "交通": "#BA7517", "制造": "#639922", "其他": "#888780",
    }

    def job_card(job: dict, highlight: bool = False) -> str:
        ind_color = industries.get(job.get("industry", "其他"), "#888780")
        border = f"border-left: 4px solid {ind_color};" if highlight else ""
        vn_badge = '<span style="background:#E1F5EE;color:#0F6E56;font-size:11px;padding:2px 8px;border-radius:4px;margin-left:6px;font-weight:600;">外派越南</span>' if job.get("vietnam") else ""
        hot_badge = '<span style="background:#FCEBEB;color:#A32D2D;font-size:11px;padding:2px 8px;border-radius:4px;margin-left:4px;">热招</span>' if job.get("hot") else ""
        salary_str = f'<span style="color:#1D9E75;font-weight:600;">{job["salary"]}</span> · ' if job.get("salary") else ""
        url_str = f'<a href="{job["url"]}" style="color:#378ADD;font-size:12px;text-decoration:none;">查看详情 →</a>' if job.get("url") else ""
        return f"""
        <div style="background:#fff;border-radius:8px;padding:14px 16px;margin-bottom:10px;{border}box-shadow:0 1px 4px rgba(0,0,0,0.06);">
          <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:4px;">
            <div>
              <span style="font-size:15px;font-weight:600;color:#1a1a1a;">{job.get('title','—')}</span>
              {vn_badge}{hot_badge}
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
    other_section = "".join(job_card(j) for j in other_jobs)

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
          <div style="color:#85B7EB;font-size:24px;font-weight:700;">{len({j.get('company_short') or j.get('company') for j in jobs})}</div>
          <div style="color:#888;font-size:11px;">招聘企业</div>
        </div>
        <div style="text-align:center;">
          <div style="color:#FAC775;font-size:24px;font-weight:700;">{len({j.get('industry') for j in jobs})}</div>
          <div style="color:#888;font-size:11px;">覆盖行业</div>
        </div>
      </div>
    </div>

    <!-- 越南专区 -->
    <div style="background:#fff;padding:20px 20px 10px;border-top:3px solid #1D9E75;">
      <div style="font-size:14px;font-weight:600;color:#0F6E56;margin-bottom:12px;display:flex;align-items:center;gap:6px;">
        🌏 外派越南专项职位（{len(vn_jobs)} 条）
      </div>
      {vn_section}
    </div>

    <!-- 其他职位 -->
    <div style="background:#fff;padding:20px 20px 10px;margin-top:2px;">
      <div style="font-size:14px;font-weight:600;color:#333;margin-bottom:12px;">
        📋 国内及其他海外职位（{len(other_jobs)} 条）
      </div>
      {other_section}
    </div>

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
    jobs = search_jobs()
    if not jobs:
        log.error("未获取到任何招聘信息，任务终止")
        return

    # 生成邮件
    vn_jobs = [j for j in jobs if j.get("vietnam")]
    html = build_html_email(jobs)

    # 发送
    success = send_email(html, len(jobs), len(vn_jobs))
    if success:
        log.info(f"任务完成：{len(jobs)} 条职位，{len(vn_jobs)} 条越南外派，已发送至 {config.TARGET_EMAIL}")
    else:
        log.error("任务完成，但邮件发送失败，请检查 SMTP 配置")


if __name__ == "__main__":
    main()
