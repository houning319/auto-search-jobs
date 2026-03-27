# 国企招聘日报 · 自动化脚本

每天早8点自动搜索国企招聘信息（重点外派越南），发送至指定邮箱。

---

## 文件结构

```
soe_job_alert/
├── main.py                              # 主程序
├── config.py                            # 配置（API密钥 / SMTP）
├── requirements.txt                     # 依赖
└── .github/workflows/daily_job_alert.yml  # GitHub Actions 定时任务
```

---

## 快速部署（GitHub Actions，推荐）

### 第一步：上传代码到 GitHub

```bash
git init
git add .
git commit -m "init: 国企招聘日报"
git remote add origin https://github.com/你的用户名/soe-job-alert.git
git push -u origin main
```

### 第二步：添加 Secrets

在 GitHub 仓库页面：**Settings → Secrets and variables → Actions → New repository secret**

| Secret 名称        | 填写内容                                    |
|--------------------|---------------------------------------------|
| `ANTHROPIC_API_KEY`| Anthropic 控制台的 API Key                  |
| `SMTP_HOST`        | `smtp.qq.com`（QQ邮箱）                     |
| `SMTP_PORT`        | `465`                                       |
| `SMTP_USER`        | 发件人邮箱，如 `sender@qq.com`              |
| `SMTP_PASS`        | QQ邮箱的 **SMTP授权码**（非登录密码）       |
| `TARGET_EMAIL`     | `389556453@qq.com`                          |

### 第三步：启用 Actions

进入 **Actions** 标签页，点击 **Enable GitHub Actions**。

每天北京时间8点自动运行。也可以点击 **Run workflow** 立即手动触发测试。

---

## QQ 邮箱 SMTP 授权码获取

1. 登录 QQ 邮箱网页版
2. 设置 → 账户 → 找到「POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务」
3. 开启「SMTP服务」，按提示发送短信验证
4. 生成授权码，复制填入 `SMTP_PASS`

---

## 本地运行测试

```bash
# 安装依赖
pip install -r requirements.txt

# 编辑 config.py，填入真实的 API Key 和 SMTP 信息
# 然后运行
python main.py
```

---

## 费用参考

- **Anthropic API**：每次搜索约消耗 3000-5000 tokens，每月约 ¥1-3 元
- **GitHub Actions**：免费账户每月 2000 分钟，每次运行约 2 分钟，完全够用
- **邮件发送**：QQ SMTP 免费

---

## 常见问题

**Q：邮件发送失败，提示认证错误？**
A：QQ邮箱 SMTP 需要使用授权码，不是登录密码。

**Q：如何修改搜索关键词？**
A：编辑 `main.py` 中 `search_jobs()` 函数的 `prompt` 内容。

**Q：如何同时发给多人？**
A：将 `config.py` 中 `TARGET_EMAIL` 改为逗号分隔的多个邮箱，并在 `send_email()` 函数中将 `sendmail` 的第二个参数改为列表。
