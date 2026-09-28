# Ubuntu / Docker 安装与更新（v1.2.0）

适用于已有 AstrBot 的 Ubuntu 主机，包括菲比的 `/opt/phoebe` Docker 数据卷布局。插件运行需要 AstrBot >= 4.28.1，使用其 Python 3.12+ 环境；无需额外的模型或搜索密钥。

## 方式一：AstrBot 管理页

在**菲比实例**的插件管理页安装或更新：

```text
https://github.com/XyeeCheng/astrbot_plugin_a_guess
```

已安装时先等当前局结束，再停用本插件、备份本插件源码与插件数据、更新并启用。日志应包含“已加载 200 道本地题卡”。管理员发送 `a题库状态`，应看到 v1.2.0、题库 v4、普通150、困难50。

进行中的对局有独立题卡快照，不会因更新清零。旧快照仍按旧核心规则判定；如需马上使用新规则，可由发起人 `a结束` 后 `a再来`。

## 方式二：Ubuntu 离线安装包

从 [v1.2.0 Release](https://github.com/XyeeCheng/astrbot_plugin_a_guess/releases/tag/v1.2.0) 下载：

- `astrbot_plugin_a_guess-v1.2.0-ubuntu.tar.gz`
- `SHA256SUMS-v1.2.0.txt`

ZIP 包包含同一套源码。包内没有虚拟环境、用户对局数据库、机器人配置或密钥。

在独立临时目录中核对哈希、解压、审查 `install_ubuntu.py`，随后执行：

```bash
# 在下载目录执行；只下载了 tar.gz 时会跳过 ZIP。
sha256sum --check --ignore-missing SHA256SUMS-v1.2.0.txt
tar -xzf astrbot_plugin_a_guess-v1.2.0-ubuntu.tar.gz
cd astrbot_plugin_a_guess
python3 install_ubuntu.py check
python3 -m unittest discover -s tests -v
```

哈希用于发现传输或文件改动，不是独立的数字签名。清单检查全部列出的文件及 Python 语法；测试是下一条单独执行的命令。

**先在菲比管理页停用“a一把”**，确认目标属于菲比，然后安装：

```bash
sudo python3 install_ubuntu.py install \
  --target /opt/phoebe/data/plugins/astrbot_plugin_a_guess \
  --plugin-stopped
```

`--plugin-stopped` 表示操作者已停用插件，脚本不会连接管理页替你停用。脚本适用于标准 `data/plugins` 布局；自定义布局应填写实际挂载目录。父级 `plugins` 必须已经存在。

安装器会：

1. 校验发行包、插件身份与目标路径，拒绝链接路径、源/目标嵌套和其他插件目录。
2. 准备源码，保留目标原来的属主。
3. 把旧源码移到 `data/plugin_data/astrbot_plugin_a_guess/code_backups/<时间戳>/`，避免被扫描为第二个插件。
4. 替换本插件源码；最终目录切换失败时恢复旧目录，并打印备份路径。

安装后回到菲比管理页启用或重载本插件。脚本不启动服务，不修改游戏数据库、QQ 或模型配置。新版本首次加载时自动给申诉表补充状态字段，保留原记录。

## 交给服务器 AI 的操作要求

把本页和 Release 链接发给服务器上的 AI：

> 只更新 `/opt/phoebe` 的 a一把插件至 v1.2.0。先核实挂载路径与版本，下载核对哈希、审查安装器，执行 check 与测试。插件停用后用安装器更新，报告备份路径，再启用本插件。核对版本、200题加载日志和 SQLite 旧记录；不要发送群测试消息。真实群验收等我在指定群主动发命令后进行。

## 验收

在用户指定的测试群，由用户发送：

```text
@菲比 a一把
@菲比 a提示
@菲比 a猜二分
@菲比 a进度
@菲比 a结束
@菲比 a一把困难
@菲比 a上局
```

核对开场无题目提示、结束带原题链接和中文、上局可重看且当前局不变。**随机题不保证答案是二分**；回归测试已固定1354B/888C验证普通二分核心。

开局后重载插件，核对题卡、次数和截止时间保持。超时群发需单独验收真实平台权限；无回执或异常会保存结算，可用 `a上局` 找回，不无限自动重发。

## 回滚

先停用本插件，将当前源码移到本插件备份目录，再把安装器打印的旧源码备份恢复到原插件路径，随后启用。不要把备份直接复制成 `plugins` 下的第二个插件。

安装器只备份源码。需回退数据时，使用更新前单独保存的本插件数据备份；SQLite 应在停用后复制完整目录，或使用 SQLite backup API。仅回滚源码时，新版题卡快照可能与旧判定器不一致，应先结束新版本开启的对局。不要覆盖 AstrBot 主数据库、其他插件数据或机器人配置。
