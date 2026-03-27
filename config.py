"""
配置文件 —— 填入你自己的密钥和邮箱信息
推荐用环境变量管理敏感信息（见注释）
"""

import os

# ── Anthropic API ──────────────────────────────────────────────────────────────
# 前往 https://console.anthropic.com 获取
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "sk-ant-xxxxxxxxxxxxxxxx")

# ── 目标收件邮箱 ───────────────────────────────────────────────────────────────
TARGET_EMAIL = os.getenv("TARGET_EMAIL", "389556453@qq.com")

# ── SMTP 发件配置 ──────────────────────────────────────────────────────────────
# 下面默认使用 QQ 邮箱 SMTP，如用其他邮箱请修改对应参数

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))  # SSL 端口

# 发件人邮箱（建议单独申请一个用于发送通知的邮箱）
SMTP_USER = os.getenv("SMTP_USER", "your_sender@qq.com")

# QQ邮箱：在「设置→账户→SMTP服务」中生成授权码（不是登录密码！）
# 163邮箱：同样使用授权码
# Gmail：需开启「应用专用密码」
SMTP_PASS = os.getenv("SMTP_PASS", "your_smtp_auth_code_here")

# ── 其他设置 ───────────────────────────────────────────────────────────────────
# 每次搜索的最大职位数（越大消耗 token 越多）
MAX_JOBS = 18

# 日志文件路径
LOG_FILE = "job_alert.log"
