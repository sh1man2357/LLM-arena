import { useState } from 'react';
import { api } from './api';
import { Icon, PageTitle } from './ui';

export function Manage() {
  const [message, setMessage] = useState(''); const [busy, setBusy] = useState(false);
  async function unlock() { await api('/api/v1/admin/unlock', { method: 'POST', headers: { 'X-Arena-Local': '1' } }); }
  async function reference() { setBusy(true); setMessage('正在校验并导入完整参考赛…'); try { await unlock(); await api('/api/v1/imports', { method: 'POST', body: JSON.stringify({ source: 'bundled-v0.1' }) }); setMessage('参考赛已导入，可返回大厅观赛。'); } catch(e) { setMessage((e as Error).message); } finally { setBusy(false); } }
  async function upload(file: File | undefined) { if (!file) return; setBusy(true); try { await unlock(); const form = new FormData(); form.append('file', file); await api('/api/v1/imports/replay', { method: 'POST', body: form }); setMessage('Replay 已验证并导入。'); } catch(e) { setMessage((e as Error).message); } finally { setBusy(false); } }
  return <><PageTitle eyebrow="主办方 / CONTROL ROOM" title="让比赛准备就绪。" detail="本机管理入口 · 收卷、资格与比赛作业在此组织。" /><div className="manage-grid"><section className="panel"><div className="section-heading"><h2>导入比赛证据</h2><Icon name="share" /></div><p className="muted">已有回放可以直接观赛；原始文件与验证哈希分别保留。</p><button className="primary" disabled={busy} onClick={reference}><Icon name="check" />导入 v0.1 完整参考赛</button><label className="file-input-label button"><Icon name="share" />上传 Replay<input type="file" accept=".jsonl" disabled={busy} onChange={e => upload(e.target.files?.[0])} /></label><p role="status" className="form-message">{message}</p></section><section className="panel protocol-card"><p className="eyebrow">模型开发协议</p><strong className="protocol-time mono">60<span>min</span></strong><h2>交卷即冻结。</h2><p className="muted">从收到任务起计时，可提前交卷。时限内自主编译、测试与修改，无额外 token 或轮数配置。正式比赛只执行已冻结的程序。</p><span className="small muted">收卷与作业工作流正在本阶段接入；已有证据导入可直接使用。</span></section></div></>;
}
