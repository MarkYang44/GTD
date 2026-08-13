# 局域网 Web 访问实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 Web 服务安全地扩展为同一局域网可访问，并重启验证。

**Architecture:** 保留 Flask 和端口 `8233`，仅扩大监听地址；用户文档和配置回归测试与实现同步。服务重启前按进程命令和 cwd 验证所有权。

**Tech Stack:** Python, Flask, unittest, macOS networking tools.

## Global Constraints

- 不修改下载业务、页面交互或端口 `8233`。
- 不停止不属于当前项目的进程。
- 不删除或改写 `downloads` 中的文件。
- 不增加公网暴露、认证、TLS 或新依赖。

---

### Task 1: LAN listener, documentation, regression, and restart

**Files:**
- Modify: `app.py`
- Modify: `README.md`
- Modify: `tests/test_web_progress.py`

**Interfaces:**
- Produces `WEB_HOST = "0.0.0.0"` and `WEB_PORT = 8233`.
- Keeps local access at `http://127.0.0.1:8233` and adds LAN access at `http://<LAN-IP>:8233`.

- [ ] Add a failing configuration test for the listener and documentation.
- [ ] Run the focused test and confirm failure because the host is still `127.0.0.1`.
- [ ] Change the listener and startup text; synchronize README security and access instructions.
- [ ] Run focused and full automated verification.
- [ ] Identify the current 8233 listener by PID, command, and cwd; stop it only if it belongs to this project.
- [ ] Start `venv/bin/python app.py` and verify loopback plus LAN-IP HTTP 200.
- [ ] Verify download-file hashes remain unchanged.
